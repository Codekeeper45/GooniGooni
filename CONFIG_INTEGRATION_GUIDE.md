# 🔧 Интеграция inference_settings.json

## 📋 Обзор

`inference_settings.json` — централизованная конфигурация всех моделей и параметров для MediaGen WebUI. Позволяет динамически рендерить UI на основе выбранной модели и режима.

---

## 🎯 Преимущества schema-driven подхода

✅ **Единый источник истины** — все параметры в одном месте  
✅ **Динамический UI** — автоматическое показ/скрытие полей  
✅ **Валидация** — встроенные правила и ограничения  
✅ **Легко добавлять модели** — просто добавь JSON блок  
✅ **API payload** — автоматическая генерация запроса  
✅ **Type safety** — TypeScript типы из схемы  

---

## 📁 Структура JSON

```json
{
  "version": "2026-02-24",
  "common": { /* Общие параметры для всех моделей */ },
  "image_models": { /* Модели изображений */ },
  "video_models": { /* Модели видео */ },
  "ui_logic": { /* Правила рендеринга UI */ },
  "presets": { /* Пресеты для быстрого доступа */ }
}
```

### Common Parameters (Общие)

Применяются ко всем моделям:
- `prompt` — основной промпт
- `negative_prompt` — негативный промпт
- `width`, `height` — разрешение
- `seed` — зерно случайности
- `output_format` — формат выходного файла

### Model Structure (Структура модели)

Каждая модель содержит:

```json
{
  "id": "pony",                    // Внутренний ID
  "name": "Pony V6 XL",           // Отображаемое имя
  "type": "image",                // image | video
  "category": "hentai",           // hentai | realistic
  "description": "...",           // Описание
  
  "modes": {                      // Доступные режимы
    "txt2img": {
      "label": "Text to Image",
      "requires_reference": false
    }
  },
  
  "parameters": {                 // Параметры модели
    "steps": {
      "type": "int",
      "default": 30,
      "min": 20,
      "max": 60,
      "label": "Steps",
      "advanced": true
    }
  },
  
  "fixed_parameters": {           // Фиксированные значения
    "steps": {
      "value": 8,
      "locked": true,
      "warning": "⚠️ Fixed"
    }
  }
}
```

---

## 🚀 Использование ConfigManager

### 1. Импорт

```typescript
import { configManager, ModelId } from "./utils/configManager";
```

### 2. Получение модели

```typescript
const model = configManager.getModel("pony");
console.log(model.name); // "Pony V6 XL"
console.log(model.type); // "image"
```

### 3. Получение режимов

```typescript
const modes = configManager.getModesForModel("anisora");
// {
//   "t2v": { label: "Text2Video", ... },
//   "i2v": { label: "Image2Video", ... },
//   ...
// }
```

### 4. Получение параметров

```typescript
const params = configManager.getParameters("pony");
// { steps: {...}, cfg_scale: {...}, sampler: {...}, ... }

// Только видимые параметры для режима
const visible = configManager.getVisibleParameters(
  "anisora",
  "i2v",
  false  // advanced = false
);
```

### 5. Валидация

```typescript
const values = {
  prompt: "Test prompt",
  steps: 30,
  width: 512,
  height: 512,
  seed: -1
};

const validation = configManager.validateValues("pony", "txt2img", values);
if (!validation.valid) {
  console.error(validation.errors);
}
```

### 6. Генерация API payload

```typescript
const payload = configManager.buildPayload("pony", "txt2img", {
  prompt: "anime girl",
  width: 1024,
  height: 1024,
  seed: 123456,
  steps: 30,
  cfg_scale: 6
});

// Результат:
// {
//   model: "pony",
//   type: "image",
//   mode: "txt2img",
//   prompt: "anime girl",
//   width: 1024,
//   height: 1024,
//   seed: 123456,
//   steps: 30,
//   cfg_scale: 6
// }
```

### 7. Расчёт времени

```typescript
const estSeconds = configManager.calculateEstimate("anisora", {
  num_frames: 81,
  fps: 16
});
// ~18 секунд
```

---

## 🎨 Интеграция в ControlPanel

### Шаг 1: Динамический рендеринг режимов

```typescript
function ModeSelector({ modelId, mode, onChange }: Props) {
  const modes = configManager.getModesForModel(modelId);
  
  return (
    <ToggleGroup
      options={Object.entries(modes).map(([key, config]) => ({
        value: key,
        label: config.label
      }))}
      value={mode}
      onChange={onChange}
    />
  );
}
```

