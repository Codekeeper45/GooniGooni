import { motion, AnimatePresence } from "motion/react";
import { X, RotateCcw, Trash2, Clock, Video, Image as ImageLucide } from "lucide-react";
import type { GenerationType } from "./ControlPanel";

export interface HistoryItem {
  id: string;
  prompt: string;
  type: GenerationType;
  model: string;
  thumbnailUrl: string;
  width: number;
  height: number;
  seed: number;
  createdAt: Date;
}

interface HistoryPanelProps {
  isOpen: boolean;
  onClose: () => void;
  history: HistoryItem[];
  onReuse: (item: HistoryItem) => void;
  onClear: () => void;
}

function timeAgo(date: Date): string {
  const diff = Math.floor((Date.now() - date.getTime()) / 1000);
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export function HistoryPanel({
  isOpen,
  onClose,
  history,
  onReuse,
  onClear,
}: HistoryPanelProps) {
  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="fixed inset-0 z-40"
            style={{ background: "rgba(0,0,0,0.5)", backdropFilter: "blur(4px)" }}
            onClick={onClose}
          />

          {/* Panel */}
          <motion.div
            key="panel"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", damping: 28, stiffness: 300 }}
            className="fixed right-0 top-0 bottom-0 z-50 flex flex-col"
            style={{
              width: "clamp(320px, 380px, 380px)",
              background: "#151922",
              borderLeft: "1px solid rgba(255,255,255,0.06)",
              fontFamily: "'Space Grotesk', sans-serif",
            }}
          >
            {/* Header */}
            <div
              className="flex-shrink-0 flex items-center justify-between px-5 h-16 border-b"
              style={{ borderColor: "rgba(255,255,255,0.06)" }}
            >
              <div className="flex items-center gap-2.5">
                <Clock className="w-4 h-4" style={{ color: "#4F8CFF" }} />
                <span className="text-sm" style={{ color: "#E5E7EB" }}>
                  History
                </span>
                {history.length > 0 && (
                  <span
                    className="text-[10px] px-1.5 py-0.5 rounded-full"
                    style={{
                      background: "rgba(79,140,255,0.1)",
                      color: "#4F8CFF",
                      border: "1px solid rgba(79,140,255,0.15)",
                    }}
                  >
                    {history.length}
                  </span>
                )}
              </div>

              <div className="flex items-center gap-1">
                {history.length > 0 && (
                  <button
                    onClick={onClear}
                    className="p-2 rounded-lg text-xs flex items-center gap-1.5 transition-all duration-150"
                    style={{ color: "#4B5563" }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.color = "#EF4444";
                      e.currentTarget.style.background = "rgba(239,68,68,0.06)";
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.color = "#4B5563";
                      e.currentTarget.style.background = "transparent";
                    }}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    Clear
                  </button>
                )}
                <button
                  onClick={onClose}
                  className="p-2 rounded-lg transition-all duration-150"
                  style={{ color: "#6B7280" }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.color = "#E5E7EB";
                    e.currentTarget.style.background = "rgba(255,255,255,0.05)";
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.color = "#6B7280";
                    e.currentTarget.style.background = "transparent";
                  }}
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-4">
              {history.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full gap-4 py-16">
                  <div
                    className="w-14 h-14 rounded-2xl flex items-center justify-center"
                    style={{
                      background: "rgba(79,140,255,0.04)",
                      border: "1px solid rgba(79,140,255,0.08)",
                    }}
                  >
                    <Clock className="w-6 h-6" style={{ color: "rgba(79,140,255,0.2)" }} />
                  </div>
                  <div className="text-center">
                    <p className="text-sm" style={{ color: "#4B5563" }}>
                      No generations yet
                    </p>
                    <p className="text-xs mt-1" style={{ color: "#374151" }}>
                      Your history will appear here
                    </p>
                  </div>
                </div>
              ) : (
                <div className="space-y-3">
                  {history.map((item) => (
                    <HistoryCard
                      key={item.id}
                      item={item}
                      onReuse={onReuse}
                    />
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

function HistoryCard({
  item,
  onReuse,
}: {
  item: HistoryItem;
  onReuse: (item: HistoryItem) => void;
}) {
  const Icon = item.type === "video" ? Video : ImageLucide;
  
  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.95 }}
      className="group rounded-xl overflow-hidden cursor-pointer transition-all duration-200"
      style={{
        background: "#1C212C",
        border: "1px solid rgba(255,255,255,0.05)",
        boxShadow: "0 4px 16px rgba(0,0,0,0.2)",
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = "rgba(79,140,255,0.2)";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = "rgba(255,255,255,0.05)";
      }}
      onClick={() => onReuse(item)}
    >
      {/* Thumbnail */}
      <div className="relative aspect-video overflow-hidden">
        <img
          src={item.thumbnailUrl}
          alt={item.prompt}
          className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />

        {/* Type badge */}
        <span
          className="absolute top-2 left-2 text-[10px] px-1.5 py-0.5 rounded flex items-center gap-1"
          style={{
            background: "rgba(0,0,0,0.6)",
            backdropFilter: "blur(4px)",
            color: "#9CA3AF",
            border: "1px solid rgba(255,255,255,0.07)",
          }}
        >
          <Icon className="w-3 h-3" />
          {item.type === "video" ? "Video" : "Image"}
        </span>

        {/* Hover reuse button */}
        <div className="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-200">
          <div
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs"
            style={{
              background: "rgba(79,140,255,0.15)",
              backdropFilter: "blur(8px)",
              border: "1px solid rgba(79,140,255,0.25)",
              color: "#4F8CFF",
            }}
          >
            <RotateCcw className="w-3.5 h-3.5" />
            Reuse
          </div>
        </div>
      </div>

      {/* Info */}
      <div className="p-3 space-y-2">
        <p
          className="text-xs line-clamp-2 leading-relaxed"
          style={{ color: "#9CA3AF" }}
        >
          {item.prompt}
        </p>
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span
              className="text-[10px] px-1.5 py-0.5 rounded"
              style={{
                background: "rgba(255,255,255,0.03)",
                border: "1px solid rgba(255,255,255,0.06)",
                color: "#4B5563",
              }}
            >
              {item.model.split(" ")[0]}
            </span>
            <span
              className="text-[10px] px-1.5 py-0.5 rounded"
              style={{
                background: "rgba(255,255,255,0.03)",
                border: "1px solid rgba(255,255,255,0.06)",
                color: "#4B5563",
              }}
            >
              {item.width}×{item.height}
            </span>
          </div>
          <span className="text-[10px]" style={{ color: "#374151" }}>
            {timeAgo(item.createdAt)}
          </span>
        </div>
      </div>
    </motion.div>
  );
}
