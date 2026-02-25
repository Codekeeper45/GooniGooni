# 🎬 Multi-Frame Update - Enhanced Video Modes

## ✅ Что добавлено

### 1. **First+Last Frame Mode — Двойная загрузка**
Теперь режим First+Last поддерживает загрузку двух отдельных изображений для первого и последнего кадра.

**До:**
- ❌ Только один reference image
- ❌ Неясно какой кадр (first или last)

**После:**
- ✅ Отдельный загрузчик для First Frame
- ✅ Отдельный загрузчик для Last Frame
- ✅ Визуально понятно какой кадр какой
- ✅ Автоматическая очистка при смене режима

**UI:**
```
┌─────────────────────────────┐
│ First Frame                 │
│ [Image uploader]            │
│                             │
│ Last Frame                  │
│ [Image uploader]            │
└─────────────────────────────┘
```

---

### 2. **Arbitrary Frame Mode — Multi-Keyframe Support**
Переработан режим Arbitrary Frame для поддержки **множественных ключевых кадров** (spatiotemporal guidance).

**Что изменилось:**
- ❌ Старое: Один reference image на один frame_index
- ✅ Новое: Неограниченное количество keyframes в любых позициях

**Возможности:**
- ✅ Добавление множественных референсных изображений
- ✅ Указание позиции каждого keyframe (0-N)
- ✅ Удаление и редактирование keyframes
- ✅ Автоинкремент frame_index при добавлении
- ✅ Визуальный превью всех keyframes

**UI:**
```
┌────────────────────────────────────────┐
│ Arbitrary Frames (Multi-Keyframe)     │
├────────────────────────────────────────┤
│ ┌─ Keyframe 1 ─────────────────────┐  │
│ │ Frame: [0]              [Remove] │  │
│ │ [Front view preview]             │  │
│ └──────────────────────────────────┘  │
│                                        │
│ ┌─ Keyframe 2 ─────────────────────┐  │
│ │ Frame: [40]             [Remove] │  │
│ │ [Side view preview]              │  │
│ └──────────────────────────────────┘  │
│                                        │
│ ┌─ Add New Keyframe ───────────────┐  │
│ │ Frame Index: [60]                │  │
│ │ [+ Add Keyframe Image]           │  │
│ └──────────────────────────────────┘  │
│                                        │
│ 💡 Model interpolates between all     │
│    keyframes automatically            │
└────────────────────────────────────────┘
```

---

## 🔧 Технические изменения

### 1. Обновлённые типы (ControlPanel.tsx)

```typescript
export interface ArbitraryFrameItem {
  id: string;
  frameIndex: number;
  image: string;
}

export interface ControlPanelProps {
  // ... existing props
  
  // First+Last frames
  firstFrameImage: string | null;
  lastFrameImage: string | null;
  onFirstFrameUpload: (data: string) => void;
  onLastFrameUpload: (data: string) => void;
  onFirstFrameRemove: () => void;
  onLastFrameRemove: () => void;
  
  // Arbitrary frames
  arbitraryFrames: ArbitraryFrameItem[];
  onArbitraryFrameAdd: (frameIndex: number, image: string) => void;
  onArbitraryFrameRemove: (id: string) => void;
  onArbitraryFrameUpdate: (id: string, frameIndex: number) => void;
}
```

### 2. Новый ImageUploader компонент

Переиспользуемый компонент для загрузки изображений:
- Drag & drop support
- Replace/Remove buttons
- Preview with overlay
- Disabled state
- Customizable label

```typescript
<ImageUploader
  image={firstFrameImage}
  onUpload={onFirstFrameUpload}
  onRemove={onFirstFrameRemove}
  fileRef={firstFrameRef}
  label="First Frame"
  disabled={isGenerating}
/>
```

### 3. Автоматическая очистка при смене режима

```typescript
const handleVideoModeChange = (mode: VideoMode) => {
  setVideoMode(mode);
  // Clear all reference images
  setReferenceImage(null);
  setFirstFrameImage(null);
  setLastFrameImage(null);
  setArbitraryFrames([]);
};
```

### 4. Валидация

```typescript
const needsFirstLastFrames = 
  generationType === "video" && videoMode === "first_last_frame";

const needsArbitraryFrames = 
  generationType === "video" && videoMode === "arbitrary_frame";

const canGenerate =
  !isGenerating && 
  prompt.trim().length > 0 && 
  (!needsReferenceImage || !!referenceImage) &&
  (!needsFirstLastFrames || (firstFrameImage && lastFrameImage)) &&
  (!needsArbitraryFrames || arbitraryFrames.length > 0);
```

---

## 📊 Обновлённая конфигурация

### inference_settings.json

```json
{
  "modes": {
    "arbitrary_frame": {
      "label": "Arbitrary",
      "description": "Multi-keyframe control with spatiotemporal guidance",
      "requires_reference": true,
      "requires_multiple": true,
      "supports_keyframes": true
    }
  },
  
  "parameters": {
    "arbitrary_frames": {
      "type": "keyframe_array",
      "default": [],
      "label": "Keyframe References",
      "advanced": false,
      "visible_if": "mode == arbitrary_frame",
      "help": "Multiple reference images at different frame positions",
      "item_schema": {
        "frame_index": {
          "type": "int",
          "min": 0,
          "max": 160,
          "help": "Frame position (0-N)"
        },
        "image": {
          "type": "image_upload",
          "help": "Reference image for this frame"
        },
        "strength": {
          "type": "float",
          "default": 0.85,
          "min": 0.1,
          "max": 1.0,
          "help": "Influence strength"
        }
      }
    }
  }
}
```