### Шаг 2: Динамический рендеринг параметров

```typescript
function ParameterField({ modelId, paramKey, mode, value, onChange }: Props) {
  const param = configManager.getParameters(modelId)[paramKey];
  
  if (!param) return null;
  
  // Check visibility
  if (param.visible_if) {
    const visible = configManager
      .getVisibleParameters(modelId, mode, true)
      .hasOwnProperty(paramKey);
    if (!visible) return null;
  }
  
  // Render based on type
  switch (param.type) {
    case "int":
    case "float":
      return (
        <div>
          <ParamLabel>{param.label}</ParamLabel>
          <RangeSlider
            min={param.min}
            max={param.max}
            step={param.step}
            value={value}
            onChange={onChange}
          />
        </div>
      );
      
    case "enum":
      return (
        <div>
          <ParamLabel>{param.label}</ParamLabel>
          <ToggleGroup
            options={param.options.map(opt => ({ value: opt, label: opt }))}
            value={value}
            onChange={onChange}
          />
        </div>
      );
      
    case "image_upload":
      return (
        <div>
          <ParamLabel>{param.label}</ParamLabel>
          <ImageUploader
            value={value}
            onChange={onChange}
            accepts={param.accepts}
          />
        </div>
      );
      
    default:
      return null;
  }
}
```

### Шаг 3: Reference Image условный рендеринг

```typescript
function ReferenceImageField({ modelId, mode }: Props) {
  const modes = configManager.getModesForModel(modelId);
  const modeConfig = modes[mode];
  
  if (!modeConfig.requires_reference) {
    return null;
  }
  
  return (
    <div>
      <ParamLabel>Reference Image</ParamLabel>
      <ImageUploader />
    </div>
  );
}
```

### Шаг 4: Advanced Settings автоматически

```typescript
function AdvancedSettings({ modelId, mode, showAdvanced }: Props) {
  if (!showAdvanced) return null;
  
  const allParams = configManager.getParameters(modelId);
  const advancedParams = Object.entries(allParams)
    .filter(([_, param]) => param.advanced);
  
  return (
    <motion.div>
      {advancedParams.map(([key, param]) => (
        <ParameterField
          key={key}
          modelId={modelId}
          paramKey={key}
          mode={mode}
        />
      ))}
    </motion.div>
  );
}
```

---

## 🔄 Workflow при смене модели/режима

### 1. Пользователь выбирает модель

```typescript
const handleModelChange = (newModelId: ModelId) => {
  // 1. Получить конфиг модели
  const model = configManager.getModel(newModelId);
  
  // 2. Установить default mode
  const defaultMode = configManager.getDefaultMode(newModelId);
  setMode(defaultMode);
  
  // 3. Загрузить defaults для параметров
  const params = configManager.getParameters(newModelId);
  Object.entries(params).forEach(([key, param]) => {
    if (param.default !== undefined) {
      setValue(key, param.default);
    }
  });
  
  // 4. Применить fixed parameters
  const fixedParams = configManager.getFixedParameters(newModelId);
  Object.entries(fixedParams).forEach(([key, config]) => {
    setValue(key, config.value);
  });
  
  // 5. Re-render UI
  setModelId(newModelId);
};
```

### 2. Пользователь меняет режим

```typescript
const handleModeChange = (newMode: string) => {
  // 1. Проверить requires_reference
  const modes = configManager.getModesForModel(modelId);
  const modeConfig = modes[newMode];
  
  if (modeConfig.requires_reference && !referenceImage) {
    // Показать placeholder для загрузки
  }
  
  // 2. Обновить видимость параметров
  const visible = configManager.getVisibleParameters(
    modelId,
    newMode,
    showAdvanced
  );
  
  // 3. Re-render UI
  setMode(newMode);
};
```

### 3. Перед генерацией

```typescript
const handleGenerate = async () => {
  // 1. Валидация
  const validation = configManager.validateValues(
    modelId,
    mode,
    currentValues
  );
  
  if (!validation.valid) {
    alert(validation.errors.join("\n"));
    return;
  }
  
  // 2. Построить payload
  const payload = configManager.buildPayload(
    modelId,
    mode,
    currentValues
  );
  
  // 3. Отправить на API
  const response = await fetch("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  
  // ...
};
```

---

## 📝 Примеры конфигурации

### Пример 1: Добавить новую модель

