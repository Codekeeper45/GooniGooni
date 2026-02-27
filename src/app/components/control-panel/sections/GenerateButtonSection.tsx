/**
 * control-panel/sections/GenerateButtonSection.tsx
 * ──────────────────────────────────────────────────
 * Sticky bottom bar with model info, estimated time, and generate button.
 */

import { RotateCcw, Wand2, Sparkles } from "lucide-react";
import type { GenerationType, GenerationStatus } from "../types";

interface Props {
  onGenerate: () => void;
  canGenerate: boolean;
  isGenerating: boolean;
  status: GenerationStatus;
  generationType: GenerationType;
  currentModel: string;
  estSeconds: number;
  needsReferenceImage: boolean;
  referenceImage: string | null;
}

export function GenerateButtonSection({
  onGenerate, canGenerate, isGenerating, status,
  generationType, currentModel, estSeconds,
  needsReferenceImage, referenceImage,
}: Props) {
  return (
    <div
      className="flex-shrink-0 px-6 pb-6 pt-4 border-t space-y-3"
      style={{ borderColor: "rgba(255,255,255,0.06)" }}
    >
      {/* Model info row */}
      <div className="flex items-center justify-between text-[11px]" style={{ color: "#4B5563" }}>
        <span>{currentModel}</span>
        <span>Est. ~{estSeconds}s</span>
      </div>

      {/* Generate button */}
      <button
        onClick={onGenerate}
        disabled={!canGenerate}
        className="w-full relative overflow-hidden rounded-2xl py-4 flex items-center justify-center gap-2.5 text-white text-sm transition-all duration-300 disabled:cursor-not-allowed"
        style={
          canGenerate
            ? { background: "linear-gradient(135deg, #4F8CFF, #6366F1)", boxShadow: "0 0 28px rgba(79,140,255,0.28), 0 8px 20px rgba(0,0,0,0.3)" }
            : { background: "#1C212C", border: "1px solid rgba(255,255,255,0.06)", color: "#374151" }
        }
        onMouseEnter={(e) => {
          if (canGenerate) {
            e.currentTarget.style.boxShadow = "0 0 40px rgba(79,140,255,0.4), 0 8px 24px rgba(0,0,0,0.4)";
            e.currentTarget.style.transform = "translateY(-1px)";
          }
        }}
        onMouseLeave={(e) => {
          if (canGenerate) {
            e.currentTarget.style.boxShadow = "0 0 28px rgba(79,140,255,0.28), 0 8px 20px rgba(0,0,0,0.3)";
            e.currentTarget.style.transform = "translateY(0)";
          }
        }}
      >
        {isGenerating ? (
          <>
            <div className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
            Generating...
          </>
        ) : status === "done" ? (
          <>
            <RotateCcw className="w-4 h-4" />
            Generate Again
          </>
        ) : (
          <>
            <Wand2 className="w-4 h-4" />
            Generate {generationType === "video" ? "Video" : "Image"}
            <Sparkles className="w-3.5 h-3.5 opacity-60" />
          </>
        )}
      </button>

      {/* Hint when a reference image is needed */}
      {needsReferenceImage && !referenceImage && (
        <p className="text-xs text-center" style={{ color: "#F59E0B" }}>
          Upload a reference image to continue
        </p>
      )}
    </div>
  );
}
