# Data Model: VRAM OOM Stability for Video Pipelines

## 1) VideoExecutionLane

**Purpose**: Represents a model-dedicated heavy video execution lane in GPU workers.

**Fields**
- `lane_key` (enum: `anisora`, `phr00t`)
- `mode` (enum: `dedicated`, `degraded_shared`)
- `warm` (boolean)
- `availability` (enum: `ready`, `cold`, `unavailable`)
- `fallback_reason` (enum nullable: `capacity`, `quota`, `manual`)
- `updated_at` (datetime)

**Validation rules**
- In `dedicated` mode, one lane maps to one heavy model only.
- `fallback_reason` required when `mode=degraded_shared`.

## 2) DegradedQueuePolicy

**Purpose**: Governs overload handling for degraded shared-worker mode.

**Fields**
- `max_depth` (int, fixed = 25)
- `max_wait_seconds` (int, fixed = 30)
- `overflow_code` (string, fixed = `queue_overloaded`)

**Validation rules**
- `max_depth` and `max_wait_seconds` are immutable for this feature version.
- Exceeded depth or wait MUST produce deterministic overload result.

## 3) VideoGenerationConstraints

**Purpose**: Immutable model-specific request validation constraints.

**Fields**
- `model` (enum: `anisora`, `phr00t`)
- `fixed_steps` (int)
- `fixed_cfg` (float nullable)

**Validation rules**
- `anisora`: `fixed_steps=8`, `fixed_cfg` optional/unchanged by this feature.
- `phr00t`: `fixed_steps=4`, `fixed_cfg=1.0`.
- Violations fail pre-inference with validation error.

## 4) GenerationTask (existing; affected)

**Purpose**: Existing async generation job entity affected by routing/overload behavior.

**Relevant fields**
- `id` (string)
- `model` (string)
- `type` (string)
- `status` (enum: `pending`, `processing`, `done`, `failed`)
- `error_msg` (string nullable)
- `created_at`, `updated_at` (datetime)

**New behavior constraints**
- Task creation and enqueue must respect degraded queue policy.
- Overload rejection must occur before task execution when queue policy is exceeded.

## 5) MemoryDiagnosticEvent

**Purpose**: Operational event for memory safety and fallback observability.

**Fields**
- `event_type` (enum: `memory_cleanup`, `memory_post_generation`, `fallback_activated`, `queue_timeout`, `queue_overloaded`)
- `task_id` (string nullable)
- `model` (string nullable)
- `lane_mode` (enum: `dedicated`, `degraded_shared`)
- `value` (number/string nullable; e.g., allocated_gib, queue_depth, wait_seconds)
- `reason` (enum nullable: `capacity`, `quota`, `manual`)
- `timestamp` (datetime)

**Validation rules**
- `reason` required for `fallback_activated`.
- `value` required for memory and queue threshold events.

## Relationships

- `VideoExecutionLane` serves many `GenerationTask` entries over time.
- `DegradedQueuePolicy` governs `GenerationTask` admission in `degraded_shared` mode.
- `VideoGenerationConstraints` validates `GenerationTask` request payload before enqueue.
- `MemoryDiagnosticEvent` references `GenerationTask` and lane context for operational auditing.

## State Transition Summary

### Lane state
- `ready` -> `cold` (autoscaling/idle)
- `ready|cold` -> `unavailable` (capacity/quota failure)
- `unavailable` -> `ready` (recovered capacity/quota)

### Routing mode
- `dedicated` -> `degraded_shared` (fallback activation)
- `degraded_shared` -> `dedicated` (capacity restored)

### Queue admission outcome
- `admitted` (within depth/wait limits)
- `rejected_overloaded` (`503 queue_overloaded` on depth/wait breach)
