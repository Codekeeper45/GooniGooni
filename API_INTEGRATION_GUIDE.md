# 🔌 API Integration Guide - MediaGen Universal WebUI

## 📋 Обзор

Это универсальный WebUI для генерации изображений и видео с поддержкой 4 моделей:

### Видео модели:
1. **Index-AniSora V3.2** (хентай видео)
2. **Phr00t WAN 2.2 Rapid-AllInOne NSFW** (порно видео)

### Изображения модели:
3. **Pony Diffusion V6 XL** (хентай изображения)
4. **Flux.1 [dev] nf4** (реализм порно изображения)

---

## 🎯 Структура Payload для API

### 1️⃣ ОБЩИЕ ПАРАМЕТРЫ (для всех моделей)

**Обязательные:**
```typescript
{
  prompt: string;          // Основной промпт
  width: number;           // Разрешение по ширине (512, 768, 1024)
  height: number;          // Разрешение по высоте (512, 768, 1024)
  seed: number;            // -1 = random, иначе конкретное число
}
```

**По умолчанию:**
```typescript
{
  negative_prompt: string;  // По умолчанию ""
  batch_size: number;       // По умолчанию 1
  output_format: string;    // "mp4" | "webm" | "gif" для видео
                            // "png" | "jpg" для изображений
}
```

---

## 🎬 2️⃣ ПАРАМЕТРЫ ДЛЯ ВИДЕО

### Применяется к:
- Index-AniSora V3.2
- Phr00t WAN 2.2 Rapid-AllInOne NSFW

### Обязательные параметры:

```typescript
{
  mode: "t2v" | "i2v" | "first_last_frame" | "arbitrary_frame";
  // "arbitrary_frame" доступен только для AniSora
  
  num_frames: number;       // Рекомендуем 81 (= 5 секунд при 16 fps)
  
  reference_image?: File;   // ОБЯЗАТЕЛЬНО при i2v, first_last_frame, arbitrary_frame
}
```

### Index-AniSora V3.2 - Defaults (НЕ МЕНЯЙ!):

```typescript
{
  steps: 8,                 // ⚠️ ФИКСИРОВАННОЕ ЗНАЧЕНИЕ
  guidance_scale: 1.0,      // CFG scale для AniSora
  fps: 16,                  // Frames per second
  motion_score: 3.0,        // Интенсивность движения (0-5)
}
```

### Phr00t WAN 2.2 Rapid - Defaults (НЕ МЕНЯЙ!):

```typescript
{
  steps: 4,                 // ⚠️ ФИКСИРОВАННОЕ ЗНАЧЕНИЕ (быстрая генерация)
  cfg_scale: 1.0,           // ⚠️ ОБЯЗАТЕЛЬНО 1.0!
  fps: 16,
}
```

### Опциональные параметры для видео:

```typescript
{
  reference_strength: number;     // 0.0-1.0, default 0.85-1.0
                                  // Только для i2v и first_last_frame
  
  first_frame_image?: File;       // Если mode = first_last_frame
  last_frame_image?: File;        // Если mode = first_last_frame
  
  lighting_variant?: "high_noise" | "low_noise";  // Только для Phr00t
                                                   // default: "low_noise"
  
  denoising_strength?: number;    // 0.0-1.0, для img2vid режимов
}
```

---

## 🖼️ 3️⃣ ПАРАМЕТРЫ ДЛЯ ИЗОБРАЖЕНИЙ

### Применяется к:
- Pony Diffusion V6 XL
- Flux.1 [dev] nf4

### Обязательные параметры:

```typescript
{
  mode: "txt2img" | "img2img";
  
  reference_image?: File;   // ОБЯЗАТЕЛЬНО при img2img
}
```

### Pony Diffusion V6 XL - Defaults:

```typescript
{
  steps: 30,
  cfg_scale: 6,
  clip_skip: 2,             // Специфично для Pony
  sampler: "Euler a",       // Альтернативы: "DPM++ 2M Karras", "DPM++ SDE Karras"
}
```

### Flux.1 [dev] nf4 - Defaults:

