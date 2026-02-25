import { Sparkles, Clock, Zap, Grid3x3, Settings, KeyRound } from "lucide-react";
import { useNavigate } from "react-router";
import { useState } from "react";
import type React from "react";
import { useGallery } from "../context/GalleryContext";
import { SettingsModal } from "./SettingsModal";

interface NavbarProps {
  onHistoryClick: () => void;
  historyCount: number;
  onAdminClick?: () => void;
}

export function Navbar({ onHistoryClick, historyCount, onAdminClick }: NavbarProps) {
  const navigate = useNavigate();
  const { gallery } = useGallery();
  const galleryCount = gallery.length;
  const [showSettings, setShowSettings] = useState(false);

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
        <NavButton
          icon={<Grid3x3 className="w-4 h-4" />}
          label="Gallery"
          badge={galleryCount > 0 ? String(galleryCount > 99 ? "99+" : galleryCount) : undefined}
          onClick={() => navigate("/gallery")}
        />
        <NavButton
          icon={<Clock className="w-4 h-4" />}
          label="History"
          badge={historyCount > 0 ? String(historyCount > 9 ? "9+" : historyCount) : undefined}
          onClick={onHistoryClick}
        />
        <NavButton
          icon={<Zap className="w-4 h-4" />}
          label="100 GPU·s"
        />
        <NavButton
          icon={<KeyRound className="w-4 h-4" />}
          label="API Keys"
          onClick={() => setShowSettings(true)}
        />
        <NavButton
          icon={<Settings className="w-4 h-4" />}
          label="Admin"
          onClick={() => navigate("/admin")}
        />
      </div>

      {showSettings && <SettingsModal onClose={() => setShowSettings(false)} />}
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
