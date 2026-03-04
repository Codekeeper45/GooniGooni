/**
 * ModelManager — Full-screen dialog for managing ComfyUI models.
 *
 * Tabs:
 *  1. Рекомендуемые — pre-configured models with one-click install
 *  2. Установленные — installed models with delete option
 *  3. CivitAI — search and download from CivitAI
 *  4. Ссылка — paste any URL to download
 */

import { useState, useCallback, useEffect } from "react";
import {
  Download, Trash2, Search, Link, CheckCircle2, XCircle, Loader2,
  HardDrive, AlertTriangle, RefreshCw, ExternalLink, Star, Package,
  Play, Power, Film,
} from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "./ui/dialog";
import { Progress } from "./ui/progress";
import { useModelManager, type CivitAIModel, type RecommendedModel } from "../hooks/useModelManager";

// ─── Types ───────────────────────────────────────────────────────────────────

type Tab = "recommended" | "installed" | "civitai" | "url";

interface ModelManagerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// ─── Component ───────────────────────────────────────────────────────────────

export function ModelManager({ open, onOpenChange }: ModelManagerProps) {
  const [tab, setTab] = useState<Tab>("recommended");

  const {
    installedModels, downloads, loading, comfyStatus,
    searchResults, searching, searchError,
    refreshModels, downloadModel, cancelDownload, deleteModel,
    searchCivitAI, checkStatus, isModelInstalled,
    recommendedModels, launchComfyUI,
  } = useModelManager();

  // Refresh when dialog opens
  useEffect(() => {
    if (open) {
      refreshModels();
      checkStatus();
    }
  }, [open]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-3xl max-h-[85vh] overflow-hidden flex flex-col"
        style={{
          background: "#0F1117",
          border: "1px solid rgba(255,255,255,0.08)",
          color: "#E5E7EB",
          fontFamily: "'Space Grotesk', sans-serif",
        }}
      >
        <DialogHeader>
          <DialogTitle className="text-lg font-semibold" style={{ color: "#E5E7EB" }}>
            <div className="flex items-center gap-2">
              <Package className="w-5 h-5" style={{ color: "#4F8CFF" }} />
              Управление моделями
            </div>
          </DialogTitle>
          <DialogDescription className="text-sm" style={{ color: "#6B7280" }}>
            Скачивайте и управляйте моделями для генерации изображений
          </DialogDescription>
        </DialogHeader>

        {/* ComfyUI Status Banner */}
        <ComfyUIStatusBanner comfyStatus={comfyStatus} onLaunch={launchComfyUI} onRefresh={checkStatus} />

        {/* Active Downloads Banner */}
        <ActiveDownloads downloads={downloads} onCancel={cancelDownload} />

        {/* Tabs */}
        <div
          className="flex gap-1 p-1 rounded-xl"
          style={{ background: "#1C212C", border: "1px solid rgba(255,255,255,0.05)" }}
        >
          {([
            { id: "recommended" as Tab, label: "Рекомендуемые", icon: Star },
            { id: "installed" as Tab, label: "Установленные", icon: HardDrive },
            { id: "civitai" as Tab, label: "CivitAI", icon: Search },
            { id: "url" as Tab, label: "Ссылка", icon: Link },
          ]).map((t) => (
            <button
              key={t.id}
              onClick={() => setTab(t.id)}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm transition-all duration-200 flex-1 justify-center"
              style={
                tab === t.id
                  ? { background: "#151922", border: "1px solid rgba(79,140,255,0.2)", color: "#E5E7EB", boxShadow: "0 2px 8px rgba(0,0,0,0.3)" }
                  : { background: "transparent", border: "1px solid transparent", color: "#4B5563" }
              }
            >
              <t.icon className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">{t.label}</span>
            </button>
          ))}
        </div>

        {/* Tab Content */}
        <div className="flex-1 overflow-y-auto min-h-0" style={{ maxHeight: "50vh" }}>
          {tab === "recommended" && (
            <RecommendedTab
              models={recommendedModels}
              isInstalled={isModelInstalled}
              onDownload={downloadModel}
            />
          )}
          {tab === "installed" && (
            <InstalledTab
              models={installedModels}
              loading={loading}
              onDelete={deleteModel}
              onRefresh={refreshModels}
              checkpointsDir={comfyStatus?.checkpointsDir}
            />
          )}
          {tab === "civitai" && (
            <CivitAITab
              results={searchResults}
              searching={searching}
              error={searchError}
              onSearch={searchCivitAI}
              onDownload={downloadModel}
              isInstalled={isModelInstalled}
            />
          )}
          {tab === "url" && (
            <UrlDownloadTab onDownload={downloadModel} />
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ─── ComfyUI Status Banner ───────────────────────────────────────────────────

function ComfyUIStatusBanner({
  comfyStatus,
  onLaunch,
  onRefresh,
}: {
  comfyStatus: { comfyuiFound: boolean; comfyuiPath: string | null; checkpointsDir: string | null; comfyuiRunning?: boolean } | null;
  onLaunch: () => Promise<any>;
  onRefresh: () => Promise<void>;
}) {
  const [launching, setLaunching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!comfyStatus) return null;

  const handleLaunch = async () => {
    setLaunching(true);
    setError(null);
    try {
      await onLaunch();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLaunching(false);
    }
  };

  // ComfyUI is running — green banner
  if (comfyStatus.comfyuiRunning) {
    return (
      <div
        className="flex items-center gap-2 p-3 rounded-lg text-sm"
        style={{ background: "rgba(16,185,129,0.08)", border: "1px solid rgba(16,185,129,0.2)", color: "#10B981" }}
      >
        <Power className="w-4 h-4 flex-shrink-0" />
        <span className="flex-1">ComfyUI запущен на <b>127.0.0.1:8188</b></span>
        <button
          onClick={onRefresh}
          className="p-1 rounded hover:bg-white/5 transition-colors"
          title="Обновить статус"
        >
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>
    );
  }

  // ComfyUI not found
  if (!comfyStatus.comfyuiFound) {
    return (
      <div
        className="flex items-center gap-2 p-3 rounded-lg text-sm"
        style={{ background: "rgba(245,158,11,0.1)", border: "1px solid rgba(245,158,11,0.2)", color: "#F59E0B" }}
      >
        <AlertTriangle className="w-4 h-4 flex-shrink-0" />
        <span>
          ComfyUI не найден. Укажите путь через переменную <code className="px-1 py-0.5 rounded" style={{ background: "rgba(255,255,255,0.05)" }}>COMFYUI_PATH</code> в .env.local
        </span>
      </div>
    );
  }

  // ComfyUI found but not running — show launch button
  return (
    <div
      className="flex items-center gap-2 p-3 rounded-lg text-sm"
      style={{ background: "rgba(79,140,255,0.05)", border: "1px solid rgba(79,140,255,0.1)", color: "#9CA3AF" }}
    >
      <Power className="w-4 h-4 flex-shrink-0" style={{ color: "#4B5563" }} />
      <span className="flex-1">ComfyUI не запущен</span>
      {error && <span className="text-xs" style={{ color: "#EF4444" }}>{error}</span>}
      <button
        onClick={handleLaunch}
        disabled={launching}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all"
        style={{
          background: "linear-gradient(135deg, #10B981, #059669)",
          color: "#fff",
          boxShadow: "0 2px 6px rgba(16,185,129,0.25)",
        }}
      >
        {launching ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin" />
        ) : (
          <Play className="w-3.5 h-3.5" />
        )}
        Запустить ComfyUI
      </button>
    </div>
  );
}

// ─── Active Downloads ────────────────────────────────────────────────────────

function ActiveDownloads({
  downloads,
  onCancel,
}: {
  downloads: Array<{ id: string; filename: string; percentage: number; status: string; error?: string }>;
  onCancel: (id: string) => void;
}) {
  const active = downloads.filter((d) => d.status === "downloading");
  if (active.length === 0) return null;

  return (
    <div className="space-y-2">
      {active.map((d) => (
        <div
          key={d.id}
          className="flex items-center gap-3 p-3 rounded-lg"
          style={{ background: "rgba(79,140,255,0.05)", border: "1px solid rgba(79,140,255,0.1)" }}
        >
          <Loader2 className="w-4 h-4 animate-spin" style={{ color: "#4F8CFF" }} />
          <div className="flex-1 min-w-0">
            <div className="text-sm truncate" style={{ color: "#E5E7EB" }}>{d.filename}</div>
            <Progress value={d.percentage} className="h-1.5 mt-1" />
          </div>
          <span className="text-xs tabular-nums" style={{ color: "#6B7280" }}>{d.percentage}%</span>
          <button
            onClick={() => onCancel(d.id)}
            className="p-1 rounded hover:bg-white/5 transition-colors"
            style={{ color: "#6B7280" }}
          >
            <XCircle className="w-4 h-4" />
          </button>
        </div>
      ))}
    </div>
  );
}

// ─── Recommended Tab ─────────────────────────────────────────────────────────

function RecommendedTab({
  models,
  isInstalled,
  onDownload,
}: {
  models: RecommendedModel[];
  isInstalled: (filename: string) => boolean;
  onDownload: (url: string, filename: string) => Promise<any>;
}) {
  return (
    <div className="space-y-3 py-2">
      <p className="text-sm" style={{ color: "#6B7280" }}>
        Эти модели нужны для работы генерации. Нажмите «Скачать» для автоматической установки.
      </p>
      {models.map((model) => {
        const installed = isInstalled(model.filename);
        return (
          <RecommendedModelCard
            key={model.id}
            model={model}
            installed={installed}
            onDownload={onDownload}
          />
        );
      })}
    </div>
  );
}

function RecommendedModelCard({
  model,
  installed,
  onDownload,
}: {
  model: RecommendedModel;
  installed: boolean;
  onDownload: (url: string, filename: string) => Promise<any>;
}) {
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleDownload = async () => {
    setDownloading(true);
    setError(null);
    try {
      await onDownload(model.downloadUrl, model.filename);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div
      className="p-4 rounded-xl transition-all"
      style={{
        background: installed ? "rgba(16,185,129,0.05)" : "rgba(255,255,255,0.02)",
        border: installed ? "1px solid rgba(16,185,129,0.15)" : "1px solid rgba(255,255,255,0.06)",
      }}
    >
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="font-medium text-sm" style={{ color: "#E5E7EB" }}>{model.name}</h3>
            {/* Type badge — video or image */}
            {model.requiredBy.includes("видео") ? (
              <span className="flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded"
                style={{ background: "rgba(168,85,247,0.1)", color: "#A855F7", border: "1px solid rgba(168,85,247,0.2)" }}>
                <Film className="w-2.5 h-2.5" /> Видео
              </span>
            ) : (
              <span className="text-[10px] px-1.5 py-0.5 rounded"
                style={{ background: "rgba(79,140,255,0.08)", color: "#4F8CFF", border: "1px solid rgba(79,140,255,0.15)" }}>
                🖼 Фото
              </span>
            )}
            {installed && (
              <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full"
                style={{ background: "rgba(16,185,129,0.1)", color: "#10B981" }}>
                <CheckCircle2 className="w-3 h-3" /> Установлена
              </span>
            )}
          </div>
          <p className="text-xs mt-1" style={{ color: "#6B7280" }}>{model.description}</p>
          <div className="flex items-center gap-3 mt-2">
            <span className="text-xs" style={{ color: "#4B5563" }}>📦 {model.sizeFormatted}</span>
            <span className="text-xs" style={{ color: "#4B5563" }}>🎨 Для: {model.requiredBy}</span>
            {model.civitaiUrl && (
              <a href={model.civitaiUrl} target="_blank" rel="noopener noreferrer"
                className="flex items-center gap-1 text-xs hover:underline" style={{ color: "#4F8CFF" }}>
                <ExternalLink className="w-3 h-3" /> CivitAI
              </a>
            )}
            {model.huggingfaceUrl && (
              <a href={model.huggingfaceUrl} target="_blank" rel="noopener noreferrer"
                className="flex items-center gap-1 text-xs hover:underline" style={{ color: "#4F8CFF" }}>
                <ExternalLink className="w-3 h-3" /> HuggingFace
              </a>
            )}
          </div>
          {error && (
            <p className="text-xs mt-2" style={{ color: "#EF4444" }}>❌ {error}</p>
          )}
        </div>
        <div>
          {!installed && (
            <button
              onClick={handleDownload}
              disabled={downloading}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all disabled:opacity-50"
              style={{
                background: "linear-gradient(135deg, #4F8CFF, #6366F1)",
                color: "#fff",
                boxShadow: "0 2px 8px rgba(79,140,255,0.25)",
              }}
            >
              {downloading ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Download className="w-4 h-4" />
              )}
              Скачать
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Installed Tab ───────────────────────────────────────────────────────────

function InstalledTab({
  models,
  loading,
  onDelete,
  onRefresh,
  checkpointsDir,
}: {
  models: Array<{ filename: string; sizeFormatted: string; modifiedAt: string }>;
  loading: boolean;
  onDelete: (filename: string) => Promise<void>;
  onRefresh: () => Promise<void>;
  checkpointsDir?: string | null;
}) {
  const [deleting, setDeleting] = useState<string | null>(null);

  const handleDelete = async (filename: string) => {
    if (!confirm(`Удалить модель ${filename}? Это действие нельзя отменить.`)) return;
    setDeleting(filename);
    try {
      await onDelete(filename);
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div className="space-y-3 py-2">
      <div className="flex items-center justify-between">
        <p className="text-sm" style={{ color: "#6B7280" }}>
          {models.length} {models.length === 1 ? "модель" : "моделей"} установлено
        </p>
        <button
          onClick={() => onRefresh()}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs transition-all hover:bg-white/5"
          style={{ color: "#6B7280" }}
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          Обновить
        </button>
      </div>

      {checkpointsDir && (
        <p className="text-xs truncate" style={{ color: "#374151" }}>
          📁 {checkpointsDir}
        </p>
      )}

      {models.length === 0 ? (
        <div className="text-center py-8" style={{ color: "#4B5563" }}>
          <HardDrive className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p className="text-sm">Нет установленных моделей</p>
          <p className="text-xs mt-1">Перейдите на вкладку «Рекомендуемые» для начала</p>
        </div>
      ) : (
        <div className="space-y-2">
          {models.map((model) => (
            <div
              key={model.filename}
              className="flex items-center gap-3 p-3 rounded-lg"
              style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)" }}
            >
              <HardDrive className="w-4 h-4 flex-shrink-0" style={{ color: "#4B5563" }} />
              <div className="flex-1 min-w-0">
                <p className="text-sm truncate" style={{ color: "#E5E7EB" }}>{model.filename}</p>
                <p className="text-xs" style={{ color: "#4B5563" }}>{model.sizeFormatted}</p>
              </div>
              <button
                onClick={() => handleDelete(model.filename)}
                disabled={deleting === model.filename}
                className="p-2 rounded-lg hover:bg-red-500/10 transition-colors"
                style={{ color: "#6B7280" }}
                title="Удалить модель"
              >
                {deleting === model.filename ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Trash2 className="w-4 h-4" />
                )}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ─── CivitAI Tab ─────────────────────────────────────────────────────────────

function CivitAITab({
  results,
  searching,
  error,
  onSearch,
  onDownload,
  isInstalled,
}: {
  results: CivitAIModel[];
  searching: boolean;
  error: string | null;
  onSearch: (q: string) => Promise<void>;
  onDownload: (url: string, filename: string) => Promise<any>;
  isInstalled: (filename: string) => boolean;
}) {
  const [query, setQuery] = useState("");
  const [downloading, setDownloading] = useState<number | null>(null);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    onSearch(query);
  };

  const handleDownload = async (model: CivitAIModel) => {
    const version = model.modelVersions?.[0];
    if (!version) return;
    const file = version.files?.find((f) => f.name.endsWith(".safetensors")) || version.files?.[0];
    if (!file) return;

    setDownloading(model.id);
    try {
      await onDownload(file.downloadUrl, file.name);
    } catch {}
    setDownloading(null);
  };

  return (
    <div className="space-y-3 py-2">
      <form onSubmit={handleSearch} className="flex gap-2">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4" style={{ color: "#4B5563" }} />
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Поиск моделей на CivitAI..."
            className="w-full pl-9 pr-3 py-2 rounded-lg text-sm outline-none focus:ring-1"
            style={{
              background: "#1C212C",
              border: "1px solid rgba(255,255,255,0.08)",
              color: "#E5E7EB",
            }}
          />
        </div>
        <button
          type="submit"
          disabled={searching || !query.trim()}
          className="px-4 py-2 rounded-lg text-sm font-medium transition-all disabled:opacity-50"
          style={{ background: "#4F8CFF", color: "#fff" }}
        >
          {searching ? <Loader2 className="w-4 h-4 animate-spin" /> : "Найти"}
        </button>
      </form>

      {error && (
        <p className="text-xs" style={{ color: "#EF4444" }}>❌ {error}</p>
      )}

      {results.length === 0 && !searching ? (
        <div className="text-center py-8" style={{ color: "#4B5563" }}>
          <Search className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p className="text-sm">Введите запрос для поиска моделей</p>
          <p className="text-xs mt-1">Например: «anime», «realistic», «pixel art»</p>
        </div>
      ) : (
        <div className="space-y-2">
          {results.map((model) => (
            <CivitAIModelCard
              key={model.id}
              model={model}
              onDownload={() => handleDownload(model)}
              downloading={downloading === model.id}
              isInstalled={isInstalled}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function CivitAIModelCard({
  model,
  onDownload,
  downloading,
  isInstalled,
}: {
  model: CivitAIModel;
  onDownload: () => void;
  downloading: boolean;
  isInstalled: (filename: string) => boolean;
}) {
  const version = model.modelVersions?.[0];
  const file = version?.files?.find((f) => f.name.endsWith(".safetensors")) || version?.files?.[0];
  const previewImage = version?.images?.[0];
  const installed = file ? isInstalled(file.name) : false;

  return (
    <div
      className="flex gap-3 p-3 rounded-lg"
      style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)" }}
    >
      {/* Preview */}
      {previewImage && previewImage.nsfw === "None" && (
        <div className="w-16 h-16 rounded-lg overflow-hidden flex-shrink-0" style={{ background: "#1C212C" }}>
          <img
            src={previewImage.url}
            alt=""
            className="w-full h-full object-cover"
            loading="lazy"
          />
        </div>
      )}

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <h4 className="text-sm font-medium truncate" style={{ color: "#E5E7EB" }}>{model.name}</h4>
          {installed && (
            <CheckCircle2 className="w-3.5 h-3.5 flex-shrink-0" style={{ color: "#10B981" }} />
          )}
        </div>
        <div className="flex items-center gap-3 mt-1">
          {model.creator && (
            <span className="text-xs" style={{ color: "#4B5563" }}>👤 {model.creator.username}</span>
          )}
          {model.stats && (
            <span className="text-xs" style={{ color: "#4B5563" }}>
              ⬇️ {(model.stats.downloadCount / 1000).toFixed(0)}K
            </span>
          )}
          {file && (
            <span className="text-xs" style={{ color: "#4B5563" }}>
              📦 {(file.sizeKB / 1024 / 1024).toFixed(1)} GB
            </span>
          )}
          <a
            href={`https://civitai.com/models/${model.id}`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 text-xs hover:underline"
            style={{ color: "#4F8CFF" }}
          >
            <ExternalLink className="w-3 h-3" />
          </a>
        </div>
      </div>

      {!installed && file && (
        <button
          onClick={onDownload}
          disabled={downloading}
          className="self-center flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all disabled:opacity-50"
          style={{ background: "#4F8CFF", color: "#fff" }}
        >
          {downloading ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
          Скачать
        </button>
      )}
    </div>
  );
}

// ─── URL Download Tab ────────────────────────────────────────────────────────

function UrlDownloadTab({
  onDownload,
}: {
  onDownload: (url: string, filename: string) => Promise<any>;
}) {
  const [url, setUrl] = useState("");
  const [filename, setFilename] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  // Auto-extract filename from URL
  useEffect(() => {
    if (!url) return;
    try {
      const urlObj = new URL(url);
      const pathParts = urlObj.pathname.split("/");
      const lastPart = pathParts[pathParts.length - 1];
      if (lastPart && (lastPart.endsWith(".safetensors") || lastPart.endsWith(".ckpt"))) {
        setFilename(lastPart);
      }
    } catch {}
  }, [url]);

  const handleDownload = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url || !filename) return;

    // Ensure file extension
    let finalFilename = filename;
    if (!finalFilename.endsWith(".safetensors") && !finalFilename.endsWith(".ckpt")) {
      finalFilename += ".safetensors";
    }

    setDownloading(true);
    setError(null);
    setSuccess(false);
    try {
      await onDownload(url, finalFilename);
      setSuccess(true);
      setUrl("");
      setFilename("");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setDownloading(false);
    }
  };

  return (
    <div className="space-y-4 py-2">
      <p className="text-sm" style={{ color: "#6B7280" }}>
        Вставьте прямую ссылку на файл модели (.safetensors или .ckpt)
      </p>

      <form onSubmit={handleDownload} className="space-y-3">
        <div>
          <label className="text-xs font-medium mb-1 block" style={{ color: "#9CA3AF" }}>URL модели</label>
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://civitai.com/api/download/models/... или https://huggingface.co/..."
            className="w-full px-3 py-2 rounded-lg text-sm outline-none focus:ring-1"
            style={{
              background: "#1C212C",
              border: "1px solid rgba(255,255,255,0.08)",
              color: "#E5E7EB",
            }}
          />
        </div>

        <div>
          <label className="text-xs font-medium mb-1 block" style={{ color: "#9CA3AF" }}>Имя файла</label>
          <input
            type="text"
            value={filename}
            onChange={(e) => setFilename(e.target.value)}
            placeholder="my_model.safetensors"
            className="w-full px-3 py-2 rounded-lg text-sm outline-none focus:ring-1"
            style={{
              background: "#1C212C",
              border: "1px solid rgba(255,255,255,0.08)",
              color: "#E5E7EB",
            }}
          />
        </div>

        {error && <p className="text-xs" style={{ color: "#EF4444" }}>❌ {error}</p>}
        {success && <p className="text-xs" style={{ color: "#10B981" }}>✅ Загрузка началась! Прогресс отображается сверху.</p>}

        <button
          type="submit"
          disabled={downloading || !url || !filename}
          className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all disabled:opacity-50 w-full justify-center"
          style={{
            background: "linear-gradient(135deg, #4F8CFF, #6366F1)",
            color: "#fff",
          }}
        >
          {downloading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Download className="w-4 h-4" />
          )}
          Скачать модель
        </button>
      </form>
    </div>
  );
}