```typescript
{
  steps: 25,
  guidance_scale: 3.5,      // Это CFG для Flux
  sampler: "Euler",         // Альтернативы: "Euler a", "DPM++ 2M"
}
```

### Опциональные параметры для изображений:

```typescript
{
  denoising_strength?: number;  // 0.0-1.0, default 0.6-0.75
                                // Только для img2img режима
  
  vae?: string;                 // "Pony XL VAE" | "Flux VAE"
                                // Автоматически выбирается по модели
}
```

---

## 📤 Примеры Payload

### Пример 1: Генерация хентай видео (AniSora, t2v)

```json
{
  "model": "anisora",
  "type": "video",
  "mode": "t2v",
  "prompt": "anime girl with pink hair dancing in sakura garden, smooth motion, high quality",
  "negative_prompt": "blurry, low quality, distorted",
  "width": 512,
  "height": 512,
  "seed": -1,
  "num_frames": 81,
  "fps": 16,
  "steps": 8,
  "guidance_scale": 1.0,
  "motion_score": 3.0,
  "output_format": "mp4"
}
```

### Пример 2: Генерация порно видео из изображения (Phr00t, i2v)

```json
{
  "model": "phr00t",
  "type": "video",
  "mode": "i2v",
  "prompt": "slow camera zoom, add sensual motion and lighting effects",
  "negative_prompt": "static, no motion",
  "width": 768,
  "height": 768,
  "seed": 123456789,
  "num_frames": 81,
  "fps": 16,
  "steps": 4,
  "cfg_scale": 1.0,
  "reference_strength": 0.85,
  "lighting_variant": "low_noise",
  "denoising_strength": 0.7,
  "output_format": "mp4",
  "reference_image": "<base64_или_file>"
}
```

### Пример 3: Генерация хентай изображения (Pony, txt2img)

```json
{
  "model": "pony",
  "type": "image",
  "mode": "txt2img",
  "prompt": "1girl, blue eyes, long blonde hair, school uniform, detailed face, masterpiece, best quality",
  "negative_prompt": "low quality, worst quality, bad anatomy, bad hands",
  "width": 1024,
  "height": 1024,
  "seed": -1,
  "steps": 30,
  "cfg_scale": 6,
  "clip_skip": 2,
  "sampler": "DPM++ 2M Karras",
  "output_format": "png"
}
```

### Пример 4: Генерация реалистичного изображения (Flux, img2img)

```json
{
  "model": "flux",
  "type": "image",
  "mode": "img2img",
  "prompt": "enhance details, professional photography, cinematic lighting",
  "negative_prompt": "cartoon, anime, illustration",
  "width": 768,
  "height": 1024,
  "seed": 987654321,
  "steps": 25,
  "guidance_scale": 3.5,
  "sampler": "Euler",
  "denoising_strength": 0.65,
  "output_format": "jpg",
  "reference_image": "<base64_или_file>"
}
```

---

## 🔄 Как WebUI формирует Payload

### Код из `/src/app/components/MediaGenApp.tsx` (строки 115-161):

```typescript
const handleGenerate = async () => {
  // Validation
  if (!prompt.trim()) return;
  if (needsReferenceImage && !referenceImage) return;
  if (status === "generating") return;

  const resolvedSeed = seed === -1 
    ? Math.floor(Math.random() * 2147483647) 
    : seed;

  // Определяем модель
  const modelId = generationType === "video"
    ? (videoModel === "anisora" ? "anisora" : "phr00t")
    : (imageModel === "pony" ? "pony" : "flux");

  // Формируем payload
  const payload: GenerationPayload = {
    model: modelId,
    type: generationType,
    mode: generationType === "video" ? videoMode : imageMode,
    
    // Common params
    prompt,
    negative_prompt: negativePrompt,
    width,
    height,
    seed: resolvedSeed,
    batch_size: batchSize,
    output_format: outputFormat,
    
    // Video-specific
    ...(generationType === "video" && {
      num_frames: numFrames,
      fps,
      steps: videoSteps,
      ...(videoModel === "anisora" ? {
        guidance_scale: guidanceScale,
        motion_score: motionScore,
      } : {
        cfg_scale: cfgScaleVideo,
        lighting_variant: lightingVariant,
      }),
      ...(referenceImage && {
        reference_image: referenceImage,
        reference_strength: referenceStrength,
        denoising_strength: denoisingStrength,
      }),
    }),
    
    // Image-specific
    ...(generationType === "image" && {
      steps: imageSteps,
      sampler,
      ...(imageModel === "pony" ? {
        cfg_scale: cfgScaleImage,
        clip_skip: clipSkip,
      } : {
        guidance_scale: imageGuidanceScale,
      }),
      ...(imageMode === "img2img" && referenceImage && {
        reference_image: referenceImage,
        denoising_strength: imgDenoisingStrength,
      }),
    }),
  };

  // Отправка на API
  const response = await fetch(`${API_URL}/generate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${API_KEY}`,
    },
    body: JSON.stringify(payload),
  });
  
  const result = await response.json();
  // ... обработка результата
};
```

