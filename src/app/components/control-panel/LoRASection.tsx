/**
 * LoRASection — Displays LoRA files with enable toggle, strength sliders,
 * compatibility warnings, and refresh button.
 */

import { RefreshCw, AlertTriangle } from "lucide-react";
import type { LoRAFile, LoRASelection } from "../../hooks/useLoRA";
import { RangeSlider } from "../control-panel/ui/RangeSlider";
import { ParamLabel } from "../control-panel/ui/ParamLabel";

const MAX_LORAS = 5;

interface Props {
  files: LoRAFile[];
  selected: LoRASelection[];
  loading: boolean;
  error: string | null;
  scanPath: string | null;
  visible: boolean;
  isRemoteMode: boolean;
  toggleLoRA: (path: string) => void;
  setStrength: (path: string, field: "strength_model" | "strength_clip", value: number) => void;
  refresh: () => void;
  disabled: boolean;
}

export function LoRASection({
  files, selected, loading, error, scanPath, visible,
  isRemoteMode, toggleLoRA, setStrength, refresh, disabled,
}: Props) {
  if (!visible) return null;

  if (isRemoteMode) {
    return (
      <div className="space-y-2">
        <ParamLabel>LoRA</ParamLabel>
        <div
          className="rounded-xl p-3 text-xs"
          style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)", color: "#6b7280" }}
        >
          LoRA доступна только в Local Mode
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="space-y-2">
        <ParamLabel>LoRA</ParamLabel>
        <div className="text-xs" style={{ color: "#6b7280" }}>Сканирование файлов...</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-2">
        <ParamLabel>LoRA</ParamLabel>
        <div className="rounded-xl p-3 text-xs" style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.2)", color: "#fca5a5" }}>
          {error}
        </div>
      </div>
    );
  }

  if (!scanPath) {
    return (
      <div className="space-y-2">
        <ParamLabel>LoRA</ParamLabel>
        <div
          className="rounded-xl p-3 text-xs"
          style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)", color: "#6b7280" }}
        >
          Папка loras/ не найдена
        </div>
      </div>
    );
  }

  const atMax = selected.length >= MAX_LORAS;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <ParamLabel>LoRA ({selected.length}/{MAX_LORAS})</ParamLabel>
        <button
          onClick={refresh}
          disabled={disabled}
          className="p-1 rounded-md transition-colors hover:bg-white/5 disabled:opacity-50"
          title="Обновить"
        >
          <RefreshCw className="w-3.5 h-3.5" style={{ color: "#6b7280" }} />
        </button>
      </div>

      {atMax && (
        <div className="text-[10px] px-1" style={{ color: "#f59e0b" }}>
          Максимум {MAX_LORAS} LoRA одновременно
        </div>
      )}

      {files.length === 0 ? (
        <div
          className="rounded-xl p-3 text-xs"
          style={{ background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)", color: "#6b7280" }}
        >
          Нет совместимых LoRA файлов
        </div>
      ) : (
        <div className="space-y-1.5 max-h-52 overflow-y-auto scrollbar-thin scrollbar-thumb-white/10">
          {files.map((file) => {
            const isSelected = selected.some((s) => s.path === file.path);
            const sel = selected.find((s) => s.path === file.path);
            const isUnknown = file.compatible_base === "unknown";

            return (
              <div
                key={file.path}
                className="rounded-lg p-2 transition-colors"
                style={{
                  background: isSelected ? "rgba(79,140,255,0.08)" : "rgba(255,255,255,0.03)",
                  border: isSelected ? "1px solid rgba(79,140,255,0.25)" : "1px solid rgba(255,255,255,0.06)",
                }}
              >
                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => toggleLoRA(file.path)}
                    disabled={disabled || (!isSelected && atMax)}
                    className="rounded accent-blue-500"
                    style={{ width: 14, height: 14 }}
                  />
                  <div className="flex-1 min-w-0">
                    <div className="text-xs truncate" style={{ color: "#e5e7eb" }}>
                      {file.filename}
                    </div>
                    <div className="text-[10px] flex items-center gap-2" style={{ color: "#6b7280" }}>
                      <span>{file.size_mb} MB</span>
                      <span>{file.path}</span>
                    </div>
                  </div>
                  {isUnknown && (
                    <span title="Переместите в sdxl/ или flux/ для фильтрации">
                      <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" style={{ color: "#f59e0b" }} />
                    </span>
                  )}
                </div>

                {isUnknown && (
                  <div className="text-[10px] mt-1 pl-6" style={{ color: "#f59e0b" }}>
                    Переместите в sdxl/ или flux/ для фильтрации по совместимости
                  </div>
                )}

                {isSelected && sel && (
                  <div className="mt-2 pl-6 space-y-1.5">
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] w-14 flex-shrink-0" style={{ color: "#9ca3af" }}>Model</span>
                      <RangeSlider
                        value={sel.strength_model}
                        onChange={(v) => setStrength(file.path, "strength_model", v)}
                        min={0} max={2} step={0.05}
                        disabled={disabled}
                      />
                      <span className="text-[10px] w-8 text-right" style={{ color: "#9ca3af" }}>
                        {sel.strength_model.toFixed(2)}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="text-[10px] w-14 flex-shrink-0" style={{ color: "#9ca3af" }}>CLIP</span>
                      <RangeSlider
                        value={sel.strength_clip}
                        onChange={(v) => setStrength(file.path, "strength_clip", v)}
                        min={0} max={2} step={0.05}
                        disabled={disabled}
                      />
                      <span className="text-[10px] w-8 text-right" style={{ color: "#9ca3af" }}>
                        {sel.strength_clip.toFixed(2)}
                      </span>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
