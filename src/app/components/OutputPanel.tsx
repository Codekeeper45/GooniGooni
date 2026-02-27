import { motion, AnimatePresence } from "motion/react";
import {
  Video,
  Download,
  RotateCcw,
  XCircle,
  RefreshCw,
  Image as ImageLucide,
} from "lucide-react";
import type React from "react";
import type { GenerationStatus, GenerationType, VideoMode, ImageMode } from "./ControlPanel";
import { VideoPlayer } from "./VideoPlayer";

interface OutputPanelProps {
  status: GenerationStatus;
  progress: number;
  statusText: string;
  stageDetail?: string;
  result: {
    url: string;
    thumbnailUrl?: string;
    seed: number;
    width: number;
    height: number;
    prompt: string;
    model: string;
    type: GenerationType;
  } | null;
  error: string | null;
  referenceImage: string | null;
  generationType: GenerationType;
  mode: VideoMode | ImageMode;
  onRetry: () => void;
  onRegenerate: () => void;
  estSeconds: number;
}

function GlowBar({ value }: { value: number }) {
  return (
    <div
      className="absolute top-0 left-0 right-0 h-[3px]"
      style={{ background: "rgba(255,255,255,0.04)", zIndex: 10 }}
    >
      <motion.div
        className="h-full"
        style={{
          background: "linear-gradient(90deg, #4F8CFF, #6366F1)",
          boxShadow: "0 0 12px rgba(79,140,255,0.8), 0 0 24px rgba(79,140,255,0.3)",
        }}
        animate={{ width: `${value}%` }}
        transition={{ duration: 0.3, ease: "easeOut" }}
      />
    </div>
  );
}

// ── Idle ────────────────────────────────────────────────────────────────────
function IdleState({ generationType }: { generationType: GenerationType }) {
  const Icon = generationType === "video" ? Video : ImageLucide;
  const typeLabel = generationType === "video" ? "video" : "image";

  return (
    <div className="flex flex-col items-center justify-center h-full gap-6 select-none">
      <motion.div
        animate={{ opacity: [0.5, 0.8, 0.5] }}
        transition={{ duration: 3, repeat: Infinity, ease: "easeInOut" }}
        className="relative flex items-center justify-center"
      >
        {/* Outer ring */}
        <motion.div
          className="absolute w-40 h-40 rounded-full"
          style={{ border: "1px solid rgba(79,140,255,0.06)" }}
          animate={{ scale: [1, 1.05, 1], opacity: [0.4, 0.2, 0.4] }}
          transition={{ duration: 4, repeat: Infinity }}
        />
        <motion.div
          className="absolute w-24 h-24 rounded-full"
          style={{ border: "1px solid rgba(79,140,255,0.1)" }}
          animate={{ scale: [1, 1.06, 1], opacity: [0.5, 0.25, 0.5] }}
          transition={{ duration: 4, repeat: Infinity, delay: 0.5 }}
        />
        <div
          className="w-16 h-16 rounded-2xl flex items-center justify-center"
          style={{
            background: "rgba(79,140,255,0.04)",
            border: "1px solid rgba(79,140,255,0.1)",
          }}
        >
          <Icon className="w-7 h-7" style={{ color: "rgba(79,140,255,0.25)" }} />
        </div>
      </motion.div>

      <div className="text-center space-y-2">
        <p className="text-sm" style={{ color: "#4B5563" }}>
          Your generated {typeLabel} will appear here
        </p>
        <p className="text-xs" style={{ color: "#374151" }}>
          Enter a prompt and click Generate
        </p>
      </div>
    </div>
  );
}