```json
{
  "video_models": {
    "NewModel_v1": {
      "id": "newmodel",
      "name": "New Model v1",
      "type": "video",
      "category": "realistic",
      "description": "New awesome model",
      
      "modes": {
        "t2v": {
          "label": "Text2Video",
          "requires_reference": false
        }
      },
      "default_mode": "t2v",
      
      "parameters": {
        "custom_param": {
          "type": "float",
          "default": 1.5,
          "min": 0.0,
          "max": 5.0,
          "step": 0.1,
          "label": "Custom Parameter",
          "advanced": true
        }
      }
    }
  }
}
```

### Пример 2: Conditional visibility

```json
{
  "parameters": {
    "reference_strength": {
      "type": "float",
      "default": 0.85,
      "visible_if": "mode == 'i2v' || mode == 'arbitrary_frame'",
      "label": "Reference Strength",
      "advanced": true
    }
  }
}
```

### Пример 3: Multiple reference images

```json
{
  "modes": {
    "first_last_frame": {
      "label": "First+Last",
      "requires_reference": true,
      "requires_multiple": true
    }
  },
  "parameters": {
    "first_frame_image": {
      "type": "image_upload",
      "required_if": "mode == 'first_last_frame'",
      "visible_if": "mode == 'first_last_frame'",
      "label": "First Frame"
    },
    "last_frame_image": {
      "type": "image_upload",
      "required_if": "mode == 'first_last_frame'",
      "visible_if": "mode == 'first_last_frame'",
      "label": "Last Frame"
    }
  }
}
```

---

## 🧪 Тестирование

### Unit тесты для ConfigManager

```typescript
describe("ConfigManager", () => {
  it("should get model by id", () => {
    const model = configManager.getModel("pony");
    expect(model?.name).toBe("Pony Diffusion V6 XL");
  });
  
  it("should filter visible parameters", () => {
    const visible = configManager.getVisibleParameters(
      "anisora",
      "t2v",
      false
    );
    expect(visible).not.toHaveProperty("reference_image");
  });
  
  it("should validate required fields", () => {
    const validation = configManager.validateValues(
      "pony",
      "txt2img",
      { prompt: "" }  // Missing required
    );
    expect(validation.valid).toBe(false);
  });
  
  it("should build correct payload", () => {
    const payload = configManager.buildPayload("pony", "txt2img", {
      prompt: "test",
      steps: 30
    });
    expect(payload.model).toBe("pony");
    expect(payload.type).toBe("image");
  });
});
```

---

## 🔧 Миграция существующего кода

### До (hardcoded):

```typescript
if (generationType === "video") {
  if (videoModel === "anisora") {
    setVideoSteps(8);
    setGuidanceScale(1.0);
    setFps(16);
    setMotionScore(3.0);
  } else if (videoModel === "phr00t") {
    setVideoSteps(4);
    setCfgScaleVideo(1.0);
    setFps(16);
  }
}
```

### После (config-driven):

```typescript
const handleModelChange = (modelId: ModelId) => {
  const params = configManager.getParameters(modelId);
  const fixedParams = configManager.getFixedParameters(modelId);
  
  // Auto-set defaults
  Object.entries(params).forEach(([key, param]) => {
    setValue(key, param.default);
  });
  
  // Auto-set fixed values
  Object.entries(fixedParams).forEach(([key, config]) => {
    setValue(key, config.value);
  });
};
```

---

## 📊 Визуализация flow

```
User selects model
       ↓
configManager.getModel(id)
       ↓
Load defaults from config
       ↓
Render mode selector
       ↓
User selects mode
       ↓
configManager.getVisibleParameters(id, mode)
       ↓
Show/hide fields dynamically
       ↓
User fills values
       ↓
configManager.validateValues(id, mode, values)
       ↓
configManager.buildPayload(id, mode, values)
       ↓
Send to API
```

---

## 🎯 Следующие шаги

1. ✅ Создан `inference_settings.json`
2. ✅ Создан `configManager.ts`
3. 🔄 Рефакторинг `ControlPanel.tsx` для использования config
4. 🔄 Рефакторинг `MediaGenApp.tsx` для использования config
5. 🔄 Добавить unit тесты
6. 🔄 Обновить документацию

---

## 💡 Советы

1. **Не дублируй логику** — используй configManager для всего
2. **Валидация на клиенте** — используй `validateValues()` перед отправкой
3. **Type safety** — экспортируй типы из configManager
4. **Extend легко** — просто добавь новую модель в JSON
5. **Тестируй** — config меняется редко, но критичен для работы

---

**Версия:** 1.0  
**Дата:** 2026-02-24  
**Файлы:** `inference_settings.json`, `utils/configManager.ts`
