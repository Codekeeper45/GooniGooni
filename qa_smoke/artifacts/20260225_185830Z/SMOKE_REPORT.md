# Smoke Test Report

- Generated at: `2026-02-25T18:58:50.757466+00:00`
- Base URL: `http://34.73.173.191`
- API URL: `https://yapparov-emir-f--gooni-api.modal.run`
- API key provided: `no`

## Results

| Scenario | Status | Details | Screenshot |
|---|---|---|---|
| UI Load And Core Elements | PASSED | Главная страница и ключевые элементы доступны. | `C:\Users\yappa\OneDrive\MyFolder\myProjects\Веб приложение Gooni Gooni\qa_smoke\artifacts\20260225_185830Z\ui_load.png` |
| Model Selection And Modes | PASSED | Переключение типов/моделей/режимов работает. | `C:\Users\yappa\OneDrive\MyFolder\myProjects\Веб приложение Gooni Gooni\qa_smoke\artifacts\20260225_185830Z\model_switch.png` |
| Negative: Generate Without Prompt | PASSED | Без prompt кнопка Generate отключена. | `C:\Users\yappa\OneDrive\MyFolder\myProjects\Веб приложение Gooni Gooni\qa_smoke\artifacts\20260225_185830Z\negative_no_prompt.png` |
| Negative: Unsupported Upload Format | PASSED | Невалидный файл не принят как image reference. | `C:\Users\yappa\OneDrive\MyFolder\myProjects\Веб приложение Gooni Gooni\qa_smoke\artifacts\20260225_185830Z\negative_bad_upload.png` |
| E2E: Flux Image Generate -> Download -> Gallery -> Delete | SKIPPED | Нет E2E_API_KEY: full-chain генерация недоступна (backend отвечает 403). | - |
| Video Smoke: AniSora T2V Start | SKIPPED | Нет E2E_API_KEY: video smoke недоступен (backend отвечает 403). | - |
| Video Smoke: Phr00t WAN 2.2 Start | SKIPPED | Нет E2E_API_KEY: video smoke недоступен (backend отвечает 403). | - |

## Summary

- Passed: **4**
- Failed: **0**
- Skipped: **3**