// ── Generating ───────────────────────────────────────────────────────────────
function GeneratingState({
  progress,
  statusText,
  stageDetail,
  referenceImage,
  generationType,
  mode,
  estSeconds,
}: {
  progress: number;
  statusText: string;
  stageDetail?: string;
  referenceImage: string | null;
  generationType: GenerationType;
  mode: VideoMode | ImageMode;
  estSeconds: number;
}) {
  const remaining = Math.max(0, Math.round(estSeconds * (1 - progress / 100)));
  const needsReference = mode === "i2v" || mode === "img2img" || mode === "first_last_frame";

  return (
    <div className="relative flex flex-col h-full overflow-hidden">
      <GlowBar value={progress} />

      {/* Background */}
      {needsReference && referenceImage ? (
        <div className="absolute inset-0">
          <img
            src={referenceImage}
            alt="Reference"
            className="w-full h-full object-cover"
            style={{ opacity: 0.08, filter: "blur(12px)", transform: "scale(1.05)" }}
          />
          <div className="absolute inset-0" style={{ background: "#0F1117" + "bb" }} />
        </div>
      ) : (
        <motion.div
          className="absolute inset-0"
          animate={{ opacity: [0.3, 0.6, 0.3] }}
          transition={{ duration: 3, repeat: Infinity }}
          style={{
            background:
              "radial-gradient(ellipse at 50% 50%, rgba(79,140,255,0.04) 0%, transparent 70%)",
          }}
        />
      )}

      {/* Centered content */}
      <div className="relative flex-1 flex flex-col items-center justify-center gap-8 px-8">
        {/* Rings + progress */}
        <div className="relative flex items-center justify-center">
          {[80, 56, 36].map((size, i) => (
            <motion.div
              key={i}
              className="absolute rounded-full"
              style={{
                width: size * 2,
                height: size * 2,
                border: `1px solid rgba(79,140,255,${0.06 + i * 0.06})`,
              }}
              animate={{
                scale: [1, 1.04, 1],
                opacity: [0.5, 0.2, 0.5],
              }}
              transition={{
                duration: 2.5,
                repeat: Infinity,
                delay: i * 0.4,
              }}
            />
          ))}

          {/* Center */}
          <div
            className="relative w-16 h-16 rounded-2xl flex flex-col items-center justify-center"
            style={{
              background: "rgba(79,140,255,0.08)",
              border: "1px solid rgba(79,140,255,0.2)",
              boxShadow: "0 0 24px rgba(79,140,255,0.12)",
            }}
          >
            {/* Spinner */}
            <div
              className="absolute inset-0 rounded-2xl border-2 border-transparent animate-spin"
              style={{ borderTopColor: "#4F8CFF" }}
            />
            <span
              className="text-sm"
              style={{ color: "#4F8CFF", fontFamily: "'Space Grotesk', sans-serif" }}
            >
              {progress}%
            </span>
          </div>
        </div>

        {/* Status + time */}
        <div className="text-center space-y-2">
          <AnimatePresence mode="wait">
            <motion.p
              key={statusText}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.2 }}
              className="text-sm"
              style={{ color: "#9CA3AF", fontFamily: "'Space Grotesk', sans-serif" }}
            >
              {statusText}
            </motion.p>
          </AnimatePresence>
          <p className="text-xs" style={{ color: "#4B5563" }}>
            ~{remaining}s remaining
          </p>
          {stageDetail ? (
            <p className="text-[11px]" style={{ color: "#6B7280" }}>
              {stageDetail}
            </p>
          ) : null}
        </div>

        {/* Wide progress bar */}
        <div className="w-full max-w-xs space-y-1.5">
          <div
            className="w-full h-1.5 rounded-full overflow-hidden"
            style={{ background: "rgba(255,255,255,0.05)" }}
          >
            <motion.div
              className="h-full rounded-full"
              style={{
                background: "linear-gradient(90deg, #4F8CFF, #6366F1)",
                boxShadow: "0 0 8px rgba(79,140,255,0.6)",
              }}
              animate={{ width: `${progress}%` }}
              transition={{ duration: 0.3 }}
            />
          </div>
          <div className="flex justify-between text-[10px]" style={{ color: "#374151" }}>
            <span>0%</span>
            <span>100%</span>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Success ──────────────────────────────────────────────────────────────────
