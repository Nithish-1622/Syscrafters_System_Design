# Inventory & Reservation Service — Class Diagram

## 1. Class Structure & Object-Oriented Relationships

```mermaid
classDiagram
    %% Presentation Layer
    class InventoryController {
        -ReservationApplicationService reservationService
        -InventoryQueryService queryService
        +reserveStock(ReservationRequestDTO request, String idempotencyKey) ResponseEntity~ReservationResponseDTO~
        +releaseStock(UUID reservationId) ResponseEntity~Void~
        +getStockStatus(String productId) ResponseEntity~StockDTO~
    }

    %% Application Layer
    class ReservationApplicationService {
        -IInventoryRepository inventoryRepo
        -IReservationRepository reservationRepo
        -IIdempotencyStore idempotencyStore
        -IEventPublisher eventPublisher
        +createReservation(CreateReservationCmd cmd) ReservationResultDTO
        +confirmReservation(UUID reservationId) void
        +releaseReservation(UUID reservationId, String reason) void
    }

    class ReservationExpiryScheduler {
        -IReservationRepository reservationRepo
        -IInventoryRepository inventoryRepo
        -IEventPublisher eventPublisher
        -int batchSize
        +sweepExpiredReservations() void
    }

    %% Domain Aggregates & Entities
    class InventoryItem {
        -ProductId productId
        -int totalQuantity
        -int availableQuantity
        -int reservedQuantity
        -int soldQuantity
        -long version
        -Instant updatedAt
        +canReserve(int qty) boolean
        +reserve(int qty) void
        +release(int qty) void
        +confirmSale(int qty) void
    }

    class InventoryReservation {
        -ReservationId reservationId
        -IdempotencyKey idempotencyKey
        -ProductId productId
        -UserId userId
        -int quantity
        -ReservationStatus status
        -Instant reservedAt
        -Instant expiresAt
        +isExpired(Instant now) boolean
        +markPaymentPending() void
        +confirm() void
        +expire() void
        +release() void
    }

    class ReservationStatus {
        <<enumeration>>
        RESERVED
        PAYMENT_PENDING
        CONFIRMED
        EXPIRED
        RELEASED
        CANCELLED
    }

    %% Ports / SPI Interfaces
    class IInventoryRepository {
        <<interface>>
        +findByProductId(ProductId id) Optional~InventoryItem~
        +reserveStockAtomic(ProductId id, int qty) boolean
        +releaseStockAtomic(ProductId id, int qty) boolean
        +confirmSaleAtomic(ProductId id, int qty) boolean
        +save(InventoryItem item) void
    }

    class IReservationRepository {
        <<interface>>
        +findById(ReservationId id) Optional~InventoryReservation~
        +findByIdempotencyKey(IdempotencyKey key) Optional~InventoryReservation~
        +findActiveExpiredReservations(Instant cutoff, int limit) List~InventoryReservation~
        +updateStatusIfCurrent(ReservationId id, ReservationStatus current, ReservationStatus next) boolean
        +save(InventoryReservation reservation) void
    }

    class IIdempotencyStore {
        <<interface>>
        +checkOrLock(String key, String hash, Duration ttl) IdempotencyStatus
        +storeResult(String key, Object payload, Duration ttl) void
        +getResult(String key) Optional~Object~
    }

    class IEventPublisher {
        <<interface>>
        +publish(DomainEvent event) void
    }

    %% Infrastructure Adapters
    class PostgresInventoryRepository {
        -DataSource dataSource
        +reserveStockAtomic(ProductId id, int qty) boolean
        +releaseStockAtomic(ProductId id, int qty) boolean
        +confirmSaleAtomic(ProductId id, int qty) boolean
        +save(InventoryItem item) void
    }

    class PostgresReservationRepository {
        -DataSource dataSource
        +save(InventoryReservation reservation) void
        +findActiveExpiredReservations(Instant cutoff, int limit) List~InventoryReservation~
        +updateStatusIfCurrent(ReservationId id, ReservationStatus current, ReservationStatus next) boolean
    }

    class RedisIdempotencyStore {
        -RedisTemplate redisTemplate
        +checkOrLock(String key, String hash, Duration ttl) IdempotencyStatus
        +storeResult(String key, Object payload, Duration ttl) void
    }

    class KafkaEventPublisher {
        -KafkaTemplate kafkaTemplate
        +publish(DomainEvent event) void
    }

    %% Relationships
    InventoryController --> ReservationApplicationService : delegates to
    ReservationApplicationService --> IInventoryRepository : depends on
    ReservationApplicationService --> IReservationRepository : depends on
    ReservationApplicationService --> IIdempotencyStore : depends on
    ReservationApplicationService --> IEventPublisher : depends on
    ReservationExpiryScheduler --> IReservationRepository : queries
    ReservationExpiryScheduler --> IInventoryRepository : updates stock
    ReservationExpiryScheduler --> IEventPublisher : publishes expired event

    IInventoryRepository <|.. PostgresInventoryRepository : implements
    IReservationRepository <|.. PostgresReservationRepository : implements
    IIdempotencyStore <|.. RedisIdempotencyStore : implements
    IEventPublisher <|.. KafkaEventPublisher : implements

    InventoryReservation --> ReservationStatus : has state
    PostgresInventoryRepository ..> InventoryItem : persists
    PostgresReservationRepository ..> InventoryReservation : persists
```

---

## 2. Key Responsibilities & Defensible Design Rationale

| Class / Interface | Domain Responsibility | Concurrency & Idempotency Role |
| :--- | :--- | :--- |
| `InventoryItem` | Enforces fundamental stock invariants ($total = available + reserved + sold$). | Domain-level guard checking whether $requestedQty \le available$. |
| `IInventoryRepository` | Persistence port abstracting relational database write serialization. | Executes **atomic conditional updates** in SQL: `UPDATE ... WHERE available_quantity >= :qty`. Zero application locks. |
| `InventoryReservation` | Encapsulates single reservation entity, timestamped expiration, and status transitions. | Tracks `expires_at` and `idempotency_key` binding. |
| `IIdempotencyStore` | Fast distributed key-value lock & result cache interface (Redis backed). | Deduplicates incoming client retries within a 15-minute sliding window. |
| `ReservationExpiryScheduler` | Proactive background daemon releasing abandoned reservations. | Uses CAS state transitions (`RESERVED` $\rightarrow$ `EXPIRED`) to prevent double-release race conditions. |
| `KafkaEventPublisher` | Asynchronous integration publisher. | Emits `InventoryReservedEvent` to trigger checkout and order workflows. |
