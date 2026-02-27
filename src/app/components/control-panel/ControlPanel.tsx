/**
 * control-panel/ControlPanel.tsx
 * ───────────────────────────────
 * Orchestrator component — composes section modules, holds only
 * local UI state (promptFocused, showAdvanced) that doesn't belong
 * in the global context.
 *
 * All generation state lives in GenerationContext (MediaGenApp passes it down).
 */

import { useState, useRef, useCallback } from "react";
import { configManager } from "../../utils/configManager";

import { TypeModelSection   } from "./sections/TypeModelSection";
import { QuickPresetsSection } from "./sections/QuickPresetsSection";
import { PromptSection       } from "./sections/PromptSection";
import { ImageUploadSection  } from "./sections/ImageUploadSection";
import { AdvancedSection     } from "./sections/AdvancedSection";
import { GenerateButtonSection } from "./sections/GenerateButtonSection";

// Re-export types so callers can import from one place
export type {
  ControlPanelProps, GenerationType, VideoModel, ImageModel,
  VideoMode, ImageMode, GenerationStatus, ArbitraryFrameItem,
} from "./types";
export type { ControlPanelProps as default } from "./types";
import type { ControlPanelProps } from "./types";

// Default advanced values for reset
const ADV_DEFAULTS = {
  seed: -1,
  numFrames: 81,
  fps: 16,
  motionScore: 2.5,
  guidanceScale: 1.0,
  cfgScaleVideo: 1.0,
  referenceStrength: 0.85,
  lightingVariant: "low_noise" as const,
  denoisingStrength: 0.7,
  imageSteps: 20,
  cfgScaleImage: 7.0,
  clipSkip: 2,
  sampler: "Euler a",
  imageGuidanceScale: 7.5,
  imgDenoisingStrength: 0.7,
  width: 720,
  height: 1280,
  negativePrompt: "",
};

