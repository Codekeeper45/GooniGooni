import { Sparkles, Clock, Zap, Grid3x3, Settings, Package, Play, Loader2, Power } from "lucide-react";
import { useNavigate } from "react-router";
import { useState, useEffect, useCallback } from "react";
import type React from "react";
import { useGallery } from "../context/GalleryContext";
import { ModelManager } from "./ModelManager";

interface NavbarProps {
  onHistoryClick: () => void;
  historyCount: number;
  onAdminClick?: () => void;
}

export function Navbar({ onHistoryClick, historyCount, onAdminClick }: NavbarProps) {
  const navigate = useNavigate();
  const { gallery } = useGallery();
  const galleryCount = gallery.length;
  const isLocalModelManagerAvailable = import.meta.env.DEV;
  const [modelsOpen, setModelsOpen] = useState(false);

  // ComfyUI status for the launch button
  const [comfyRunning, setComfyRunning] = useState<boolean | null>(null);
  const [comfyFound, setComfyFound] = useState(false);
  const [launching, setLaunching] = useState(false);
  const [launchError, setLaunchError] = useState<string | null>(null);

  const checkComfyStatus = useCallback(async (): Promise<{ running: boolean; error: string | null }> => {
    try {
      const res = await fetch("/local-api/comfyui/status");
      const data = await res.json();
      const running = data.comfyuiRunning ?? false;
      setComfyRunning(running);
      setComfyFound(data.comfyuiFound ?? false);
      if (data.lastLaunchError) setLaunchError(data.lastLaunchError);
      return { running, error: data.lastLaunchError ?? null };
    } catch {
      setComfyRunning(false);
      setComfyFound(false);
      return { running: false, error: null };
    }
  }, []);

  useEffect(() => {
    if (!isLocalModelManagerAvailable) {
      setComfyRunning(false);
      setComfyFound(false);
      return;
    }
    checkComfyStatus();
    const interval = setInterval(checkComfyStatus, 10000);
    return () => clearInterval(interval);
  }, [checkComfyStatus, isLocalModelManagerAvailable]);

  const handleLaunchComfy = async () => {
    if (!isLocalModelManagerAvailable) return;
    setLaunching(true);
    setLaunchError(null);
    try {
      const response = await fetch("/local-api/comfyui/launch", { method: "POST" });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        setLaunchError(data.error || "Не удалось запустить ComfyUI");
        setLaunching(false);
        return;
      }
      // Poll until running or error (max 30 attempts, 2s each = 60s)
      for (let attempt = 0; attempt < 30; attempt++) {
        await new Promise((r) => setTimeout(r, 2000));
        const status = await checkComfyStatus();
        if (status.running) {
          setLaunching(false);
          return;
        }
        if (status.error) {
          setLaunching(false);
          return;
        }
      }
      setLaunchError("ComfyUI не запустился за 60 секунд");
    } catch {
      setLaunchError("Ошибка сети при запуске ComfyUI");
    }
    setLaunching(false);
  };

  return (
    <header
      className="flex-shrink-0 flex items-center px-6 border-b"
      style={{
        height: 64,
        background: "rgba(15,17,23,0.92)",
        backdropFilter: "blur(20px)",
        borderColor: "rgba(255,255,255,0.06)",
        fontFamily: "'Space Grotesk', sans-serif",
      }}
    >
      {/* Logo */}
      <div className="flex items-center gap-2.5">
        <div
          className="w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0"
          style={{
            background: "linear-gradient(135deg, #4F8CFF, #6366F1)",
            boxShadow: "0 0 14px rgba(79,140,255,0.35)",
          }}
        >
          <Sparkles className="w-3.5 h-3.5 text-white" />
        </div>
        <span className="tracking-tight" style={{ color: "#E5E7EB" }}>
          MediaGen
        </span>
        <span
          className="text-[10px] px-1.5 py-0.5 rounded"
          style={{
            background: "rgba(79,140,255,0.08)",
            color: "#4F8CFF",
            border: "1px solid rgba(79,140,255,0.15)",
          }}
        >
          AI
        </span>
      </div>

      <div className="flex-1" />

      {/* Right actions */}
      <div className="flex items-center gap-1">
        {isLocalModelManagerAvailable && (
          <>
            {/* ComfyUI Launch Button */}
            <ComfyUIButton
              running={comfyRunning}
              found={comfyFound}
              launching={launching}
              error={launchError}
              onLaunch={handleLaunchComfy}
            />

            <div className="w-px h-6 mx-1" style={{ background: "rgba(255,255,255,0.06)" }} />

            <NavButton
              icon={<Package className="w-4 h-4" />}
              label="Модели"
              onClick={() => setModelsOpen(true)}
            />
          </>
        )}
        <NavButton
          icon={<Grid3x3 className="w-4 h-4" />}
          label="Галерея"
          badge={galleryCount > 0 ? String(galleryCount > 99 ? "99+" : galleryCount) : undefined}
          onClick={() => navigate("/gallery")}
        />
        <NavButton
          icon={<Clock className="w-4 h-4" />}
          label="История"
          badge={historyCount > 0 ? String(historyCount > 9 ? "9+" : historyCount) : undefined}
          onClick={onHistoryClick}
        />
        <NavButton
          icon={<Zap className="w-4 h-4" />}
          label="100 GPU·s"
        />
        <NavButton
          icon={<Settings className="w-4 h-4" />}
          label="Админ"
          onClick={() => navigate("/admin")}
        />
      </div>

      {/* Model Manager Dialog */}
      {isLocalModelManagerAvailable && modelsOpen && (
        <ModelManager open={modelsOpen} onOpenChange={setModelsOpen} />
      )}
    </header>
  );
}

