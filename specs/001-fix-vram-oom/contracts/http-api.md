# HTTP API Contract: VRAM OOM Stability for Video Pipelines

## Scope

This contract documents API behavior changes required by feature `001-fix-vram-oom`.
Primary affected surface: `POST /generate` request validation and overload responses.

## Endpoints

### `POST /generate`

**Auth**: unchanged (generation session/API-key precedence remains as-is).

**Request**: existing generation payload.

**Behavior additions (video only)**:
- For model `anisora`, `steps` MUST equal `8`.
- For model `phr00t`, `steps` MUST equal `4` and `cfg` MUST equal `1.0`.
- When dedicated lane is unavailable, request MAY route to degraded shared-worker mode.
- In degraded mode, queue policy applies: max depth `25`, max wait `30s`.

**Success response**:
- `202 { "task_id": "...", "status": "pending" }` (unchanged status semantics, explicit pending)

**Validation error response**:
- `422` for fixed-parameter violations (new strictness)
- Example machine-readable shape:
```json
{
  "detail": {
    "code": "validation_error",
    "detail": "Phr00t requires steps=4 and cfg=1.0",
    "user_action": "Use supported fixed values and retry"
  }
}
```

**Overload response (new)**:
- `503` when degraded queue limit is exceeded by depth or wait timeout.
- Required code: `queue_overloaded`
- Example:
```json
{
  "detail": {
    "code": "queue_overloaded",
    "detail": "Generation queue is overloaded",
    "user_action": "Retry later"
  }
}
```

**Deterministic routing order**:
1. Dedicated warm lane by model (`anisora`/`phr00t`)
2. Degraded shared-worker mode (single active heavy pipeline) if queue admission passes
3. `503 queue_overloaded` if degraded queue depth/wait limits are exceeded

## Backward Compatibility

- Compatible for clients already using model-fixed values.
- Breaking for clients that send custom video `steps/cfg` for AniSora/Phr00t.
- No method/path additions or removals.

## Contract-to-Code Mapping

### Backend
- `backend/schemas.py`: model-specific fixed parameter validation.
- `backend/app.py`: dedicated lane dispatch, degraded queue admission, `503 queue_overloaded`.
- `backend/config.py`: lane/threshold config constants if centralized.
- `backend/storage.py`: optional persistence/metrics hooks for queue/fallback diagnostics.

### Frontend
- `src/inference_settings.json`: fixed video parameter constraints for AniSora/Phr00t.
- `src/app/utils/configManager.ts`: payload/value parity with fixed constraints.
- `src/app/components/ControlPanel.tsx`: UI reflects fixed behavior.
- `src/app/components/MediaGenApp.tsx`: handles deterministic `422` and `503 queue_overloaded` errors.

## Operational Compatibility

- Existing status/result/preview endpoints remain unchanged.
- Existing auth/session/CORS behavior remains unchanged for this feature.