export function ControlPanel(props: ControlPanelProps) {
  const {
    generationType, setGenerationType,
    videoModel, setVideoModel,
    imageModel, setImageModel,
    videoMode, setVideoMode,
    imageMode, setImageMode,
    useAdvancedSettings, setUseAdvancedSettings,
    prompt, setPrompt,
    negativePrompt, setNegativePrompt,
    width, setWidth, height, setHeight,
    seed, setSeed,
    referenceImage, onImageUpload, onImageRemove,
    firstFrameImage, lastFrameImage,
    onFirstFrameUpload, onLastFrameUpload,
    onFirstFrameRemove, onLastFrameRemove,
    arbitraryFrames, onArbitraryFrameAdd, onArbitraryFrameRemove, onArbitraryFrameUpdate,
    numFrames, setNumFrames,
    fps, setFps,
    motionScore, setMotionScore,
    cfgScaleVideo, setCfgScaleVideo,
    referenceStrength, setReferenceStrength,
    lightingVariant, setLightingVariant,
    denoisingStrength, setDenoisingStrength,
    imageSteps, setImageSteps,
    cfgScaleImage, setCfgScaleImage,
    clipSkip, setClipSkip,
    sampler, setSampler,
    imageGuidanceScale, setImageGuidanceScale,
    imgDenoisingStrength, setImgDenoisingStrength,
    onGenerate, status, estSeconds,
  } = props;

  // Local UI state
  const [promptFocused, setPromptFocused] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);

  // File input refs
  const fileRef       = useRef<HTMLInputElement>(null);
  const firstFrameRef = useRef<HTMLInputElement>(null);
  const lastFrameRef  = useRef<HTMLInputElement>(null);

  // Derived
  const isGenerating = status === "generating";
  const needsReferenceImage =
    (generationType === "video" && videoMode === "i2v") ||
    (generationType === "image" && imageMode === "img2img");
  const canGenerate =
    !!prompt.trim() && !isGenerating &&
    (needsReferenceImage ? !!referenceImage : true) &&
    (generationType === "video" && videoMode === "first_last_frame"
      ? !!firstFrameImage && !!lastFrameImage
      : true);

  const currentModel = configManager.getModelLabel(generationType, generationType === "video" ? videoModel : imageModel);

  const handleResetAdvanced = useCallback(() => {
    Object.entries(ADV_DEFAULTS).forEach(([key, val]) => {
      const setter = props[`set${key.charAt(0).toUpperCase()}${key.slice(1)}` as keyof ControlPanelProps];
      if (typeof setter === "function") (setter as (v: unknown) => void)(val);
    });
    setSeed(ADV_DEFAULTS.seed);
    setWidth(ADV_DEFAULTS.width);
    setHeight(ADV_DEFAULTS.height);
    setNegativePrompt(ADV_DEFAULTS.negativePrompt);
  }, [props]);

  return (
    <div className="flex flex-col h-full">
      {/* Scrollable content */}
      <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent">

        <TypeModelSection
          generationType={generationType} setGenerationType={setGenerationType}
          videoModel={videoModel} setVideoModel={setVideoModel}
          imageModel={imageModel} setImageModel={setImageModel}
          videoMode={videoMode} setVideoMode={setVideoMode}
          imageMode={imageMode} setImageMode={setImageMode}
          disabled={isGenerating}
        />

        <QuickPresetsSection
          generationType={generationType}
          numFrames={numFrames} setNumFrames={setNumFrames}
          fps={fps} width={width} height={height}
          setWidth={setWidth} setHeight={setHeight}
          useAdvancedSettings={useAdvancedSettings}
          disabled={isGenerating}
        />

        <PromptSection
          prompt={prompt} setPrompt={setPrompt}
          negativePrompt={negativePrompt} setNegativePrompt={setNegativePrompt}
          useAdvancedSettings={useAdvancedSettings}
          disabled={isGenerating}
          promptFocused={promptFocused} setPromptFocused={setPromptFocused}
        />

        <ImageUploadSection
          generationType={generationType}
          videoMode={videoMode} imageMode={imageMode}
          referenceImage={referenceImage} onImageUpload={onImageUpload} onImageRemove={onImageRemove} fileRef={fileRef}
          firstFrameImage={firstFrameImage} lastFrameImage={lastFrameImage}
          onFirstFrameUpload={onFirstFrameUpload} onLastFrameUpload={onLastFrameUpload}
          onFirstFrameRemove={onFirstFrameRemove} onLastFrameRemove={onLastFrameRemove}
          firstFrameRef={firstFrameRef} lastFrameRef={lastFrameRef}
          arbitraryFrames={arbitraryFrames}
          onArbitraryFrameAdd={onArbitraryFrameAdd}
          onArbitraryFrameRemove={onArbitraryFrameRemove}
          onArbitraryFrameUpdate={onArbitraryFrameUpdate}
          numFrames={numFrames}
          disabled={isGenerating}
        />

        <AdvancedSection
          generationType={generationType}
          videoModel={videoModel} imageModel={imageModel}
          videoMode={videoMode} imageMode={imageMode}
          useAdvancedSettings={useAdvancedSettings} setUseAdvancedSettings={setUseAdvancedSettings}
          showAdvanced={showAdvanced} setShowAdvanced={setShowAdvanced}
          onResetAdvanced={handleResetAdvanced}
          negativePrompt={negativePrompt} setNegativePrompt={setNegativePrompt}
          seed={seed} setSeed={setSeed}
          width={width} setWidth={setWidth}
          height={height} setHeight={setHeight}
          numFrames={numFrames} setNumFrames={setNumFrames}
          fps={fps} setFps={setFps}
          motionScore={motionScore} setMotionScore={setMotionScore}
          lightingVariant={lightingVariant} setLightingVariant={setLightingVariant}
          referenceStrength={referenceStrength} setReferenceStrength={setReferenceStrength}
          imageSteps={imageSteps} setImageSteps={setImageSteps}
          cfgScaleImage={cfgScaleImage} setCfgScaleImage={setCfgScaleImage}
          clipSkip={clipSkip} setClipSkip={setClipSkip}
          sampler={sampler} setSampler={setSampler}
          imageGuidanceScale={imageGuidanceScale} setImageGuidanceScale={setImageGuidanceScale}
          imgDenoisingStrength={imgDenoisingStrength} setImgDenoisingStrength={setImgDenoisingStrength}
          disabled={isGenerating}
        />

      </div>

      <GenerateButtonSection
        onGenerate={onGenerate}
        canGenerate={canGenerate}
        isGenerating={isGenerating}
        status={status}
        generationType={generationType}
        currentModel={currentModel}
        estSeconds={estSeconds}
        needsReferenceImage={needsReferenceImage}
        referenceImage={referenceImage}
      />
    </div>
  );
}