---

## 🎯 API Payload Examples

### First+Last Frame Mode

```json
{
  "model": "anisora",
  "mode": "first_last_frame",
  "prompt": "Smooth transition between poses, maintain style",
  "first_frame_image": "data:image/png;base64,...",
  "last_frame_image": "data:image/png;base64,...",
  "first_strength": 1.0,
  "last_strength": 1.0,
  "num_frames": 81,
  "fps": 16,
  "width": 1024,
  "height": 1024,
  "seed": 123456
}
```

### Arbitrary Frame Mode (Multiple Keyframes)

```json
{
  "model": "anisora",
  "mode": "arbitrary_frame",
  "prompt": "360 degree rotation, smooth interpolation between all keyframes",
  "arbitrary_frames": [
    {
      "frame_index": 0,
      "image": "data:image/png;base64,...",
      "strength": 1.0
    },
    {
      "frame_index": 27,
      "image": "data:image/png;base64,...",
      "strength": 0.85
    },
    {
      "frame_index": 54,
      "image": "data:image/png;base64,...",
      "strength": 0.85
    },
    {
      "frame_index": 81,
      "image": "data:image/png;base64,...",
      "strength": 1.0
    }
  ],
  "num_frames": 81,
  "fps": 16,
  "steps": 8,
  "guidance_scale": 1.0,
  "width": 1024,
  "height": 1024,
  "seed": 123456
}
```

---

## 🎨 Use Cases

### 1. 360° Product Rotation (Arbitrary)
```
Keyframes:
- Frame 0: Front (1.0 strength)
- Frame 27: 45° right (0.85)
- Frame 54: Side 90° (0.85)
- Frame 81: Back 180° (1.0)

Result: Smooth turnaround animation
```

### 2. Character Pose Transition (First+Last)
```
First Frame (0): Standing
Last Frame (80): Sitting

Result: Natural sitting motion
```

### 3. Dance Choreography (Arbitrary)
```
Keyframes at: 0, 16, 32, 48, 64, 80
Each = different dance pose

Result: Fluid dance with all key poses hit perfectly
```

### 4. Facial Expressions (Arbitrary)
```
Keyframes:
- Frame 0: Neutral
- Frame 27: Smiling
- Frame 54: Surprised
- Frame 81: Laughing

Result: Smooth expression changes
```

---

## 📝 Обновлённая документация

### VIDEO_MODES_GUIDE.md
- ✅ Расширено описание Arbitrary Frame
- ✅ Добавлены примеры multiple keyframes
- ✅ Новые use cases (5 примеров)
- ✅ API payload с массивом keyframes
- ✅ Визуализация spatiotemporal guidance

---

## 🚀 Как использовать

### First+Last Frame

1. Выбери режим **First+Last**
2. Загрузи изображение для первого кадра
3. Загрузи изображение для последнего кадра
4. Напиши промпт для перехода
5. Generate!

**Промпт пример:**
```
"Smooth transition maintaining character identity and lighting"
```

### Arbitrary Frame (Multiple Keyframes)

1. Выбери режим **Arbitrary**
2. Установи Frame Index для первого keyframe (например, 0)
3. Загрузи изображение для этого кадра
4. Повтори для других keyframes (27, 54, 80, etc.)
5. Напиши промпт описывающий общее движение
6. Generate!

**Промпт пример:**
```
"360 degree smooth rotation around center axis, maintain consistent lighting and style, fluid interpolation between all keyframes"
```

**Рекомендации:**
- Используй 3-5 keyframes для лучшего контроля
- Распределяй keyframes равномерно (0, 27, 54, 81)
- Первый и последний keyframe — strength 1.0
- Промежуточные — strength 0.85

---

## ⚡ Преимущества

### First+Last
- ✅ Визуально понятно какой кадр какой
- ✅ Не нужно помнить порядок загрузки
- ✅ Отдельные превью для каждого кадра
- ✅ Легко заменить один из кадров

### Arbitrary
- ✅ Полный контроль над анимацией
- ✅ Идеальная консистентность персонажа
- ✅ Точное попадание в ключевые позы
- ✅ Неограниченное количество keyframes
- ✅ Легко добавить/удалить/редактировать
- ✅ Автоинкремент frame_index

---

## 🔮 Будущие улучшения

- [ ] Strength slider для каждого keyframe в UI
- [ ] Timeline визуализация всех keyframes
- [ ] Drag & drop для изменения order
- [ ] Presets для типичных animations
- [ ] Batch import keyframes
- [ ] Export/Import keyframe configuration
- [ ] Video preview с keyframe markers

---

**Версия:** 1.2  
**Дата:** 2026-02-24  
**Статус:** ✅ Ready to Use
