# Changelog

## 2.0.0

- оставлена только генерация изображений Pony;
- удалены неподтверждённые Flux, AniSora и Phr00t integrations;
- удалены multi-account deployer, admin token storage и routing;
- SQLite task queue заменена на Modal FunctionCall;
- модель загружается один раз на GPU-контейнер через `@modal.enter`;
- ошибки startup, inference и timeout возвращаются UI;
- добавлены cancellation, polling retry и восстановление активной задачи;
- frontend и backend используют общий `pony_contract.json`;
- неизвестные параметры строго отклоняются;
- все оставшиеся UI controls подключены к payload и pipeline;
- gallery переведена на backend manifests и authenticated asset fetch;
- API key удалён из query string и frontend build args;
- зависимости ML закреплены совместимыми версиями.
