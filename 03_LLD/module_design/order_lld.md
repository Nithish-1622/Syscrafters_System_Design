# Order Service — Low-Level Design

## 1. Service Overview & Problem Scope

The **Order Service** manages the lifecycle of customer orders from initial placement through fulfillment, shipping, and delivery.

Key requirements:
1. **Strict Order State Machine:** Enforce guaranteed state progressions (`CREATED` $\rightarrow$ `PAYMENT_PENDING` $\rightarrow$ `CONFIRMED` $\rightarrow$ `PROCESSING` $\rightarrow$ `SHIPPED` $\rightarrow$ `OUT_FOR_DELIVERY` $\rightarrow$ `DELIVERED`). Invalid transitions (e.g., `CREATED` $\rightarrow$ `DELIVERED`) are strictly rejected at the domain level.
2. **Resilience to Downstream Service Outage (30s Outage Scenario):** If the Order Service is down when a `PaymentSucceededEvent` arrives, the message broker retains the event and retries until the service recovers.
3. **Idempotent Event Consumption:** Handle duplicate `PaymentSucceededEvent` deliveries without creating duplicate orders or double-transitioning state.
4. **Transactional Outbox Pattern:** Ensure order state changes and outgoing domain events are written in a single local database transaction before publication to Kafka/SQS.

---