function NavButton({
  icon,
  label,
  badge,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  badge?: string;
  onClick?: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-all duration-150"
      style={{ color: "#9CA3AF", fontFamily: "'Space Grotesk', sans-serif" }}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = "rgba(255,255,255,0.05)";
        e.currentTarget.style.color = "#E5E7EB";
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = "transparent";
        e.currentTarget.style.color = "#9CA3AF";
      }}
    >
      {icon}
      {label}
      {badge && (
        <span
          className="text-[10px] min-w-[18px] h-[18px] rounded-full flex items-center justify-center px-1"
          style={{ background: "rgba(79,140,255,0.15)", color: "#4F8CFF" }}
        >
          {badge}
        </span>
      )}
    </button>
  );
}

// ─── ComfyUI Launch Button ───────────────────────────────────────────────────

function ComfyUIButton({
  running,
  found,
  launching,
  error,
  onLaunch,
}: {
  running: boolean | null;
  found: boolean;
  launching: boolean;
  error: string | null;
  onLaunch: () => void;
}) {
  // Still loading status
  if (running === null) {
    return (
      <div
        className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm"
        style={{ color: "#4B5563", fontFamily: "'Space Grotesk', sans-serif" }}
      >
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
        <span className="hidden sm:inline">ComfyUI</span>
      </div>
    );
  }

  // Running — green dot
  if (running) {
    return (
      <div
        className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm"
        style={{ color: "#10B981", fontFamily: "'Space Grotesk', sans-serif" }}
      >
        <span className="relative flex h-2.5 w-2.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75" style={{ background: "#10B981" }} />
          <span className="relative inline-flex rounded-full h-2.5 w-2.5" style={{ background: "#10B981" }} />
        </span>
        <span className="hidden sm:inline">ComfyUI</span>
      </div>
    );
  }

  // Error state — red with tooltip
  if (error && !launching) {
    return (
      <button
        onClick={onLaunch}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200"
        style={{
          background: "rgba(239,68,68,0.1)",
          color: "#EF4444",
          border: "1px solid rgba(239,68,68,0.2)",
          fontFamily: "'Space Grotesk', sans-serif",
        }}
        title={`Ошибка: ${error}\nНажмите для повторной попытки`}
      >
        <Power className="w-3.5 h-3.5" />
        <span className="hidden sm:inline">Ошибка</span>
      </button>
    );
  }

  // Not running — show launch button
  return (
    <button
      onClick={onLaunch}
      disabled={launching || !found}
      className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-200 disabled:opacity-40"
      style={{
        background: found
          ? "linear-gradient(135deg, #10B981, #059669)"
          : "rgba(255,255,255,0.03)",
        color: found ? "#fff" : "#4B5563",
        boxShadow: found ? "0 2px 8px rgba(16,185,129,0.25)" : "none",
        border: found ? "none" : "1px solid rgba(255,255,255,0.06)",
        fontFamily: "'Space Grotesk', sans-serif",
      }}
      title={found ? "Запустить ComfyUI" : "ComfyUI не найден — укажите COMFYUI_PATH в .env.local"}
      onMouseEnter={(e) => {
        if (found && !launching) {
          e.currentTarget.style.boxShadow = "0 4px 12px rgba(16,185,129,0.35)";
          e.currentTarget.style.transform = "translateY(-1px)";
        }
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.boxShadow = found ? "0 2px 8px rgba(16,185,129,0.25)" : "none";
        e.currentTarget.style.transform = "none";
      }}
    >
      {launching ? (
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
      ) : (
        <Play className="w-3.5 h-3.5" />
      )}
      <span className="hidden sm:inline">{launching ? "Запуск..." : "ComfyUI"}</span>
    </button>
  );
}
