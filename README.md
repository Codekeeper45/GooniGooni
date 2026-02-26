
  # Веб приложение Gooni Gooni

  This is a code bundle for Веб приложение Gooni Gooni. The original project is available at https://www.figma.com/design/r3om1nsfq9oNFCmaZB32Gl/%D0%92%D0%B5%D0%B1-%D0%BF%D1%80%D0%B8%D0%BB%D0%BE%D0%B6%D0%B5%D0%BD%D0%B8%D0%B5-Gooni-Gooni.

  ## Running the code

  Run `npm i` to install the dependencies.

  Run `npm run dev` to start the development server.

## Backend Deploy

- Deploy backend: `modal deploy backend/app.py`
- Health check: `GET /health`

## Video VRAM Stability (A10G)

Current production policy for heavy video models (`anisora`, `phr00t`):

- Dedicated warm lane per model for fast model switching.
- Automatic degraded shared-worker fallback when dedicated lane is unavailable.
- Degraded admission limits:
  - queue depth <= 25
  - queue wait <= 30s
  - overflow response: `503` with code `queue_overloaded`

Fixed video parameters:

- `anisora`: `steps=8`
- `phr00t`: `steps=4`, `cfg_scale=1.0`

## Rollback Triggers

Rollback to previous backend revision if any of the following appears after deploy:

- sustained increase in `503 queue_overloaded` beyond expected load window;
- repeated fallback activation with rising queue timeout count;
- client incompatibility due to `422` fixed-parameter enforcement.

## Capacity Tradeoff Notes

- Keeping two dedicated warm lanes reduces switch latency but increases baseline GPU cost.
- Disabling warm lanes reduces baseline cost but increases cold-start latency and degraded-mode usage.
- Recommended baseline: keep warm lanes enabled for primary traffic hours; monitor diagnostics and adjust.
  