---

## 📥 Ожидаемый Response от API

### Успешный ответ:

```typescript
interface GenerationResponse {
  status: "success";
  url: string;              // URL сгенерированного файла
  seed: number;             // Использованный seed
  width: number;
  height: number;
  model: string;            // Название модели
  type: "image" | "video";
  
  // Опционально:
  metadata?: {
    inference_time: number;   // Время генерации в секундах
    gpu_time: number;
    num_frames?: number;      // Для видео
    fps?: number;             // Для видео
  };
}
```

### Ошибка:

```typescript
interface ErrorResponse {
  status: "error";
  error: string;            // Сообщение об ошибке
  code?: string;            // Код ошибки
  details?: any;            // Дополнительная информация
}
```

---

## 🔐 Настройка API Endpoints

### В файле `/src/app/components/MediaGenApp.tsx` замените:

```typescript
// Строки 30-45 — текущая заглушка
async function simulateGeneration(
  onProgress: (p: number) => void,
  type: GenerationType
): Promise<string> {
  // MOCK IMPLEMENTATION
  // ...
}
```

### На реальный API call:

```typescript
const API_BASE_URL = "https://your-inference-server.com/api";
const API_KEY = process.env.REACT_APP_API_KEY || "YOUR_API_KEY_HERE";

async function callGenerateAPI(
  payload: GenerationPayload,
  onProgress: (p: number) => void
): Promise<GenerationResponse> {
  
  // Start generation
  const response = await fetch(`${API_BASE_URL}/generate`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${API_KEY}`,
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || "Generation failed");
  }

  const data = await response.json();
  
  // If async generation with polling:
  if (data.job_id) {
    return await pollJobStatus(data.job_id, onProgress);
  }
  
  // If synchronous:
  return data;
}

