# Payment Sequence Diagram

## 1. Complete Workflow: Success, Gateway Failure, Ambiguous Timeout & Reconciliation

This sequence diagram illustrates the lifecycle of a payment request across synchronous processing, provider adapter routing, circuit breaker protection, ambiguous timeout isolation, and asynchronous reconciliation.

```mermaid
sequenceDiagram
    autonumber
    actor Customer as Customer / Checkout App
    participant PayCtrl as PaymentController
    participant IdemStore as Redis Idempotency Store
    participant PayApp as PaymentApplicationService
    participant Factory as PaymentProviderFactory
    participant CB as CircuitBreaker
    participant Adapter as StripePaymentAdapter
    participant Gateway as External Stripe Gateway
    participant PayDB as PostgreSQL (Payment DB)
    participant Broker as Kafka (Event Broker)
    participant ReconcileSvc as PaymentReconciliationService

    Customer->>PayCtrl: POST /api/v1/payments (Idempotency-Key: PAY-KEY-77)
    PayCtrl->>IdemStore: Check / Lock PAY-KEY-77
    
    alt Duplicate Payment Request
        IdemStore-->>PayCtrl: Key exists with status SUCCESS
        PayCtrl-->>Customer: 200 OK (Cached PaymentResultDTO)
    else New Request (Lock Acquired)
        IdemStore-->>PayCtrl: Lock OK
        PayCtrl->>PayApp: processPayment(cmd)
        
        PayApp->>Factory: getProvider(STRIPE)
        Factory-->>PayApp: StripePaymentAdapter
        
        PayApp->>PayDB: INSERT INTO payment_transactions (id, status='INITIATED')
        
        PayApp->>CB: execute(StripePaymentAdapter.processPayment)
        CB->>Adapter: processPayment(GatewayChargeRequest)
        Adapter->>Gateway: POST /v1/charges (HTTPS)
        
        alt Path A: Definite Success (HTTP 200)
            Gateway-->>Adapter: 200 OK { id: "ch_abc123", status: "succeeded" }
            Adapter-->>CB: GatewayChargeResult(SUCCESS, "ch_abc123")
            CB-->>PayApp: Result: SUCCESS
            PayApp->>PayDB: UPDATE payment_transactions SET status='SUCCESS', provider_ref='ch_abc123'
            PayApp->>Broker: Publish "PaymentSucceededEvent" (Topic: payment.events)
            PayApp->>IdemStore: Store Result(PAY-KEY-77, SUCCESS)
            PayApp-->>PayCtrl: PaymentResultDTO(SUCCESS)
            PayCtrl-->>Customer: 200 OK { status: "SUCCESS", txnId: "TX-1001" }

        else Path B: Definite Decline (HTTP 402 Card Declined)
            Gateway-->>Adapter: 402 Declined { error: "insufficient_funds" }
            Adapter-->>CB: GatewayChargeResult(FAILED, "insufficient_funds")
            CB-->>PayApp: Result: FAILED
            PayApp->>PayDB: UPDATE payment_transactions SET status='FAILED'
            PayApp->>Broker: Publish "PaymentFailedEvent" (Topic: payment.events)
            PayApp->>IdemStore: Store Result(PAY-KEY-77, FAILED)
            PayApp-->>PayCtrl: PaymentResultDTO(FAILED)
            PayCtrl-->>Customer: 400 Bad Request { status: "FAILED", error: "Card Declined" }

        else Path C: Ambiguous Network Timeout (HTTP 504 / ReadTimeout)
            Gateway--xAdapter: Socket Timeout / No Response
            Adapter-->>CB: PaymentGatewayTimeoutException
            CB-->>PayApp: Catch Timeout
            PayApp->>PayDB: UPDATE payment_transactions SET status='PENDING_VERIFICATION', retry_count=0
            PayApp-->>PayCtrl: PaymentResultDTO(PENDING_VERIFICATION)
            PayCtrl-->>Customer: 202 Accepted { status: "PENDING_VERIFICATION", message: "Verifying with bank" }
            
            %% Background Asynchronous Reconciliation
            Note over ReconcileSvc,Gateway: Asynchronous Polling / Webhook Resolution
            ReconcileSvc->>PayDB: SELECT * FROM payment_transactions WHERE status='PENDING_VERIFICATION'
            ReconcileSvc->>Adapter: queryPaymentStatus(refId, PAY-KEY-77)
            Adapter->>Gateway: GET /v1/charges?idempotency_key=PAY-KEY-77
            Gateway-->>Adapter: 200 OK { status: "succeeded", id: "ch_abc123" }
            Adapter-->>ReconcileSvc: Status: PAID
            ReconcileSvc->>PayDB: UPDATE payment_transactions SET status='SUCCESS'
            ReconcileSvc->>Broker: Publish "PaymentSucceededEvent" (Topic: payment.events)
        end
    end
```

---

## 2. Key Reliability Design Elements

1. **Strict Prevention of Double Charges:**
   - Under timeout conditions (Path C), the service **never blind-retries a charge request**.
   - Instead, it marks the transaction `PENDING_VERIFICATION` and relies on `queryPaymentStatus()` using the original `Idempotency-Key`.
2. **Circuit Breaker Shielding:**
   - If Stripe fails 50% of requests in a sliding window, `CircuitBreaker` opens, instantly failing fast without tying up server threads.
3. **Decoupled Event Notification:**
   - On verified success, `PaymentSucceededEvent` is published to Kafka, guaranteeing downstream Order confirmation and Inventory finalization.
