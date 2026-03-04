/**
 * GPUInfoBanner — Displays GPU name, VRAM total/free, driver version,
 * and a color-coded badge based on VRAM level.
 * Also shows CPU-mode warning when device is set to "cpu".
 */

import type { GPUInfo } from "../hooks/useGPUInfo";

const LEVEL_COLORS: Record<string, { bg: string; border: string; text: string; dot: string }> = {
  green:  { bg: "rgba(34,197,94,0.08)",  border: "rgba(34,197,94,0.25)",  text: "#86efac", dot: "🟢" },
  yellow: { bg: "rgba(234,179,8,0.08)",  border: "rgba(234,179,8,0.25)",  text: "#fde68a", dot: "🟡" },
  orange: { bg: "rgba(249,115,22,0.08)", border: "rgba(249,115,22,0.25)", text: "#fdba74", dot: "🟠" },
  red:    { bg: "rgba(239,68,68,0.08)",  border: "rgba(239,68,68,0.25)",  text: "#fca5a5", dot: "🔴" },
};

function formatMB(mb: number): string {
  if (mb >= 1024) return `${(mb / 1024).toFixed(1)} GB`;
  return `${mb} MB`;
}

interface Props {
  gpuInfo: GPUInfo | null;
  loading: boolean;
  error: string | null;
  /** Currently selected device — "gpu" or "cpu" */
  selectedDevice?: string;
  /** Callback when user changes device selection */
  onDeviceChange?: (device: string) => void;
}

export function GPUInfoBanner({ gpuInfo, loading, error, selectedDevice, onDeviceChange }: Props) {
  // CPU-mode warning (T040)
  if (selectedDevice === "cpu") {
    const c = LEVEL_COLORS.orange;
    return (
      <div className="space-y-1.5">
        <div
          className="rounded-xl px-3 py-2 text-xs"
          style={{ background: c.bg, border: `1px solid ${c.border}`, color: c.text }}
        >
          🟠 Генерация на CPU будет очень медленной. Рекомендуем использовать GPU или Remote Mode.
        </div>
        {onDeviceChange && (
          <DeviceSelect
            gpuName={gpuInfo?.name ?? null}
            selectedDevice={selectedDevice}
            onDeviceChange={onDeviceChange}
          />
        )}
      </div>
    );
  }

  if (loading) {
    return (
      <div
        className="rounded-xl px-3 py-2 text-xs"
        style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)", color: "#6b7280" }}
      >
        Определение GPU...
      </div>
    );
  }

  if (error || !gpuInfo) {
    const c = LEVEL_COLORS.red;
    return (
      <div
        className="rounded-xl px-3 py-2 text-xs"
        style={{ background: c.bg, border: `1px solid ${c.border}`, color: c.text }}
      >
        {c.dot} GPU не обнаружена. Рекомендуем использовать Remote Mode
      </div>
    );
  }

  if (!gpuInfo.detected) {
    const c = LEVEL_COLORS.red;
    return (
      <div
        className="rounded-xl px-3 py-2 text-xs"
        style={{ background: c.bg, border: `1px solid ${c.border}`, color: c.text }}
      >
        {c.dot} GPU не обнаружена. Рекомендуем использовать Remote Mode
      </div>
    );
  }

  const c = LEVEL_COLORS[gpuInfo.vram_level] ?? LEVEL_COLORS.red;

  return (
    <div className="space-y-1.5">
      <div
        className="rounded-xl px-3 py-2 text-xs space-y-0.5"
        style={{ background: c.bg, border: `1px solid ${c.border}`, color: c.text }}
      >
        <div className="flex items-center gap-1.5 font-semibold">
          <span>{c.dot}</span>
          <span>{gpuInfo.name}</span>
        </div>
        <div className="flex items-center gap-3 text-[10px]" style={{ color: "rgba(255,255,255,0.5)" }}>
          {gpuInfo.vram_total_mb != null && (
            <span>VRAM: {formatMB(gpuInfo.vram_total_mb)}</span>
          )}
          {gpuInfo.vram_free_mb != null && (
            <span>Свободно: {formatMB(gpuInfo.vram_free_mb)}</span>
          )}
          {gpuInfo.driver_version && (
            <span>Driver: {gpuInfo.driver_version}</span>
          )}
          {gpuInfo.cuda_version && (
            <span>CUDA: {gpuInfo.cuda_version}</span>
          )}
        </div>
      </div>
      {onDeviceChange && (
        <DeviceSelect
          gpuName={gpuInfo.name}
          selectedDevice={selectedDevice ?? "gpu"}
          onDeviceChange={onDeviceChange}
        />
      )}
    </div>
  );
}

/* ── Small inline device selector ─────────── */

function DeviceSelect({
  gpuName,
  selectedDevice,
  onDeviceChange,
}: {
  gpuName: string | null;
  selectedDevice: string;
  onDeviceChange: (d: string) => void;
}) {
  return (
    <div className="flex items-center gap-2 text-xs text-zinc-400">
      <span>Устройство:</span>
      <select
        value={selectedDevice}
        onChange={(e) => onDeviceChange(e.target.value)}
        className="bg-zinc-800 border border-white/10 rounded px-2 py-0.5 text-xs text-white outline-none focus:border-blue-500"
      >
        <option value="gpu">{gpuName ?? "GPU"}</option>
        <option value="cpu">CPU</option>
      </select>
    </div>
  );
}