## 2. Hexagonal Domain Architecture & Layer Separation

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                             ORDER SERVICE BOUNDARY                              │
│                                                                                 │
│   ┌─────────────────────────────────────────────────────────────────────────┐   │
│   │                        API & Event Consumer Layer                       │   │
│   │   [OrderController]                 [PaymentEventConsumer]              │   │
│   └────────────────────────────────────┬────────────────────────────────────┘   │
│                                        │                                        │
│   ┌────────────────────────────────────▼────────────────────────────────────┐   │
│   │                       Application Service Layer                         │   │
│   │   [OrderApplicationService]         [TransactionalOutboxDispatcher]     │   │
│   │   [IdempotentEventProcessor]        [OrderQueryService]                 │   │
│   └────────────────────────────────────┬────────────────────────────────────┘   │
│                                        │                                        │
│   ┌────────────────────────────────────▼────────────────────────────────────┐   │
│   │                             Domain Layer                                │   │
│   │   Aggregates: [Order]               Entities: [OrderItem]               │   │
│   │   State Pattern: [IOrderState]      Concrete States: [CreatedState,     │   │
│   │                  [PaymentPendingState], [ConfirmedState], [ShippedState]│   │
│   │   Value Obj:  [OrderId]  [CustomerId]  [ShippingAddress]  [Money]       │   │
│   │   Exceptions: [InvalidOrderStateTransitionException]                    │   │
│   └────────────────────────────────────┬────────────────────────────────────┘   │
│                                        │                                        │
│   ┌────────────────────────────────────▼────────────────────────────────────┐   │
│   │                           Ports (SPI Interfaces)                        │   │
│   │   [IOrderRepository]                [IProcessedEventRepository]         │   │
│   │   [IOutboxRepository]               [IMessagePublisher]                 │   │
│   └────────────────────────────────────┬────────────────────────────────────┘   │
│                                        │                                        │
│   ┌────────────────────────────────────▼────────────────────────────────────┐   │
│   │                        Adapters (Infrastructure)                        │   │
│   │   [PostgresOrderRepository]         [PostgresProcessedEventRepo]        │   │
│   │   [PostgresOutboxRepository]        [KafkaMessagePublisher]             │   │
│   └─────────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Class & Interface Specification

### 3.1 Domain Aggregate: `Order`

```java
public class Order {
    private final OrderId id;
    private final CustomerId customerId;
    private final ReservationId reservationId;
    private final List<OrderItem> items;
    private final ShippingAddress shippingAddress;
    private final Money totalAmount;
    private IOrderState currentState;
    private Instant createdAt;
    private Instant updatedAt;
    private Long version;

    public Order(OrderId id, CustomerId customerId, ReservationId reservationId, 
                 List<OrderItem> items, ShippingAddress address, Money totalAmount) {
        this.id = id;
        this.customerId = customerId;
        this.reservationId = reservationId;
        this.items = List.copyOf(items);
        this.shippingAddress = address;
        this.totalAmount = totalAmount;
        this.currentState = new CreatedState();
        this.createdAt = Instant.now();
        this.updatedAt = this.createdAt;
    }

    // State Pattern Transitions
    public void markPaymentPending() {
        this.currentState = this.currentState.transitionTo(this, OrderStatus.PAYMENT_PENDING);
        this.updatedAt = Instant.now();
    }

    public void confirmPayment(PaymentTransactionId paymentId) {
        this.currentState = this.currentState.transitionTo(this, OrderStatus.CONFIRMED);
        this.updatedAt = Instant.now();
    }

    public void processFulfillment() {
        this.currentState = this.currentState.transitionTo(this, OrderStatus.PROCESSING);
        this.updatedAt = Instant.now();
    }

    public void ship(TrackingNumber trackingNumber) {
        this.currentState = this.currentState.transitionTo(this, OrderStatus.SHIPPED);
        this.updatedAt = Instant.now();
    }

    public void deliver() {
        this.currentState = this.currentState.transitionTo(this, OrderStatus.DELIVERED);
        this.updatedAt = Instant.now();
    }

    public void cancel(String reason) {
        this.currentState = this.currentState.transitionTo(this, OrderStatus.CANCELLED);
        this.updatedAt = Instant.now();
    }
}
```

---

### 3.2 State Pattern Interfaces & State Encapsulation

```java
public interface IOrderState {
    OrderStatus getStatus();
    IOrderState transitionTo(Order order, OrderStatus targetStatus);
}

public class CreatedState implements IOrderState {
    @Override
    public OrderStatus getStatus() { return OrderStatus.CREATED; }

    @Override
    public IOrderState transitionTo(Order order, OrderStatus targetStatus) {
        if (targetStatus == OrderStatus.PAYMENT_PENDING) {
            return new PaymentPendingState();
        }
        if (targetStatus == OrderStatus.CANCELLED) {
            return new CancelledState();
        }
        throw new InvalidOrderStateTransitionException(
            "Cannot transition from CREATED to " + targetStatus);
    }
}

public class PaymentPendingState implements IOrderState {
    @Override
    public OrderStatus getStatus() { return OrderStatus.PAYMENT_PENDING; }

    @Override
    public IOrderState transitionTo(Order order, OrderStatus targetStatus) {
        if (targetStatus == OrderStatus.CONFIRMED) {
            return new ConfirmedState();
        }
        if (targetStatus == OrderStatus.CANCELLED) {
            return new CancelledState();
        }
        throw new InvalidOrderStateTransitionException(
            "Cannot transition from PAYMENT_PENDING to " + targetStatus);
    }
}

public class ConfirmedState implements IOrderState {
    @Override
    public OrderStatus getStatus() { return OrderStatus.CONFIRMED; }

    @Override
    public IOrderState transitionTo(Order order, OrderStatus targetStatus) {
        if (targetStatus == OrderStatus.PROCESSING) {
            return new ProcessingState();
        }
        if (targetStatus == OrderStatus.CANCELLED) {
            return new CancelledState();
        }
        throw new InvalidOrderStateTransitionException(
            "Cannot transition from CONFIRMED to " + targetStatus);
    }
}
```

---

### 3.3 Ports / SPI Interfaces

```java
public interface IOrderRepository {
    Optional<Order> findById(OrderId id);
    Optional<Order> findByReservationId(ReservationId reservationId);
    void save(Order order);
}

public interface IProcessedEventRepository {
    // Inserts eventId with UNIQUE constraint in the same DB transaction
    boolean tryRecordProcessedEvent(String eventId, String eventType, Instant processedAt);
}

public interface IOutboxRepository {
    void saveEvent(OutboxRecord outboxRecord);
    List<OutboxRecord> fetchUnsentEvents(int batchSize);
    void markSent(List<UUID> eventIds);
}
```

---

## 4. Handling 30-Second Order Service Failure Scenario

### 4.1 Failure Timeline & Recovery Sequence
1. **$T_0$:** Payment Service captures funds successfully and publishes `PaymentSucceededEvent(eventId=EVT-9001, orderId=ORD-101, reservationId=RES-555)` to the `payment.events` topic/queue.
2. **$T_1$ (Order Service Down):** Order Service pod crashes or encounters database connection saturation.
3. **$T_{1..30s}$ (Message Retention):**
   - The Message Broker (Kafka/RabbitMQ/SQS) retains the unacknowledged message on partition offset / queue.
   - Message visibility timeout expires or consumer heartbeat triggers rebalance.
   - No data loss occurs because messages are committed **only after successful DB transaction completion**.
4. **$T_{31s}$ (Order Service Restored):**
   - New Order Service replica boots up, connects to DB, and polls `payment.events` topic.
   - Redelivered `PaymentSucceededEvent(eventId=EVT-9001)` is received by `PaymentEventConsumer`.
5. **$T_{32s}$ (Idempotent Processing & Outbox Write):**
   - `IdempotentEventProcessor` executes in a single local database transaction:
     ```sql
     BEGIN TRANSACTION;
     -- Step A: Deduplication check
     INSERT INTO processed_events (event_id, event_type, processed_at) 
     VALUES ('EVT-9001', 'PaymentSucceeded', NOW());
     
     -- Step B: Transition Order
     UPDATE orders SET status = 'CONFIRMED', updated_at = NOW() WHERE id = 'ORD-101';
     
     -- Step C: Write outgoing event to Outbox table
     INSERT INTO outbox_events (id, aggregate_type, aggregate_id, payload, created_at)
     VALUES ('OUT-1', 'Order', 'ORD-101', '{"status":"CONFIRMED"}', NOW());
     
     COMMIT;
     ```
   - Message ACK is sent to the broker.
6. **$T_{33s}$:** `TransactionalOutboxDispatcher` reads `outbox_events` and emits `OrderConfirmedEvent` to downstream Fulfillment and Notification services.

---

## 5. Duplicate Event Delivery Handling

If the network drops the consumer ACK and Kafka redelivers `PaymentSucceededEvent(eventId=EVT-9001)`:
- `tryRecordProcessedEvent('EVT-9001')` triggers a `UniqueConstraintViolationException` on the `processed_events.event_id` primary key.
- The `IdempotentEventProcessor` catches this exception, recognizes the event as already committed, skips order state mutation, and immediately acknowledges the message.
- **Result:** Exact-once business processing semantics achieved over an at-least-once transport.
