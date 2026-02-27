/**
 * MediaGenApp — Refactored to use GenerationContext
 * =================================================
 * Now just a view orchestrator. All state and logic live in GenerationContext.
 */

import { useState, useCallback } from "react";
import { Navbar } from "./Navbar";
import { ControlPanel } from "./ControlPanel";
import { OutputPanel } from "./OutputPanel";
import { HistoryPanel } from "./HistoryPanel";
import { useGeneration } from "../context/GenerationContext";

export function MediaGenApp() {
  const {
    generationType, setGenerationType,
    videoModel, setVideoModel,
    imageModel, setImageModel,
    videoMode, setVideoMode,
    imageMode, setImageMode,
    useAdvancedSettings, setUseAdvancedSettings,
    prompt, setPrompt,
    negativePrompt, setNegativePrompt,
    width, setWidth,
    height, setHeight,
    seed, setSeed,
    outputFormat, setOutputFormat,
    referenceImage, setReferenceImage,
    firstFrameImage, setFirstFrameImage,
    lastFrameImage, setLastFrameImage,
    arbitraryFrames, setArbitraryFrames,
    numFrames, setNumFrames,
    videoSteps, setVideoSteps,
    guidanceScale, setGuidanceScale,
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
    status, progress, statusText, error, result, estSeconds,
    generate, retry, regenerate,
    history,
  } = useGeneration();

  const [showHistory, setShowHistory] = useState(false);

  // ── History reuse ───────────────────────────────────────────────────────────
  const handleReuseHistory = useCallback((item: any) => {
    setPrompt(item.prompt);
    if (item.type) {
      setGenerationType(item.type);
    }
    setShowHistory(false);
  }, [setPrompt, setGenerationType]);

  // ── Arbitrary frame handlers (local bridge to context) ──────────────────────
  const handleArbitraryFrameAdd = useCallback((frameIndex: number, image: string) => {
    setArbitraryFrames((prev) => [
      ...prev,
      { id: Date.now().toString(), frameIndex, image },
    ]);
  }, [setArbitraryFrames]);

  const handleArbitraryFrameRemove = useCallback((id: string) => {
    setArbitraryFrames((prev: any) => prev.filter((f: any) => f.id !== id));
  }, [setArbitraryFrames]);

  const handleArbitraryFrameUpdate = useCallback((id: string, frameIndex: number) => {
    setArbitraryFrames((prev: any) =>
      prev.map((f: any) => (f.id === id ? { ...f, frameIndex } : f))
    );
  }, [setArbitraryFrames]);

  return (
    <div
      className="h-screen flex flex-col overflow-hidden"
      style={{
        background: "#0F1117",
        fontFamily: "'Space Grotesk', sans-serif",
        color: "#E5E7EB",
      }}
    >
      <Navbar
        onHistoryClick={() => setShowHistory(true)}
        historyCount={history.length}
      />

      <div className="flex-1 flex overflow-hidden min-h-0">
        <ControlPanel
          generationType={generationType}
          setGenerationType={setGenerationType}
          videoModel={videoModel}
          setVideoModel={setVideoModel}
          imageModel={imageModel}
          setImageModel={setImageModel}
          videoMode={videoMode}
          setVideoMode={setVideoMode}
          imageMode={imageMode}
          setImageMode={setImageMode}
          useAdvancedSettings={useAdvancedSettings}
          setUseAdvancedSettings={setUseAdvancedSettings}
          prompt={prompt}
          setPrompt={setPrompt}
          negativePrompt={negativePrompt}
          setNegativePrompt={setNegativePrompt}
          width={width}
          setWidth={setWidth}
          height={height}
          setHeight={setHeight}
          seed={seed}
          setSeed={setSeed}
          outputFormat={outputFormat}
          setOutputFormat={setOutputFormat}
          referenceImage={referenceImage}
          onImageUpload={setReferenceImage}
          onImageRemove={() => setReferenceImage(null)}
          firstFrameImage={firstFrameImage}
          lastFrameImage={lastFrameImage}
          onFirstFrameUpload={setFirstFrameImage}
          onLastFrameUpload={setLastFrameImage}
          onFirstFrameRemove={() => setFirstFrameImage(null)}
          onLastFrameRemove={() => setLastFrameImage(null)}
          arbitraryFrames={arbitraryFrames}
          onArbitraryFrameAdd={handleArbitraryFrameAdd}
          onArbitraryFrameRemove={handleArbitraryFrameRemove}
          onArbitraryFrameUpdate={handleArbitraryFrameUpdate}
          numFrames={numFrames}
          setNumFrames={setNumFrames}
          videoSteps={videoSteps}
          setVideoSteps={setVideoSteps}
          guidanceScale={guidanceScale}
          setGuidanceScale={setGuidanceScale}
          fps={fps}
          setFps={setFps}
          motionScore={motionScore}
          setMotionScore={setMotionScore}
          cfgScaleVideo={cfgScaleVideo}
          setCfgScaleVideo={setCfgScaleVideo}
          referenceStrength={referenceStrength}
          setReferenceStrength={setReferenceStrength}
          lightingVariant={lightingVariant}
          setLightingVariant={setLightingVariant}
          denoisingStrength={denoisingStrength}
          setDenoisingStrength={setDenoisingStrength}
          imageSteps={imageSteps}
          setImageSteps={setImageSteps}
          cfgScaleImage={cfgScaleImage}
          setCfgScaleImage={setCfgScaleImage}
          clipSkip={clipSkip}
          setClipSkip={setClipSkip}
          sampler={sampler}
          setSampler={setSampler}
          imageGuidanceScale={imageGuidanceScale}
          setImageGuidanceScale={setImageGuidanceScale}
          imgDenoisingStrength={imgDenoisingStrength}
          setImgDenoisingStrength={setImgDenoisingStrength}
          onGenerate={generate}
          status={status}
          estSeconds={estSeconds}
        />

        <OutputPanel
          status={status}
          progress={progress}
          statusText={statusText}
          result={result}
          error={error}
          referenceImage={referenceImage}
          generationType={generationType}
          mode={generationType === "video" ? videoMode : imageMode}
          onRetry={retry}
          onRegenerate={regenerate}
          estSeconds={estSeconds}
        />
      </div>

      <HistoryPanel
        isOpen={showHistory}
        onClose={() => setShowHistory(false)}
        history={history}
        onReuse={handleReuseHistory}
        onClear={() => {}} // History clear not implemented in context yet
      />
    </div>
  );
}
