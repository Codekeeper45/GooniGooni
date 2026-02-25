import { motion, AnimatePresence } from "motion/react";
import { X, Download, Maximize2, Video, Image as ImageIcon, Trash2 } from "lucide-react";
import { useState } from "react";
import type { GenerationType } from "./ControlPanel";

export interface GalleryItem {
  id: string;
  url: string;
  prompt: string;
  type: GenerationType;
  model: string;
  width: number;
  height: number;
  seed: number;
  createdAt: Date;
}

interface GalleryPanelProps {
  isOpen: boolean;
  onClose: () => void;
  items: GalleryItem[];
  onClear: () => void;
}

export function GalleryPanel({
  isOpen,
  onClose,
  items,
  onClear,
}: GalleryPanelProps) {
  const [selectedItem, setSelectedItem] = useState<GalleryItem | null>(null);

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
            style={{ background: "rgba(0,0,0,0.7)", backdropFilter: "blur(8px)" }}
            onClick={() => {
              if (selectedItem) {
                setSelectedItem(null);
              } else {
                onClose();
              }
            }}
          />

          {/* Panel */}
          <motion.div
            key="panel"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ type: "spring", damping: 25, stiffness: 300 }}
            className="fixed inset-8 z-50 flex flex-col rounded-3xl overflow-hidden"
            style={{
              background: "#151922",
              border: "1px solid rgba(255,255,255,0.08)",
              boxShadow: "0 20px 80px rgba(0,0,0,0.5)",
              fontFamily: "'Space Grotesk', sans-serif",
            }}
          >
            {/* Header */}
            <div
              className="flex-shrink-0 flex items-center justify-between px-8 h-20 border-b"
              style={{ borderColor: "rgba(255,255,255,0.06)" }}
            >
              <div className="flex items-center gap-3">
                <div
                  className="w-10 h-10 rounded-xl flex items-center justify-center"
                  style={{
                    background: "rgba(79,140,255,0.08)",
                    border: "1px solid rgba(79,140,255,0.15)",
                  }}
                >
                  <ImageIcon className="w-5 h-5" style={{ color: "#4F8CFF" }} />
                </div>
                <div>
                  <h2 className="text-lg" style={{ color: "#E5E7EB" }}>
                    Gallery
                  </h2>
                  <p className="text-xs" style={{ color: "#6B7280" }}>
                    {items.length} {items.length === 1 ? "item" : "items"}
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {items.length > 0 && (
                  <button
                    onClick={onClear}
                    className="flex items-center gap-2 px-4 py-2 rounded-xl text-xs transition-all duration-150"
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
                    <Trash2 className="w-4 h-4" />
                    Clear All
                  </button>
                )}
                <button
                  onClick={onClose}
                  className="p-2.5 rounded-xl transition-all duration-150"
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
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-8">
              {items.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full gap-6">
                  <div
                    className="w-20 h-20 rounded-2xl flex items-center justify-center"
                    style={{
                      background: "rgba(79,140,255,0.04)",
                      border: "1px solid rgba(79,140,255,0.08)",
                    }}
                  >
                    <ImageIcon className="w-9 h-9" style={{ color: "rgba(79,140,255,0.2)" }} />
                  </div>
                  <div className="text-center">
                    <p className="text-base" style={{ color: "#4B5563" }}>
                      No items in gallery
                    </p>
                    <p className="text-sm mt-2" style={{ color: "#374151" }}>
                      Generated images and videos will appear here
                    </p>
                  </div>
                </div>
              ) : (
                <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 gap-4">
                  {items.map((item) => (
                    <GalleryCard
                      key={item.id}
                      item={item}
                      onClick={() => setSelectedItem(item)}
                    />
                  ))}
                </div>
              )}
            </div>
          </motion.div>

          {/* Lightbox */}
          <AnimatePresence>
            {selectedItem && (
              <Lightbox
                item={selectedItem}
                onClose={() => setSelectedItem(null)}
              />
            )}
          </AnimatePresence>
        </>
      )}
    </AnimatePresence>
  );
}

