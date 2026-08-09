import { useEffect, useState } from "react";
import {
  ArrowLeft,
  Download,
  Loader2,
  RefreshCw,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { useNavigate } from "react-router";
import { fetchAsset, type GalleryItem } from "../api";
import { useGallery } from "../context/GalleryContext";

export function GalleryPage() {
  const navigate = useNavigate();
  const { gallery, loading, error, refresh, removeFromGallery, clearGallery } = useGallery();
  const [query, setQuery] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);
  const [selected, setSelected] = useState<GalleryItem | null>(null);
  const [fullUrl, setFullUrl] = useState<string | null>(null);
  const [opening, setOpening] = useState(false);

  const filtered = gallery.filter((item) =>
    item.prompt.toLowerCase().includes(query.toLowerCase()),
  );

  useEffect(() => {
    return () => {
      if (fullUrl) URL.revokeObjectURL(fullUrl);
    };
  }, [fullUrl]);

  const openItem = async (item: GalleryItem) => {
    setSelected(item);
    setOpening(true);
    setActionError(null);
    try {
      const blob = await fetchAsset(item.result_url);
      if (fullUrl) URL.revokeObjectURL(fullUrl);
      setFullUrl(URL.createObjectURL(blob));
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "Could not open image");
      setSelected(null);
    } finally {
      setOpening(false);
    }
  };

  const download = async (item: GalleryItem) => {
    setActionError(null);
    try {
      const blob = await fetchAsset(item.result_url);
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `gooni-${item.id}.${item.output_format === "jpeg" ? "jpg" : "png"}`;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "Download failed");
    }
  };

  const remove = async (id: string) => {
    if (!window.confirm("Delete this image permanently?")) return;
    setActionError(null);
    try {
      await removeFromGallery(id);
      if (selected?.id === id) {
        setSelected(null);
        setFullUrl(null);
      }
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "Delete failed");
    }
  };

  const clear = async () => {
    if (!gallery.length || !window.confirm(`Delete all ${gallery.length} images permanently?`)) {
      return;
    }
    setActionError(null);
    try {
      await clearGallery();
    } catch (caught) {
      setActionError(caught instanceof Error ? caught.message : "Clear failed");
    }
  };

  return (
    <div className="min-h-screen bg-[#0f1117] text-gray-100">
      <header className="sticky top-0 z-20 flex min-h-16 flex-wrap items-center gap-3 border-b border-white/[0.06] bg-[#0f1117]/95 px-4 py-3 backdrop-blur-xl sm:px-6">
        <button
          type="button"
          onClick={() => navigate("/")}
          className="flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-gray-400 hover:bg-white/5 hover:text-gray-200"
        >
          <ArrowLeft className="h-4 w-4" />
          Studio
        </button>
        <div>
          <p className="text-sm text-gray-100">Gallery</p>
          <p className="text-[10px] text-gray-600">{gallery.length} saved images</p>
        </div>
        <div className="flex-1" />
        <label className="relative min-w-[180px] max-w-xs flex-1 sm:flex-none">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-600" />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search prompts"
            className="w-full rounded-xl border border-white/10 bg-white/[0.04] py-2 pl-9 pr-3 text-xs text-gray-200 outline-none focus:border-blue-500/40"
          />
        </label>
        <button
          type="button"
          onClick={() => void refresh()}
          disabled={loading}
          className="rounded-lg p-2 text-gray-400 hover:bg-white/5 disabled:opacity-50"
          title="Refresh gallery"
        >
          <RefreshCw className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
        </button>
        <button
          type="button"
          onClick={() => void clear()}
          disabled={!gallery.length}
          className="flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-red-300 hover:bg-red-500/10 disabled:opacity-30"
        >
          <Trash2 className="h-4 w-4" />
          Clear all
        </button>
      </header>

      {(error || actionError) && (
        <div className="mx-auto mt-5 max-w-7xl px-4 sm:px-6">
          <p className="rounded-xl border border-red-500/20 bg-red-500/[0.08] px-4 py-3 text-xs text-red-300">
            {actionError || error}
          </p>
        </div>
      )}

      <main className="mx-auto max-w-7xl p-4 sm:p-6">
        {loading && gallery.length === 0 ? (
          <div className="flex min-h-[420px] items-center justify-center gap-3 text-sm text-gray-500">
            <Loader2 className="h-5 w-5 animate-spin" />
            Loading gallery...
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex min-h-[420px] flex-col items-center justify-center gap-2 text-center">
            <p className="text-sm text-gray-400">
              {query ? "No prompts match your search" : "No generated images yet"}
            </p>
            <button
              type="button"
              onClick={() => navigate("/")}
              className="mt-3 rounded-xl bg-blue-500/10 px-4 py-2 text-xs text-blue-300 hover:bg-blue-500/15"
            >
              Go to Studio
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {filtered.map((item) => (
              <article
                key={item.id}
                className="group overflow-hidden rounded-2xl border border-white/[0.06] bg-[#151922] transition hover:border-blue-500/25"
              >
                <button
                  type="button"
                  onClick={() => void openItem(item)}
                  className="block aspect-square w-full overflow-hidden bg-black/30"
                >
                  {item.thumbnailObjectUrl ? (
                    <img
                      src={item.thumbnailObjectUrl}
                      alt={item.prompt}
                      className="h-full w-full object-cover transition duration-500 group-hover:scale-[1.03]"
                    />
                  ) : (
                    <div className="flex h-full items-center justify-center text-xs text-gray-600">
                      Preview unavailable
                    </div>
                  )}
                </button>
                <div className="space-y-3 p-3">
                  <p className="line-clamp-2 min-h-8 text-xs leading-relaxed text-gray-300">
                    {item.prompt}
                  </p>
                  <div className="flex items-center justify-between text-[10px] text-gray-600">
                    <span>
                      {item.width}×{item.height} · seed {item.seed}
                    </span>
                    <div className="flex gap-1">
                      <button
                        type="button"
                        onClick={() => void download(item)}
                        className="rounded-lg p-2 text-gray-400 hover:bg-white/5 hover:text-blue-300"
                        title="Download"
                      >
                        <Download className="h-4 w-4" />
                      </button>
                      <button
                        type="button"
                        onClick={() => void remove(item.id)}
                        className="rounded-lg p-2 text-gray-400 hover:bg-red-500/10 hover:text-red-300"
                        title="Delete"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </main>

      {(selected || opening) && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 p-4 backdrop-blur-sm">
          <button
            type="button"
            onClick={() => {
              setSelected(null);
              setFullUrl(null);
            }}
            className="absolute right-5 top-5 rounded-xl bg-white/10 p-2 text-white hover:bg-white/15"
          >
            <X className="h-5 w-5" />
          </button>
          {opening || !fullUrl ? (
            <Loader2 className="h-8 w-8 animate-spin text-blue-400" />
          ) : (
            <img
              src={fullUrl}
              alt={selected?.prompt || "Generated image"}
              className="max-h-[90vh] max-w-[95vw] rounded-xl object-contain"
            />
          )}
        </div>
      )}
    </div>
  );
}