async function pollJobStatus(
  jobId: string,
  onProgress: (p: number) => void
): Promise<GenerationResponse> {
  
  while (true) {
    const response = await fetch(`${API_BASE_URL}/status/${jobId}`, {
      headers: { "Authorization": `Bearer ${API_KEY}` },
    });
    
    const data = await response.json();
    
    if (data.progress !== undefined) {
      onProgress(data.progress);
    }
    
    if (data.status === "completed") {
      return data.result;
    }
    
    if (data.status === "failed") {
      throw new Error(data.error || "Generation failed");
    }
    
    // Poll every 500ms
    await new Promise(r => setTimeout(r, 500));
  }
}
```

---

## 🎛️ Соответствие UI параметров и API

| UI Parameter | API Field | Models | Description |
|--------------|-----------|---------|-------------|
| **Type Selection** | `type` | All | `"image"` или `"video"` |
| **Model** | `model` | All | `"anisora"`, `"phr00t"`, `"pony"`, `"flux"` |
| **Mode** | `mode` | All | Video: `t2v/i2v/first_last_frame/arbitrary_frame`<br>Image: `txt2img/img2img` |
| **Prompt** | `prompt` | All | Основной текстовый промпт |
| **Negative Prompt** | `negative_prompt` | All | Advanced settings |
| **Width** | `width` | All | 512, 768, 1024 |
| **Height** | `height` | All | 512, 768, 1024 |
| **Seed** | `seed` | All | -1 = random |
| **Reference Image** | `reference_image` | All (if mode requires) | Base64 или File |
| **Num Frames** | `num_frames` | Video | 16-161 кадров |
| **FPS** | `fps` | Video | 8, 16, 24 |
| **Motion Score** | `motion_score` | AniSora | 0.0-5.0 |
| **Lighting Variant** | `lighting_variant` | Phr00t | `low_noise` / `high_noise` |
| **Reference Strength** | `reference_strength` | Video i2v/first_last | 0.0-1.0 |
| **Steps** (Video) | `steps` | Video | AniSora: 8, Phr00t: 4 |
| **Guidance Scale** (Video) | `guidance_scale` | AniSora | CFG для видео |
| **CFG Scale** (Video) | `cfg_scale` | Phr00t | Должен быть 1.0 |
| **Steps** (Image) | `steps` | Image | Pony: 30, Flux: 25 |
| **CFG Scale** (Image) | `cfg_scale` | Pony | 1-20 |
| **Guidance Scale** (Image) | `guidance_scale` | Flux | 1-10 |
| **Sampler** | `sampler` | Image | Euler a, DPM++, и т.д. |
| **Clip Skip** | `clip_skip` | Pony | 1-4 |
| **Denoising Strength** | `denoising_strength` | Video/Image (if i2v/img2img) | 0.0-1.0 |

---

## ⚙️ Автоматическое применение Defaults

WebUI автоматически устанавливает правильные defaults при переключении модели:

```typescript
// Из MediaGenApp.tsx, строки 144-165
useEffect(() => {
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
  } else {
    if (imageModel === "pony") {
      setImageSteps(30);
      setCfgScaleImage(6);
      setClipSkip(2);
      setSampler("Euler a");
    } else if (imageModel === "flux") {
      setImageSteps(25);
      setImageGuidanceScale(3.5);
      setSampler("Euler");
    }
  }
}, [generationType, videoModel, imageModel]);
```

---

## 📊 Расчёт времени генерации

```typescript
// Из MediaGenApp.tsx, строки 48-59
function calcEstSeconds(
  type: GenerationType,
  videoFrames?: number,
  imageSteps?: number
): number {
  if (type === "video") {
    // num_frames / fps * complexity_factor
    const frames = videoFrames || 81;
    return Math.round((frames / 16) * 3.5);
  } else {
    // steps * step_time
    const steps = imageSteps || 30;
    return Math.round(steps * 0.4);
  }
}
```

**Примеры:**
- Video 81 frames @ 16fps → ~18 секунд
- Video 161 frames @ 16fps → ~35 секунд
- Image 30 steps → ~12 секунд
- Image 50 steps → ~20 секунд

---

## 🧪 Тестирование

### 1. Проверка обязательных параметров

```bash
# Должно вернуть ошибку 400
curl -X POST "${API_URL}/generate" \
  -H "Content-Type: application/json" \
  -d '{}'

# Должно работать
curl -X POST "${API_URL}/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "video",
    "model": "anisora",
    "mode": "t2v",
    "prompt": "test",
    "width": 512,
    "height": 512,
    "seed": -1,
    "num_frames": 81
  }'
```

### 2. Проверка reference_image requirement

```bash
# Должно вернуть ошибку (нет reference_image для i2v)
curl -X POST "${API_URL}/generate" \
  -H "Content-Type: application/json" \
  -d '{
    "type": "video",
    "model": "anisora",
    "mode": "i2v",
    "prompt": "test",
    "width": 512,
    "height": 512,
    "seed": -1,
    "num_frames": 81
  }'
```

---

## 📝 TypeScript Типы

```typescript
// Полная структура типов для интеграции

type GenerationType = "image" | "video";
type VideoModel = "anisora" | "phr00t";
type ImageModel = "pony" | "flux";
type VideoMode = "t2v" | "i2v" | "first_last_frame" | "arbitrary_frame";
type ImageMode = "txt2img" | "img2img";
type Sampler = "Euler" | "Euler a" | "DPM++ 2M Karras" | "DPM++ SDE Karras" | "DPM++ 2M";
type LightingVariant = "high_noise" | "low_noise";
type OutputFormat = "mp4" | "webm" | "gif" | "png" | "jpg";

