import { useState, useMemo } from "react";
import { useNavigate } from "react-router";
import { motion, AnimatePresence } from "motion/react";
import {
  ArrowLeft,
  Sparkles,
  Image as ImageIcon,
  Video,
  Download,
  Trash2,
  X,
  Search,
  Grid2x2,
  LayoutGrid,
  Play,
  SlidersHorizontal,
} from "lucide-react";
import { useGallery, type GalleryItem } from "../context/GalleryContext";
import { VideoPlayer } from "../components/VideoPlayer";
import { readApiError, sessionFetch } from "../utils/sessionClient";

type FilterType = "all" | "image" | "video";
type SortMode = "newest" | "oldest";
type GridSize = "lg" | "sm";

export function GalleryPage() {
  const navigate = useNavigate();
  const { gallery, clearGallery, removeFromGallery } = useGallery();

  const [filter, setFilter] = useState<FilterType>("all");
  const [sort, setSort] = useState<SortMode>("newest");
  const [gridSize, setGridSize] = useState<GridSize>("lg");
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedItem, setSelectedItem] = useState<GalleryItem | null>(null);
  const [showConfirmClear, setShowConfirmClear] = useState(false);

  const handleDeleteItem = async (id: string) => {
    const response = await sessionFetch(
      `/gallery/${id}`,
      { method: "DELETE" },
      { retryOn401: true },
    );
    if (!response.ok) {
      const err = await readApiError(response, "Failed to delete gallery item.");
      throw new Error(`${err.detail} ${err.userAction}`.trim());
    }
    removeFromGallery(id);
    if (selectedItem?.id === id) {
      setSelectedItem(null);
    }
  };

  const filtered = useMemo(() => {
    let items = [...gallery];

    if (filter !== "all") {
      items = items.filter((item) => item.type === filter);
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      items = items.filter(
        (item) =>
          item.prompt.toLowerCase().includes(q) ||
          item.model.toLowerCase().includes(q)
      );
    }

    if (sort === "oldest") {
      items = items.reverse();
    }

    return items;
  }, [gallery, filter, sort, searchQuery]);

  const imageCount = gallery.filter((i) => i.type === "image").length;
  const videoCount = gallery.filter((i) => i.type === "video").length;

  const colClass =
    gridSize === "lg"
      ? "grid-cols-2 md:grid-cols-3 lg:grid-cols-4"
      : "grid-cols-3 md:grid-cols-4 lg:grid-cols-6";

  return (
    <div
      className="min-h-screen flex flex-col"
      style={{
        background: "#0B0E14",
        fontFamily: "'Space Grotesk', sans-serif",
        color: "#E5E7EB",
      }}
    >
      {/* Header */}
      <header
        className="flex-shrink-0 flex items-center justify-between px-6 border-b"
        style={{
          height: 64,
          background: "rgba(15,17,23,0.95)",
          backdropFilter: "blur(20px)",
          borderColor: "rgba(255,255,255,0.06)",
          position: "sticky",
          top: 0,
          zIndex: 20,
        }}
      >
        {/* Left: back + brand */}
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate("/")}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm transition-all duration-150"
            style={{ color: "#9CA3AF" }}
            onMouseEnter={(e) => {
              e.currentTarget.style.color = "#E5E7EB";
              e.currentTarget.style.background = "rgba(255,255,255,0.05)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.color = "#9CA3AF";
              e.currentTarget.style.background = "transparent";
            }}
          >
            <ArrowLeft className="w-4 h-4" />
            Studio
          </button>

          <div
            className="w-px h-5"
            style={{ background: "rgba(255,255,255,0.08)" }}
          />

          {/* Brand */}
          <div className="flex items-center gap-2.5">
            <div
              className="w-7 h-7 rounded-lg flex items-center justify-center"
              style={{
                background: "linear-gradient(135deg, #4F8CFF, #6366F1)",
                boxShadow: "0 0 14px rgba(79,140,255,0.35)",
              }}
            >
              <Sparkles className="w-3.5 h-3.5 text-white" />
            </div>
            <span style={{ color: "#E5E7EB" }}>MediaGen</span>
            <span
              className="text-[10px] px-1.5 py-0.5 rounded"
              style={{
                background: "rgba(79,140,255,0.08)",
                color: "#4F8CFF",
                border: "1px solid rgba(79,140,255,0.15)",
              }}
            >
              Gallery
            </span>
          </div>
        </div>

        {/* Right: actions */}
        <div className="flex items-center gap-2">
          {gallery.length > 0 && (
            <button
              onClick={() => setShowConfirmClear(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-all duration-150"
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
              Clear All
            </button>
          )}
        </div>
      </header>

      {/* Stats bar */}
      <div
        className="flex-shrink-0 px-6 py-4 flex items-center gap-6 border-b"
        style={{ borderColor: "rgba(255,255,255,0.04)" }}
      >
        {[
          { label: "Total", value: gallery.length, color: "#9CA3AF" },
          { label: "Images", value: imageCount, color: "#34D399", Icon: ImageIcon },
          { label: "Videos", value: videoCount, color: "#60A5FA", Icon: Video },
        ].map((stat) => (
          <div key={stat.label} className="flex items-center gap-2">
            {stat.Icon && <stat.Icon className="w-3.5 h-3.5" style={{ color: stat.color }} />}
            <span className="text-2xl tabular-nums" style={{ color: stat.color }}>
              {stat.value}
            </span>
            <span className="text-xs" style={{ color: "#4B5563" }}>
              {stat.label}
            </span>
          </div>
        ))}
      </div>

      {/* Toolbar */}
      <div
        className="flex-shrink-0 px-6 py-3 flex items-center gap-3 border-b"
        style={{ borderColor: "rgba(255,255,255,0.04)" }}
      >
        {/* Filter tabs */}
        <div
          className="flex items-center gap-1 p-1 rounded-lg"
          style={{ background: "rgba(255,255,255,0.04)" }}
        >
          {(["all", "image", "video"] as FilterType[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className="px-3 py-1.5 rounded-md text-xs capitalize transition-all duration-150"
              style={
                filter === f
                  ? {
                      background: "rgba(79,140,255,0.15)",
                      color: "#4F8CFF",
                      border: "1px solid rgba(79,140,255,0.2)",
                    }
                  : { color: "#6B7280", border: "1px solid transparent" }
              }
            >
              {f === "all" ? "All" : f === "image" ? "Images" : "Videos"}
            </button>
          ))}
        </div>

        {/* Search */}
        <div
          className="flex items-center gap-2 px-3 py-1.5 rounded-lg flex-1 max-w-xs"
          style={{
            background: "rgba(255,255,255,0.04)",
            border: "1px solid rgba(255,255,255,0.06)",
          }}
        >
          <Search className="w-3.5 h-3.5 flex-shrink-0" style={{ color: "#4B5563" }} />
          <input
            type="text"
            placeholder="Search prompts, models..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="bg-transparent outline-none text-xs flex-1"
            style={{ color: "#9CA3AF", fontFamily: "'Space Grotesk', sans-serif" }}
          />
          {searchQuery && (
            <button onClick={() => setSearchQuery("")}>
              <X className="w-3 h-3" style={{ color: "#4B5563" }} />
            </button>
          )}
        </div>

        <div className="flex-1" />

        {/* Sort */}
        <div className="flex items-center gap-1.5">
          <SlidersHorizontal className="w-3.5 h-3.5" style={{ color: "#4B5563" }} />
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as SortMode)}
            className="bg-transparent text-xs outline-none cursor-pointer"
            style={{ color: "#6B7280", fontFamily: "'Space Grotesk', sans-serif" }}
          >
            <option value="newest" style={{ background: "#151922" }}>
              Newest first
            </option>
            <option value="oldest" style={{ background: "#151922" }}>
              Oldest first
            </option>
          </select>
        </div>

        {/* Grid size */}
        <div
          className="flex items-center gap-0.5 p-0.5 rounded-lg"
          style={{ background: "rgba(255,255,255,0.04)" }}
        >
          <button
            onClick={() => setGridSize("lg")}
            className="p-1.5 rounded-md transition-all duration-150"
            style={
              gridSize === "lg"
                ? { background: "rgba(79,140,255,0.15)", color: "#4F8CFF" }
                : { color: "#4B5563" }
            }
          >
            <Grid2x2 className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => setGridSize("sm")}
            className="p-1.5 rounded-md transition-all duration-150"
            style={
              gridSize === "sm"
                ? { background: "rgba(79,140,255,0.15)", color: "#4F8CFF" }
                : { color: "#4B5563" }
            }
          >
            <LayoutGrid className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Content grid */}
      <div className="flex-1 overflow-y-auto p-6">
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 gap-6">
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
                {searchQuery
                  ? "No results found"
                  : gallery.length === 0
                  ? "Your gallery is empty"
                  : "No items match the filter"}
              </p>
              <p className="text-sm mt-2" style={{ color: "#374151" }}>
                {gallery.length === 0
                  ? "Generate images and videos to see them here"
                  : "Try adjusting your search or filter"}
              </p>
            </div>
            {gallery.length === 0 && (
              <button
                onClick={() => navigate("/")}
                className="flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm transition-all duration-150"
                style={{
                  background: "rgba(79,140,255,0.1)",
                  border: "1px solid rgba(79,140,255,0.2)",
                  color: "#4F8CFF",
                }}
              >
                <ArrowLeft className="w-4 h-4" />
                Go to Studio
              </button>
            )}
          </div>
        ) : (
          <motion.div layout className={`grid ${colClass} gap-4`}>
            <AnimatePresence>
              {filtered.map((item, idx) => (
                <GalleryCard
                  key={item.id}
                  item={item}
                  index={idx}
                  gridSize={gridSize}
                  onClick={() => setSelectedItem(item)}
                  onDelete={() => {
                    void handleDeleteItem(item.id).catch((err) => {
                      console.error("Delete failed", err);
                    });
                  }}
                />
              ))}
            </AnimatePresence>
          </motion.div>
        )}
      </div>

      {/* Lightbox */}
      <AnimatePresence>
        {selectedItem && (
          <Lightbox
            item={selectedItem}
            onClose={() => setSelectedItem(null)}
          />
        )}
      </AnimatePresence>

      {/* Confirm clear dialog */}
      <AnimatePresence>
        {showConfirmClear && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center"
            style={{ background: "rgba(0,0,0,0.7)", backdropFilter: "blur(8px)" }}
            onClick={() => setShowConfirmClear(false)}
          >
            <motion.div
              initial={{ scale: 0.9, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.9, opacity: 0 }}
              className="rounded-2xl p-6 flex flex-col gap-4 w-80"
              style={{
                background: "#151922",
                border: "1px solid rgba(255,255,255,0.08)",
              }}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center gap-3">
                <div
                  className="w-10 h-10 rounded-xl flex items-center justify-center"
                  style={{
                    background: "rgba(239,68,68,0.08)",
                    border: "1px solid rgba(239,68,68,0.15)",
                  }}
                >
                  <Trash2 className="w-4 h-4" style={{ color: "#EF4444" }} />
                </div>
                <div>
                  <p className="text-sm" style={{ color: "#E5E7EB" }}>
                    Clear gallery?
                  </p>
                  <p className="text-xs mt-0.5" style={{ color: "#6B7280" }}>
                    This will remove all {gallery.length} items
                  </p>
                </div>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    clearGallery();
                    setShowConfirmClear(false);
                  }}
                  className="flex-1 py-2 rounded-xl text-sm transition-all duration-150"
                  style={{
                    background: "rgba(239,68,68,0.12)",
                    border: "1px solid rgba(239,68,68,0.25)",
                    color: "#EF4444",
                  }}
                >
                  Clear All
                </button>
                <button
                  onClick={() => setShowConfirmClear(false)}
                  className="flex-1 py-2 rounded-xl text-sm transition-all duration-150"
                  style={{
                    background: "rgba(255,255,255,0.04)",
                    border: "1px solid rgba(255,255,255,0.08)",
                    color: "#9CA3AF",
                  }}
                >
                  Cancel
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

