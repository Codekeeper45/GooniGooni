/**
 * control-panel/types.ts
 * ─────────────────────
 * All TypeScript types and interfaces shared across the control panel.
 */

export type GenerationType = "image" | "video";
export type VideoModel = "anisora" | "phr00t";
export type ImageModel = "pony" | "flux";
export type VideoMode = "t2v" | "i2v" | "first_last_frame" | "arbitrary_frame";
export type ImageMode = "txt2img" | "img2img";
export type GenerationStatus = "idle" | "generating" | "done" | "error";

export interface ArbitraryFrameItem {
  id: string;
  frameIndex: number;
  image: string;
}

export interface ControlPanelProps {
  // Type & Model
  generationType: GenerationType;
  setGenerationType: (t: GenerationType) => void;
  videoModel: VideoModel;
  setVideoModel: (m: VideoModel) => void;
  imageModel: ImageModel;
  setImageModel: (m: ImageModel) => void;

  // Mode
  videoMode: VideoMode;
  setVideoMode: (m: VideoMode) => void;
  imageMode: ImageMode;
  setImageMode: (m: ImageMode) => void;

  // Advanced Settings Control
  useAdvancedSettings: boolean;
  setUseAdvancedSettings: (u: boolean) => void;

  // Common params
  prompt: string;
  setPrompt: (p: string) => void;
  negativePrompt: string;
  setNegativePrompt: (p: string) => void;
  width: number;
  setWidth: (w: number) => void;
  height: number;
  setHeight: (h: number) => void;
  seed: number;
  setSeed: (s: number) => void;
  outputFormat: string;
  setOutputFormat: (f: string) => void;

  // Reference images (single)
  referenceImage: string | null;
  onImageUpload: (data: string) => void;
  onImageRemove: () => void;

  // Multiple frame references
  firstFrameImage: string | null;
  lastFrameImage: string | null;
  onFirstFrameUpload: (data: string) => void;
  onLastFrameUpload: (data: string) => void;
  onFirstFrameRemove: () => void;
  onLastFrameRemove: () => void;

  // Arbitrary frame items
  arbitraryFrames: ArbitraryFrameItem[];
  onArbitraryFrameAdd: (frameIndex: number, image: string) => void;
  onArbitraryFrameRemove: (id: string) => void;
  onArbitraryFrameUpdate: (id: string, frameIndex: number) => void;

  // Video params
  numFrames: number;
  setNumFrames: (n: number) => void;
  videoSteps: number;
  setVideoSteps: (s: number) => void;
  guidanceScale: number;
  setGuidanceScale: (g: number) => void;
  fps: number;
  setFps: (f: number) => void;
  motionScore: number;
  setMotionScore: (m: number) => void;
  cfgScaleVideo: number;
  setCfgScaleVideo: (c: number) => void;
  referenceStrength: number;
  setReferenceStrength: (r: number) => void;
  lightingVariant: "high_noise" | "low_noise";
  setLightingVariant: (l: "high_noise" | "low_noise") => void;
  denoisingStrength: number;
  setDenoisingStrength: (d: number) => void;

  // Image params
  imageSteps: number;
  setImageSteps: (s: number) => void;
  cfgScaleImage: number;
  setCfgScaleImage: (c: number) => void;
  clipSkip: number;
  setClipSkip: (c: number) => void;
  sampler: string;
  setSampler: (s: string) => void;
  imageGuidanceScale: number;
  setImageGuidanceScale: (g: number) => void;
  imgDenoisingStrength: number;
  setImgDenoisingStrength: (d: number) => void;

  // Actions
  onGenerate: () => void;
  status: GenerationStatus;
  estSeconds: number;
}
