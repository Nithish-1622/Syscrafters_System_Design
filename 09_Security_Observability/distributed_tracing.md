# SALESTORM 2026 | Distributed Tracing Architecture (OpenTelemetry & W3C Trace Context)

## 1. Specification & Standards

SALESTORM implements the **W3C Trace Context Specification** via the **OpenTelemetry (OTel)** standard. In a distributed checkout flow, a single purchase traverses 4 independent services and an asynchronous message broker. Tracing allows SREs to visualize the exact latency breakdown and pinpoint bottlenecks.

### W3C `traceparent` Header Format:
$$\text{traceparent} = \text{version}-\text{trace\_id}-\text{parent\_id}-\text{trace\_flags}$$
$$\text{Example: } \texttt{00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01}$$

- `version`: `00` (Current standard).
- `trace_id`: 16-byte random hex (Global identifier for the entire purchase flow).
- `parent_id`: 8-byte hex (Identifies immediate parent span).
- `trace_flags`: `01` (Indicates span was sampled for recording).

---

## 2. End-to-End Distributed Span Hierarchy

```
[ Root Span: POST /api/v1/reservations ] (TraceId: 4bf92f35...)
  │
  ├── [ Child Span: RateLimiter: SlidingWindowCheck ] ─── 0.8ms
  ├── [ Child Span: InventoryService: AtomicConditionalUpdate ] ─── 2.1ms
  └── [ Child Span: TransactionalOutbox: StageEvent ] ─── 0.9ms

[ Next Phase: POST /api/v1/payments ] (Same TraceId)
  │
  ├── [ Child Span: PaymentService: AuthorizeToken ] ─── 1.2ms
  ├── [ Child Span: ExternalGateway: StripeChargeCall ] ─── 320ms (External Network)
  └── [ Child Span: PaymentService: RecordTransaction ] ─── 1.5ms

[ Async Phase: Message Broker Relay ] (Trace Context in Message Attributes)
  │
  └── [ Child Span: OrderConsumer: ProcessPaymentSucceeded ]
        │
        ├── [ Child Span: IdempotencyCheck ] ─── 0.5ms
        ├── [ Child Span: Database: InsertOrderAndItems ] ─── 3.2ms
        └── [ Child Span: NotificationService: SendConfirmationEmail ] ─── 15ms
```

---

## 3. Asynchronous Context Propagation Across Message Queues

When an event is published to an asynchronous queue (SQS, Kafka, RabbitMQ), HTTP headers are not present. SALESTORM injects the W3C trace context into:
1. **Message Broker Native Attributes**: AWS SQS MessageAttributes (`AWSTraceHeader` or custom `traceparent`).
2. **CloudEvents Payload Envelope**: `traceparent` and `correlationid` fields directly embedded in the event JSON.

The downstream consumer extracts these attributes and initializes its child span, ensuring that the trace is uninterrupted across asynchronous boundaries!
