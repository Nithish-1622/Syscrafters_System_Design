# Order Creation & 30-Second Outage Recovery Sequence Diagram

## 1. Failure & Recovery Scenario: Payment Success with Order Service Unavailable for 30 Seconds

This sequence diagram depicts the resilient recovery flow when payment succeeds, but the Order Service is down for 30 seconds. It shows broker retention, consumer reconnection, atomic transactional deduplication, and transactional outbox dispatch.

```mermaid
sequenceDiagram
    autonumber
    participant PaySvc as Payment Service
    participant Broker as Kafka / Message Broker (Topic: payment.events)
    participant Consumer as PaymentEventConsumer (Order Pod)
    participant IdemProc as IdempotentEventProcessor
    participant OrderApp as OrderApplicationService
    participant OrderDB as PostgreSQL (Order DB)
    participant OutboxWorker as TransactionalOutboxDispatcher
    participant Downstream as Fulfillment / Notification Svc

    Note over PaySvc,Broker: Phase 1: Payment Successfully Captured
    PaySvc->>Broker: Publish "PaymentSucceededEvent" (eventId="EVT-9001", orderId="ORD-101", amount=150.00)
    Broker-->>PaySvc: ACK (Offset 4520 Committed)

    Note over Consumer,OrderDB: Phase 2: Order Service Down (0s - 30s)
    Note over Broker: Order Service replicas are unreachable.<br/>Broker holds message at partition offset 4520.<br/>No messages lost.

    Note over Consumer,OrderDB: Phase 3: Order Service Recovers (t = 31s)
    Consumer->>Broker: Poll / Fetch unacknowledged messages
    Broker-->>Consumer: Deliver "PaymentSucceededEvent" (eventId="EVT-9001", orderId="ORD-101")
    
    Consumer->>IdemProc: processEvent(envelope)
    
    Note over IdemProc,OrderDB: Phase 4: Atomic DB Transaction (Idempotency + State Transition + Outbox)
    IdemProc->>OrderDB: BEGIN TRANSACTION
    
    IdemProc->>OrderDB: INSERT INTO processed_events (event_id, event_type, processed_at) VALUES ('EVT-9001', 'PaymentSucceeded', NOW())
    
    alt Event Already Processed (Duplicate Delivery)
        OrderDB-->>IdemProc: Primary Key Conflict / DuplicateKeyException
        IdemProc->>OrderDB: ROLLBACK
        IdemProc-->>Consumer: Return Duplicate Skipped (ACK broker)
    else First Time Processing (Success)
        OrderDB-->>IdemProc: 1 Row Inserted
        
        IdemProc->>OrderApp: confirmOrder(orderId="ORD-101", paymentId="TX-1001")
        OrderApp->>OrderDB: UPDATE orders SET status = 'CONFIRMED', updated_at = NOW() WHERE id = 'ORD-101'
        
        OrderApp->>OrderDB: INSERT INTO outbox_events (id, aggregate_type, aggregate_id, event_type, payload) VALUES ('OUT-77', 'Order', 'ORD-101', 'OrderConfirmedEvent', '{"orderId":"ORD-101"}')
        
        IdemProc->>OrderDB: COMMIT TRANSACTION
        OrderDB-->>IdemProc: Transaction Committed
        IdemProc-->>Consumer: Event Processed Successfully
        Consumer->>Broker: Commit Offset 4520 (ACK)
    end

    Note over OutboxWorker,Downstream: Phase 5: Transactional Outbox Dispatching
    OutboxWorker->>OrderDB: SELECT * FROM outbox_events WHERE dispatched = FALSE LIMIT 50
    OrderDB-->>OutboxWorker: Return ['OUT-77']
    OutboxWorker->>Broker: Publish "OrderConfirmedEvent" (Topic: order.events)
    Broker-->>OutboxWorker: ACK
    OutboxWorker->>OrderDB: UPDATE outbox_events SET dispatched = TRUE WHERE id = 'OUT-77'
    Broker->>Downstream: Deliver "OrderConfirmedEvent" to Fulfillment & Notification
```

---

## 2. Key Resilience & Correctness Guarantees

1. **At-Least-Once Broker Delivery $\rightarrow$ Exactly-Once Business Outcome:**
   - The message broker retains messages during service outages.
   - Dedup table `processed_events` in the Order database ensures redelivered messages are safely ignored.
2. **Transactional Outbox Pattern (Dual-Write Solution):**
   - The state transition (`orders.status = CONFIRMED`) and the outbound event (`outbox_events`) are committed in the **same local database transaction**.
   - If the system crashes after committing to the database but before publishing to Kafka, the `TransactionalOutboxDispatcher` picks up the pending row upon restart and publishes it.
