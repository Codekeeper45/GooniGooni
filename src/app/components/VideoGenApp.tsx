import { useState, useEffect } from "react";
import { Navbar } from "./Navbar";
import { ControlPanel } from "./ControlPanel";
import { OutputPanel } from "./OutputPanel";
import { HistoryPanel } from "./HistoryPanel";
import type { Mode, MotionIntensity, GenerationStatus } from "./ControlPanel";
import type { HistoryItem } from "./HistoryPanel";

// ─── API stub — real call goes through MediaGenApp ───────────────────────────
async function simulateGeneration(
  _onProgress: (p: number) => void
): Promise<string> {
  throw new Error("Backend URL не настроен. Задеплойте modal backend и укажите VITE_API_URL.");
}


function calcEstSeconds(duration: number, resolution: string): number {
  const base = duration * 6;
  const mul = resolution === "720p" ? 1.6 : 1;
  return Math.round(base * mul);
}

// ─── Main Component ────────────────────────────────────────────────────────────
export function VideoGenApp() {
  // ── Persisted state ─────────────────────────────────────────────────────────
  const [prompt, setPromptRaw] = useState<string>(
    () => localStorage.getItem("vg_prompt") ?? ""
  );
  const setPrompt = (p: string) => {
    setPromptRaw(p);
    localStorage.setItem("vg_prompt", p);
  };

  // ── UI state ─────────────────────────────────────────────────────────────────
  const [mode, setMode] = useState<Mode>("t2v");
  const [negativePrompt, setNegativePrompt] = useState("");
  const [uploadedImage, setUploadedImage] = useState<string | null>(null);
  const [motionIntensity, setMotionIntensity] = useState<MotionIntensity>("medium");
  const [duration, setDuration] = useState(4);
  const [resolution, setResolution] = useState("720p");
  const [imageInfluence, setImageInfluence] = useState(0.6);
  const [seed, setSeed] = useState<number | "random">("random");
  const [cfgScale, setCfgScale] = useState(7.5);

  // ── Generation state ─────────────────────────────────────────────────────────
  const [status, setStatus] = useState<GenerationStatus>("idle");
  const [progress, setProgress] = useState(0);
  const [statusText, setStatusText] = useState("");
  const [result, setResult] = useState<{
    videoUrl: string;
    seed: number;
    resolution: string;
    duration: number;
    fps: number;
    prompt: string;
    model: string;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  // ── History ───────────────────────────────────────────────────────────────────
  const [history, setHistory] = useState<HistoryItem[]>([]);
  const [showHistory, setShowHistory] = useState(false);

  // Update status text as progress changes
  useEffect(() => {
    if (status === "generating") {
      setStatusText(getStatusText(progress));
    }
  }, [progress, status]);

  const estSeconds = calcEstSeconds(duration, resolution);

  // ── Generate ─────────────────────────────────────────────────────────────────
  const handleGenerate = async () => {
    if (!prompt.trim()) return;
    if (mode === "i2v" && !uploadedImage) return;
    if (status === "generating") return;

    const resolvedSeed =
      seed === "random" ? Math.floor(Math.random() * 2147483647) : seed;

    setStatus("generating");
    setProgress(0);
    setStatusText("Initializing model...");
    setError(null);
    setResult(null);

    try {
      const videoUrl = await simulateGeneration((p) => setProgress(p));

      const newResult = {
        videoUrl,
        seed: resolvedSeed,
        resolution,
        duration,
        fps: 24,
        prompt,
        model: "Wan2.1",
      };

      setResult(newResult);
      setStatus("done");
      setProgress(100);

      // Add to history
      const historyItem: HistoryItem = {
        id: Date.now().toString(),
        prompt,
        mode,
        thumbnailUrl: videoUrl,
        resolution,
        duration,
        seed: resolvedSeed,
        createdAt: new Date(),
      };
      setHistory((prev) => [historyItem, ...prev.slice(0, 49)]);
    } catch {
      setStatus("error");
      setError("Connection to inference server failed.");
    }
  };

  const handleRetry = () => {
    setStatus("idle");
    setError(null);
  };

  const handleRegenerate = () => {
    handleGenerate();
  };

  const handleReuseHistory = (item: HistoryItem) => {
    setPrompt(item.prompt);
    setMode(item.mode);
    setDuration(item.duration);
    setResolution(item.resolution);
    setShowHistory(false);
  };

  return (
    <div
      className="h-screen flex flex-col overflow-hidden"
      style={{
        background: "#0F1117",
        fontFamily: "'Space Grotesk', sans-serif",
        color: "#E5E7EB",
      }}
    >
      {/* ── Navbar ─────────────────────────────────────────────────────────── */}
      <Navbar
        onHistoryClick={() => setShowHistory(true)}
        historyCount={history.length}
      />

      {/* ── Main layout ────────────────────────────────────────────────────── */}
      <div className="flex-1 flex overflow-hidden min-h-0">
        {/* Left: Control Panel */}
        <ControlPanel
          mode={mode}
          setMode={setMode}
          prompt={prompt}
          setPrompt={setPrompt}
          negativePrompt={negativePrompt}
          setNegativePrompt={setNegativePrompt}
          uploadedImage={uploadedImage}
          onImageUpload={(data) => setUploadedImage(data)}
          onImageRemove={() => setUploadedImage(null)}
          motionIntensity={motionIntensity}
          setMotionIntensity={setMotionIntensity}
          duration={duration}
          setDuration={setDuration}
          resolution={resolution}
          setResolution={setResolution}
          imageInfluence={imageInfluence}
          setImageInfluence={setImageInfluence}
          seed={seed}
          setSeed={setSeed}
          cfgScale={cfgScale}
          setCfgScale={setCfgScale}
          onGenerate={handleGenerate}
          status={status}
          estSeconds={estSeconds}
        />

        {/* Right: Output Panel */}
        <OutputPanel
          status={status}
          progress={progress}
          statusText={statusText}
          result={result}
          error={error}
          uploadedImage={uploadedImage}
          mode={mode}
          onRetry={handleRetry}
          onRegenerate={handleRegenerate}
          estSeconds={estSeconds}
        />
      </div>

      {/* History side panel */}
      <HistoryPanel
        isOpen={showHistory}
        onClose={() => setShowHistory(false)}
        history={history}
        onReuse={handleReuseHistory}
        onClear={() => setHistory([])}
      />
    </div>
  );
}
