# Smoke Test Report

- Generated at: `2026-02-25T19:00:08.296955+00:00`
- Base URL: `http://34.73.173.191`
- API URL: `https://yapparov-emir-f--gooni-api.modal.run`
- API key provided: `no`

## Results

| Scenario | Status | Details | Screenshot |
|---|---|---|---|
| UI Load And Core Elements | PASSED | Main page and core controls are visible. | `C:\Users\yappa\OneDrive\MyFolder\myProjects\Веб приложение Gooni Gooni\qa_smoke\artifacts\20260225_185950Z\ui_load.png` |
| Model Selection And Modes | PASSED | Type/model/mode switching works. | `C:\Users\yappa\OneDrive\MyFolder\myProjects\Веб приложение Gooni Gooni\qa_smoke\artifacts\20260225_185950Z\model_switch.png` |
| Negative: Generate Without Prompt | PASSED | Generate button stays disabled without prompt. | `C:\Users\yappa\OneDrive\MyFolder\myProjects\Веб приложение Gooni Gooni\qa_smoke\artifacts\20260225_185950Z\negative_no_prompt.png` |
| Negative: Unsupported Upload Format | PASSED | Unsupported file is rejected as reference. | `C:\Users\yappa\OneDrive\MyFolder\myProjects\Веб приложение Gooni Gooni\qa_smoke\artifacts\20260225_185950Z\negative_bad_upload.png` |
| E2E: Flux Image Generate -> Download -> Gallery -> Delete | SKIPPED | Missing E2E_API_KEY: full-chain generation is blocked by 403. | - |
| Video Smoke: AniSora T2V Start | SKIPPED | Missing E2E_API_KEY: video smoke is blocked by 403. | - |
| Video Smoke: Phr00t WAN 2.2 Start | SKIPPED | Missing E2E_API_KEY: video smoke is blocked by 403. | - |

## Summary

- Passed: **4**
- Failed: **0**
- Skipped: **3**
