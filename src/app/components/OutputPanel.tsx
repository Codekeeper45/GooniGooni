import {
  Ban,
  Download,
  Image as ImageIcon,
  RefreshCw,
  RotateCcw,
  XCircle,
} from "lucide-react";
import { motion } from "motion/react";
import type { ResultSummary } from "../api";

export type UiStatus = "idle" | "generating" | "success" | "error" | "cancelled";

interface OutputPanelProps {
  status: UiStatus;
  statusText: string;
  error: string | null;
  result: (ResultSummary & { objectUrl: string }) | null;
  onCancel: () => void;
  onRetry: () => void;
  onDownload: () => void;
}

export function OutputPanel({
  status,
  statusText,
  error,
  result,
  onCancel,
  onRetry,
  onDownload,
}: OutputPanelProps) {
  return (
    <main className="relative min-h-[520px] flex-1 overflow-hidden bg-[#0f1117]">
      {status === "idle" && (
        <div className="flex h-full min-h-[520px] flex-col items-center justify-center gap-4 text-center">
          <div className="rounded-3xl border border-blue-500/10 bg-blue-500/[0.04] p-7 text-blue-400/30">
            <ImageIcon className="h-12 w-12" />
          </div>
          <div>
            <p className="text-sm text-gray-400">Your image will appear here</p>
            <p className="mt-1 text-xs text-gray-600">
              Every visible control is sent to the Pony backend
            </p>
          </div>
        </div>
      )}

      {status === "generating" && (
        <div className="flex h-full min-h-[520px] flex-col items-center justify-center gap-7 px-8 text-center">
          <div className="relative h-28 w-28">
            <motion.div
              className="absolute inset-0 rounded-full border border-blue-500/20"
              animate={{ scale: [0.9, 1.15], opacity: [0.8, 0] }}
              transition={{ duration: 1.6, repeat: Infinity }}
            />
            <motion.div
              className="absolute inset-4 rounded-full border-2 border-transparent border-t-blue-400"
              animate={{ rotate: 360 }}
              transition={{ duration: 1, repeat: Infinity, ease: "linear" }}
            />
            <div className="absolute inset-0 flex items-center justify-center">
              <ImageIcon className="h-6 w-6 text-blue-400" />
            </div>
          </div>
          <div className="max-w-md">
            <p className="text-sm text-gray-200">{statusText}</p>
            <p className="mt-2 text-xs leading-relaxed text-gray-500">
              Model startup and generation may take several minutes. This indicator is
              intentionally indeterminate; the backend does not invent fake percentages.
            </p>
          </div>
          <button
            type="button"
            onClick={onCancel}
            className="flex items-center gap-2 rounded-xl border border-red-500/20 bg-red-500/[0.06] px-4 py-2 text-xs text-red-300 hover:bg-red-500/10"
          >
            <Ban className="h-4 w-4" />
            Cancel generation
          </button>
        </div>
      )}

      {status === "success" && result && (
        <div className="flex h-full min-h-[520px] flex-col">
          <div className="flex min-h-0 flex-1 items-center justify-center bg-black/30 p-4">
            <img
              src={result.objectUrl}
              alt={result.prompt}
              className="max-h-full max-w-full rounded-xl object-contain shadow-2xl"
            />
          </div>
          <div className="flex flex-wrap items-center justify-between gap-4 border-t border-white/[0.06] bg-[#151922] px-5 py-4">
            <div className="flex flex-wrap gap-x-5 gap-y-2 text-xs">
              <span className="text-gray-500">
                Model <strong className="font-medium text-gray-300">Pony V6 XL</strong>
              </span>
              <span className="text-gray-500">
                Seed <strong className="font-medium text-gray-300">{result.seed}</strong>
              </span>
              <span className="text-gray-500">
                Size{" "}
                <strong className="font-medium text-gray-300">
                  {result.width}×{result.height}
                </strong>
              </span>
              <span className="text-gray-500">
                Mode <strong className="font-medium text-gray-300">{result.mode}</strong>
              </span>
            </div>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={onDownload}
                className="flex items-center gap-2 rounded-lg border border-white/10 px-3 py-2 text-xs text-gray-300 hover:bg-white/5"
              >
                <Download className="h-4 w-4" />
                Download
              </button>
              <button
                type="button"
                onClick={onRetry}
                className="flex items-center gap-2 rounded-lg bg-blue-500/10 px-3 py-2 text-xs text-blue-300 hover:bg-blue-500/15"
              >
                <RotateCcw className="h-4 w-4" />
                Regenerate
              </button>
            </div>
          </div>
        </div>
      )}

      {(status === "error" || status === "cancelled") && (
        <div className="flex h-full min-h-[520px] flex-col items-center justify-center gap-5 px-6 text-center">
          <div
            className={`rounded-2xl border p-5 ${
              status === "error"
                ? "border-red-500/20 bg-red-500/[0.06] text-red-400"
                : "border-amber-500/20 bg-amber-500/[0.06] text-amber-400"
            }`}
          >
            {status === "error" ? (
              <XCircle className="h-8 w-8" />
            ) : (
              <Ban className="h-8 w-8" />
            )}
          </div>
          <div className="max-w-lg">
            <p className="text-sm text-gray-200">
              {status === "error" ? "Generation failed" : "Generation cancelled"}
            </p>
            <p className="mt-2 break-words text-xs leading-relaxed text-gray-500">
              {error || statusText}
            </p>
          </div>
          <button
            type="button"
            onClick={onRetry}
            className="flex items-center gap-2 rounded-xl border border-white/10 px-4 py-2 text-xs text-gray-300 hover:bg-white/5"
          >
            <RefreshCw className="h-4 w-4" />
            Retry with same settings
          </button>
        </div>
      )}
    </main>
  );
}