// ── Gallery Card ──────────────────────────────────────────────────────────────
function GalleryCard({
  item,
  index,
  gridSize,
  onClick,
  onDelete,
}: {
  item: GalleryItem;
  index: number;
  gridSize: GridSize;
  onClick: () => void;
  onDelete: () => void;
}) {
  const TypeIcon = item.type === "video" ? Video : ImageIcon;
  const thumbSrc = item.thumbnailUrl || item.url;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.92 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.88 }}
      transition={{ duration: 0.2, delay: Math.min(index * 0.03, 0.3) }}
      className="group relative rounded-xl overflow-hidden cursor-pointer"
      style={{
        background: "#1C212C",
        border: "1px solid rgba(255,255,255,0.06)",
        aspectRatio: "1 / 1",
      }}
      onClick={onClick}
      whileHover={{ scale: 1.01 }}
    >
      {/* Thumbnail */}
      <img
        src={thumbSrc}
        alt={item.prompt}
        className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
      />

      {/* Hover gradient */}
      <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-200" />

      {/* Type badge */}
      <div
        className="absolute top-2 left-2 flex items-center gap-1 px-2 py-0.5 rounded-lg text-[10px]"
        style={{
          background: "rgba(0,0,0,0.55)",
          backdropFilter: "blur(8px)",
          color: "#E5E7EB",
          border: "1px solid rgba(255,255,255,0.1)",
        }}
      >
        <TypeIcon className="w-3 h-3" />
        {item.type === "video" ? "Video" : "Image"}
      </div>

      {/* Play icon for videos */}
      {item.type === "video" && (
        <div className="absolute inset-0 flex items-center justify-center opacity-70 group-hover:opacity-100 transition-opacity">
          <div
            className="w-12 h-12 rounded-full flex items-center justify-center"
            style={{
              background: "rgba(0,0,0,0.5)",
              backdropFilter: "blur(8px)",
              border: "1.5px solid rgba(255,255,255,0.2)",
            }}
          >
            <Play className="w-5 h-5 text-white ml-0.5" />
          </div>
        </div>
      )}

      {/* Hover actions */}
      <div className="absolute top-2 right-2 flex gap-1.5 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
        <button
          onClick={(e) => {
            e.stopPropagation();
            window.open(item.url, "_blank");
          }}
          className="p-1.5 rounded-lg transition-all duration-150"
          style={{
            background: "rgba(79,140,255,0.85)",
            color: "white",
          }}
          title="Download"
        >
          <Download className="w-3 h-3" />
        </button>
        <button
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
          className="p-1.5 rounded-lg transition-all duration-150"
          style={{
            background: "rgba(239,68,68,0.7)",
            color: "white",
          }}
          title="Delete"
        >
          <Trash2 className="w-3 h-3" />
        </button>
      </div>

      {/* Info on hover (bottom) */}
      {gridSize === "lg" && (
        <div className="absolute bottom-0 left-0 right-0 p-3 opacity-0 group-hover:opacity-100 transition-opacity duration-200">
          <p
            className="text-xs line-clamp-2"
            style={{ color: "rgba(255,255,255,0.9)" }}
          >
            {item.prompt}
          </p>
          <div className="flex items-center gap-2 mt-1.5">
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
      )}
    </motion.div>
  );
}