function GalleryCard({
  item,
  onClick,
}: {
  item: GalleryItem;
  onClick: () => void;
}) {
  const Icon = item.type === "video" ? Video : ImageIcon;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9 }}
      className="group relative aspect-square rounded-xl overflow-hidden cursor-pointer"
      style={{
        background: "#1C212C",
        border: "1px solid rgba(255,255,255,0.06)",
      }}
      onClick={onClick}
      whileHover={{ scale: 1.02 }}
      transition={{ duration: 0.2 }}
    >
      {/* Image */}
      <img
        src={item.url}
        alt={item.prompt}
        className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-110"
      />

      {/* Overlay gradient */}
      <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-200" />

      {/* Type badge */}
      <div
        className="absolute top-2 left-2 flex items-center gap-1.5 px-2 py-1 rounded-lg text-[10px]"
        style={{
          background: "rgba(0,0,0,0.6)",
          backdropFilter: "blur(8px)",
          color: "#E5E7EB",
          border: "1px solid rgba(255,255,255,0.1)",
        }}
      >
        <Icon className="w-3 h-3" />
        {item.type === "video" ? "Video" : "Image"}
      </div>

      {/* Hover actions */}
      <div className="absolute bottom-2 right-2 flex gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onClick();
          }}
          className="p-2 rounded-lg transition-all duration-150"
          style={{
            background: "rgba(79,140,255,0.9)",
            color: "white",
          }}
        >
          <Maximize2 className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation();
            window.open(item.url, "_blank");
          }}
          className="p-2 rounded-lg transition-all duration-150"
          style={{
            background: "rgba(255,255,255,0.15)",
            backdropFilter: "blur(8px)",
            color: "white",
            border: "1px solid rgba(255,255,255,0.2)",
          }}
        >
          <Download className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Info overlay (on hover) */}
      <div className="absolute bottom-0 left-0 right-0 p-3 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
        <p
          className="text-xs line-clamp-2 leading-relaxed"
          style={{ color: "rgba(255,255,255,0.9)" }}
        >
          {item.prompt}
        </p>
        <div className="flex items-center gap-2 mt-2">
          <span
            className="text-[10px] px-1.5 py-0.5 rounded"
            style={{
              background: "rgba(0,0,0,0.5)",
              color: "#9CA3AF",
              border: "1px solid rgba(255,255,255,0.1)",
            }}
          >
            {item.model.split(" ")[0]}
          </span>
          <span
            className="text-[10px] px-1.5 py-0.5 rounded"
            style={{
              background: "rgba(0,0,0,0.5)",
              color: "#9CA3AF",
              border: "1px solid rgba(255,255,255,0.1)",
            }}
          >
            {item.width}×{item.height}
          </span>
        </div>
      </div>
    </motion.div>
  );
}

function Lightbox({
  item,
  onClose,
}: {
  item: GalleryItem;
  onClose: () => void;
}) {
  const Icon = item.type === "video" ? Video : ImageIcon;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[60] flex items-center justify-center p-8"
      onClick={onClose}
    >
      {/* Darker backdrop */}
      <div
        className="absolute inset-0"
        style={{ background: "rgba(0,0,0,0.95)", backdropFilter: "blur(20px)" }}
      />

      {/* Content */}
      <motion.div
        initial={{ scale: 0.9, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.9, opacity: 0 }}
        transition={{ type: "spring", damping: 25 }}
        className="relative max-w-6xl max-h-full flex flex-col gap-6"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Image */}
        <div
          className="relative rounded-2xl overflow-hidden"
          style={{
            border: "1px solid rgba(255,255,255,0.1)",
            boxShadow: "0 24px 80px rgba(0,0,0,0.8)",
          }}
        >
          <img
            src={item.url}
            alt={item.prompt}
            className="max-w-full max-h-[70vh] object-contain"
          />
        </div>

        {/* Info panel */}
        <div
          className="rounded-2xl p-6 space-y-4"
          style={{
            background: "#151922",
            border: "1px solid rgba(255,255,255,0.08)",
          }}
        >
          {/* Prompt */}
          <div>
            <p className="text-sm" style={{ color: "#E5E7EB" }}>
              {item.prompt}
            </p>
          </div>

          {/* Metadata */}
          <div className="flex items-center gap-4 text-xs" style={{ color: "#6B7280" }}>
            <div className="flex items-center gap-2">
              <Icon className="w-3.5 h-3.5" />
              <span>{item.type === "video" ? "Video" : "Image"}</span>
            </div>
            <span>•</span>
            <span>{item.model}</span>
            <span>•</span>
            <span>{item.width}×{item.height}</span>
            <span>•</span>
            <span>Seed: {item.seed.toString().slice(0, 8)}</span>
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-2">
            <button
              onClick={() => window.open(item.url, "_blank")}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm transition-all duration-150"
              style={{
                background: "rgba(79,140,255,0.1)",
                border: "1px solid rgba(79,140,255,0.2)",
                color: "#4F8CFF",
              }}
            >
              <Download className="w-4 h-4" />
              Download
            </button>
            <button
              onClick={onClose}
              className="flex items-center gap-2 px-4 py-2.5 rounded-xl text-sm transition-all duration-150"
              style={{
                background: "rgba(255,255,255,0.04)",
                border: "1px solid rgba(255,255,255,0.08)",
                color: "#9CA3AF",
              }}
            >
              Close
            </button>
          </div>
        </div>
      </motion.div>

      {/* Close button (top right) */}
      <button
        onClick={onClose}
        className="absolute top-8 right-8 p-3 rounded-xl transition-all duration-150"
        style={{
          background: "rgba(0,0,0,0.5)",
          backdropFilter: "blur(8px)",
          border: "1px solid rgba(255,255,255,0.1)",
          color: "#E5E7EB",
        }}
      >
        <X className="w-5 h-5" />
      </button>
    </motion.div>
  );
}
