# Research: VRAM OOM Stability for Video Pipelines

## Decision 1: Use Dedicated Warm Execution Lanes for Heavy Video Models

**Decision**
- Split heavy video execution into separate model-dedicated lanes for `anisora` and `phr00t`.
- Keep one warm execution instance per lane in production profile when capacity and quota allow.

**Rationale**
- Current single video function can hold both heavy pipelines in one warm container, causing VRAM pressure and OOM risk under model switching.
- Dedicated lanes preserve warm-cache benefits for each model and avoid cross-model VRAM contention.

**Alternatives considered**
- Single shared lane with aggressive cache clearing: safer for memory but degrades model-switch latency.
- No warm lanes: cheaper but unacceptable cold-start UX for frequent switching.

## Decision 2: Apply Degraded Shared-Worker Fallback Instead of Immediate Rejection

**Decision**
- When dedicated lane is unavailable (capacity/quota pressure), route requests immediately to degraded shared-worker mode with single-active memory discipline.

**Rationale**
- Preserves availability and avoids unnecessary request rejection while maintaining memory safety.
- Aligns with clarified requirement to prefer safe execution path over immediate `503`.

**Alternatives considered**
- Wait-only on dedicated lane: may stall user flows under pressure.
- Immediate `503`: deterministic but harms availability and UX.

## Decision 3: Enforce Bounded Degraded Queue with Deterministic Overload Contract

**Decision**
- Degraded mode enforces queue depth limit `25` and max wait timeout `30s`.
- Exceeding either limit returns machine-readable `503 queue_overloaded`.

**Rationale**
- Prevents unbounded backlog and cascading latency while keeping behavior predictable for clients and tests.
- Provides clear operational and API-level overload semantics.

**Alternatives considered**
- Unlimited queue: better acceptance rate but unstable latency and poor operability.
- No queue (instant fail): simplest but too harsh under transient pressure.

## Decision 4: Enforce Fixed Video Parameters at Schema Boundary

**Decision**
- Validate fixed parameters pre-inference:
  - AniSora video requires `steps=8`
  - Phr00t video requires `steps=4`, `cfg=1.0`
- Invalid requests fail with `422` before task dispatch.

**Rationale**
- Removes drift between UI assumptions and backend runtime behavior.
- Reduces invalid workload entering expensive GPU paths.

**Alternatives considered**
- Clamp values silently: hides client errors and complicates debugging.
- Enforce only in pipeline internals: late failure and wasted queue/GPU resources.

## Decision 5: Standardize GPU Memory Fragmentation Mitigation and Observability

**Decision**
- Require GPU runtime allocator setting `PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True` in GPU images.
- Require post-generation cleanup/logging for memory diagnostics on success and failure paths.

**Rationale**
- Addresses fragmentation-related OOM patterns observed in logs.
- Provides operator evidence for memory safety behavior over time.

**Alternatives considered**
- Cleanup only on failure: insufficient visibility and weaker stability guarantees.
- No allocator tuning: leaves known fragmentation risk unmitigated.

## Resolved Clarifications

All clarifications from `spec.md` session 2026-02-26 are resolved and reflected in this research:
- dedicated warm lanes with capacity-aware fallback,
- degraded-mode routing behavior,
- bounded queue policy,
- timeout and queue depth thresholds.