interface GenerationPayload {
  // Type & Model
  type: GenerationType;
  model: VideoModel | ImageModel;
  mode: VideoMode | ImageMode;
  
  // Common
  prompt: string;
  negative_prompt?: string;
  width: number;
  height: number;
  seed: number;
  batch_size?: number;
  output_format?: OutputFormat;
  
  // Reference image (conditional)
  reference_image?: string; // base64 or URL
  
  // Video-specific
  num_frames?: number;
  fps?: number;
  steps?: number;
  guidance_scale?: number;      // AniSora
  cfg_scale?: number;           // Phr00t
  motion_score?: number;        // AniSora
  lighting_variant?: LightingVariant; // Phr00t
  reference_strength?: number;
  denoising_strength?: number;
  first_frame_image?: string;
  last_frame_image?: string;
  
  // Image-specific
  sampler?: Sampler;
  clip_skip?: number;           // Pony only
}

interface GenerationResponse {
  status: "success" | "error";
  url?: string;
  seed?: number;
  width?: number;
  height?: number;
  model?: string;
  type?: GenerationType;
  error?: string;
  code?: string;
  metadata?: {
    inference_time?: number;
    gpu_time?: number;
    num_frames?: number;
    fps?: number;
  };
}
```

---

## 🚀 Production Checklist

- [ ] Установить `API_BASE_URL` и `API_KEY` в environment variables
- [ ] Реализовать proper error handling для всех API calls
- [ ] Добавить retry logic для network failures
- [ ] Implement rate limiting на клиенте
- [ ] Добавить validation перед отправкой payload
- [ ] Настроить CORS на сервере
- [ ] Implement proper file upload для reference_image
- [ ] Добавить progress polling для длинных генераций
- [ ] Implement cancellation для generation jobs
- [ ] Добавить logging и analytics
- [ ] Setup sentry или error tracking
- [ ] Implement proper authentication flow
- [ ] Add GPU credits/billing system integration

---

**Version:** 1.0  
**Last Updated:** 2026-02-24  
**Application:** MediaGen Universal WebUI

---

## Session Auth Update (2026-02)

- Frontend больше не использует `localStorage.mg_api_key` и не отправляет постоянный `X-API-Key`.
- Для пользовательских запросов используется cookie-сессия:
  - `POST /auth/session` -> выдаёт `gg_session` (HttpOnly cookie, TTL 24h).
  - `GET /auth/session` -> проверка валидности session.
- Пользовательские endpoints требуют generation session (или server-to-server `X-API-Key`):
  - `POST /generate`
  - `GET /status/{task_id}`
  - `GET /results/{task_id}`
  - `GET /preview/{task_id}`
  - `GET /gallery`
  - `DELETE /gallery/{task_id}`
- Admin авторизация работает через cookie-сессию:
  - `POST /admin/session` (header `x-admin-key` только для входа)
  - `GET /admin/session`
  - `DELETE /admin/session`
- Статусы аккаунтов server-authoritative: `pending|checking|ready|failed|disabled`.
- `ready` выставляется только после успешного health-check; переход `failed -> ready` без `checking` запрещён.

---

## VRAM Stability Contract Update (2026-02-26)

For video models, the backend now enforces strict fixed parameters before enqueue:

- `anisora`: `steps` must be `8`
- `phr00t`: `steps` must be `4` and `cfg_scale` must be `1.0`

If request payload violates these rules, backend returns `422`.

When dedicated video lanes are unavailable, backend routes requests to degraded shared-worker mode with bounded admission:

- max queue depth: `25`
- max queue wait: `30s`

If limits are exceeded, backend returns:

```json
{
  "detail": {
    "code": "queue_overloaded",
    "detail": "Generation queue is overloaded ...",
    "user_action": "Retry later."
  }
}
```

Client-side handling recommendation:

1. Show validation guidance on `422`.
2. Show retry/backoff UX on `503` with `code=queue_overloaded`.