// ── Lightbox ──────────────────────────────────────────────────────────────────
function Lightbox({
  item,
  onClose,
}: {
  item: GalleryItem;
  onClose: () => void;
}) {
  const TypeIcon = item.type === "video" ? Video : ImageIcon;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-[60] flex items-center justify-center p-8"
      onClick={onClose}
    >
      <div
        className="absolute inset-0"
        style={{ background: "rgba(0,0,0,0.92)", backdropFilter: "blur(24px)" }}
      />

      <motion.div
        initial={{ scale: 0.92, opacity: 0 }}
        animate={{ scale: 1, opacity: 1 }}
        exit={{ scale: 0.92, opacity: 0 }}
        transition={{ type: "spring", damping: 28 }}
        className="relative max-w-5xl w-full flex flex-col gap-4"
        style={{ maxHeight: "calc(100vh - 64px)" }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Media */}
        <div
          className="relative rounded-2xl overflow-hidden"
          style={{
            border: "1px solid rgba(255,255,255,0.1)",
            boxShadow: "0 24px 80px rgba(0,0,0,0.8)",
            height: "70vh",
          }}
        >
          {item.type === "video" ? (
            <VideoPlayer src={item.url} poster={item.thumbnailUrl} className="h-full" />
          ) : (
            <img
              src={item.url}
              alt={item.prompt}
              className="w-full h-full object-contain"
            />
          )}
        </div>

        {/* Info panel */}
        <div
          className="rounded-2xl p-5"
          style={{
            background: "rgba(21,25,34,0.95)",
            border: "1px solid rgba(255,255,255,0.08)",
            backdropFilter: "blur(12px)",
          }}
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1 min-w-0">
              <p className="text-sm line-clamp-2" style={{ color: "#E5E7EB" }}>
                {item.prompt}
              </p>
              <div className="flex items-center gap-4 mt-3 text-xs" style={{ color: "#6B7280" }}>
                <div className="flex items-center gap-1.5">
                  <TypeIcon className="w-3.5 h-3.5" />
                  <span>{item.type === "video" ? "Video" : "Image"}</span>
                </div>
                <span>•</span>
                <span>{item.model}</span>
                <span>•</span>
                <span>{item.width}×{item.height}</span>
                <span>•</span>
                <span>Seed: {item.seed.toString().slice(0, 8)}</span>
              </div>
            </div>

            <div className="flex gap-2 flex-shrink-0">
              <button
                onClick={() => window.open(item.url, "_blank")}
                className="flex items-center gap-2 px-4 py-2 rounded-xl text-sm transition-all duration-150"
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
                className="px-4 py-2 rounded-xl text-sm transition-all duration-150"
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
        </div>
      </motion.div>

      {/* Close button */}
      <button
        onClick={onClose}
        className="absolute top-4 right-4 p-2.5 rounded-xl z-10 transition-all duration-150"
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