function SuccessState({
  result,
  onRegenerate,
}: {
  result: NonNullable<OutputPanelProps["result"]>;
  onRegenerate: () => void;
}) {
  const isVideo = result.type === "video";

  const handleDownload = async () => {
    try {
      const response = await fetch(result.url, { credentials: "include" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const ext = isVideo ? "mp4" : "png";
      const a = document.createElement("a");
      a.href = url;
      a.download = `gooni-result-${Date.now()}.${ext}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      window.open(result.url, "_blank", "noopener,noreferrer");
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex flex-col h-full"
    >
      {/* Media area */}
      <div className="relative flex-1 overflow-hidden bg-black">
        {isVideo ? (
          <VideoPlayer
            src={result.url}
            poster={result.thumbnailUrl}
            className="w-full h-full"
          />
        ) : (
          <>
            <img
              src={result.url}
              alt={result.prompt}
              className="w-full h-full object-cover"
            />
            {/* Subtle vignette */}
            <div
              className="absolute inset-0 pointer-events-none"
              style={{
                background:
                  "radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.4) 100%)",
              }}
            />
          </>
        )}
      </div>

      {/* Metadata strip */}
      <div
        className="flex-shrink-0 px-6 py-4 flex items-center justify-between border-t"
        style={{
          borderColor: "rgba(255,255,255,0.06)",
          background: "#151922",
          fontFamily: "'Space Grotesk', sans-serif",
        }}
      >
        <div className="flex items-center gap-3">
          {[
            { label: "Model", value: result.model.split(" ")[0] },
            { label: "Seed", value: result.seed.toString().slice(0, 8) },
            { label: "Size", value: `${result.width}×${result.height}` },
            ...(isVideo ? [{ label: "Type", value: "Video" }] : []),
          ].map((m) => (
            <div key={m.label} className="flex items-center gap-1.5">
              <span className="text-[10px] uppercase tracking-wider" style={{ color: "#4B5563" }}>
                {m.label}
              </span>
              <span className="text-xs" style={{ color: "#9CA3AF" }}>
                {m.value}
              </span>
            </div>
          ))}
        </div>

        <div className="flex gap-2">
          <ActionChip
            icon={<Download className="w-3.5 h-3.5" />}
            label="Download"
            onClick={handleDownload}
          />
          <ActionChip
            icon={<RotateCcw className="w-3.5 h-3.5" />}
            label="Regenerate"
            onClick={onRegenerate}
          />
        </div>
      </div>
    </motion.div>
  );
}

function ActionChip({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-all duration-150"
      style={{
        background: "rgba(255,255,255,0.04)",
        border: "1px solid rgba(255,255,255,0.07)",
        color: "#9CA3AF",
        fontFamily: "'Space Grotesk', sans-serif",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = "rgba(255,255,255,0.08)";
        e.currentTarget.style.color = "#E5E7EB";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = "rgba(255,255,255,0.04)";
        e.currentTarget.style.color = "#9CA3AF";
      }}
    >
      {icon}
      {label}
    </button>
  );
}

// ── Error ─────────────────────────────────────────────────────────────────────
function ErrorState({
  error,
  onRetry,
}: {
  error: string;
  onRetry: () => void;
}) {
  return (
    <div className="flex flex-col items-center justify-center h-full gap-5">
      <div
        className="w-16 h-16 rounded-2xl flex items-center justify-center"
        style={{
          background: "rgba(239,68,68,0.06)",
          border: "1px solid rgba(239,68,68,0.15)",
        }}
      >
        <XCircle className="w-7 h-7" style={{ color: "#EF4444" }} />
      </div>
      <div className="text-center space-y-1.5">
        <p className="text-sm" style={{ color: "#9CA3AF" }}>
          Generation failed
        </p>
        <p className="text-xs" style={{ color: "#6B7280" }}>
          {error}
        </p>
      </div>
      <button
        onClick={onRetry}
        className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm transition-all duration-150"
        style={{
          background: "rgba(239,68,68,0.08)",
          border: "1px solid rgba(239,68,68,0.2)",
          color: "#EF4444",
          fontFamily: "'Space Grotesk', sans-serif",
        }}
      >
        <RefreshCw className="w-4 h-4" />
        Retry
      </button>
    </div>
  );
}

// ── Main export ───────────────────────────────────────────────────────────────
export function OutputPanel({
  status, progress, statusText, stageDetail, result, error,
  referenceImage, generationType, mode, onRetry, onRegenerate, estSeconds,
}: OutputPanelProps) {
  return (
    <div
      className="flex-1 relative overflow-hidden"
      style={{ background: "#0F1117", minHeight: 0 }}
    >
      <AnimatePresence mode="wait">
        {status === "idle" && (
          <motion.div
            key="idle"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0"
          >
            <IdleState generationType={generationType} />
          </motion.div>
        )}

        {status === "generating" && (
          <motion.div
            key="generating"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0"
          >
            <GeneratingState
              progress={progress}
              statusText={statusText}
              stageDetail={stageDetail}
              referenceImage={referenceImage}
              generationType={generationType}
              mode={mode}
              estSeconds={estSeconds}
            />
          </motion.div>
        )}

        {status === "done" && result && (
          <motion.div
            key="done"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 flex flex-col"
          >
            <SuccessState result={result} onRegenerate={onRegenerate} />
          </motion.div>
        )}

        {status === "error" && (
          <motion.div
            key="error"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0"
          >
            <ErrorState error={error ?? "Unknown error"} onRetry={onRetry} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
