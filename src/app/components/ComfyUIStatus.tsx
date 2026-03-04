/**
 * ComfyUI connection status indicator — green/yellow/red dot with label.
 * Only rendered when Local Mode is available.
 *
 * @module ComfyUIStatus
 */

import React from "react";
import type { ComfyUIStatus as StatusType } from "../hooks/useComfyUIAvailability";

// ═══════════════════════════════════════════════════════════════════════════════
// Props
// ═══════════════════════════════════════════════════════════════════════════════

interface ComfyUIStatusProps {
  /** Current connection status */
  status: StatusType;
  /** Optional click handler (e.g. manual reconnect) */
  onClick?: () => void;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Status configuration
// ═══════════════════════════════════════════════════════════════════════════════

const STATUS_CONFIG: Record<
  StatusType,
  { color: string; pulseColor: string; label: string; animate: boolean }
> = {
  connected: {
    color: "#22c55e",
    pulseColor: "rgba(34,197,94,0.4)",
    label: "ComfyUI подключён",
    animate: false,
  },
  checking: {
    color: "#eab308",
    pulseColor: "rgba(234,179,8,0.4)",
    label: "Проверка ComfyUI...",
    animate: true,
  },
  disconnected: {
    color: "#ef4444",
    pulseColor: "rgba(239,68,68,0.4)",
    label: "ComfyUI отключён",
    animate: false,
  },
};

// ═══════════════════════════════════════════════════════════════════════════════
// Component
// ═══════════════════════════════════════════════════════════════════════════════

export const ComfyUIStatus: React.FC<ComfyUIStatusProps> = ({
  status,
  onClick,
}) => {
  const config = STATUS_CONFIG[status];

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!onClick}
      className="flex items-center gap-2 px-2 py-1 rounded-md transition-colors hover:bg-white/5 disabled:cursor-default"
      title={config.label}
      aria-label={config.label}
    >
      {/* Status dot */}
      <span className="relative flex h-2.5 w-2.5">
        {config.animate && (
          <span
            className="absolute inline-flex h-full w-full rounded-full opacity-75 animate-ping"
            style={{ backgroundColor: config.pulseColor }}
          />
        )}
        <span
          className="relative inline-flex rounded-full h-2.5 w-2.5"
          style={{ backgroundColor: config.color }}
        />
      </span>

      {/* Label */}
      <span className="text-xs text-gray-400 select-none">{config.label}</span>
    </button>
  );
};
