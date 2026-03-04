/**
 * PresetDialogs.tsx
 * ─────────────────
 * Two dialogs for user model-parameter presets:
 *   1. SavePresetDialog — capture current parameters under a name
 *   2. ManagePresetsDialog — list / edit / delete / import / export
 */

import { useState, useRef, useCallback } from "react";
import { Save, Settings2, Pencil, Trash2, Download, Upload, Check, X } from "lucide-react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
  DialogDescription, DialogFooter,
} from "../ui/dialog";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import {
  getPresets, getPresetsForModel, savePreset, updatePreset,
  deletePreset, exportPresets, importPresets,
  type ModelPreset,
} from "../../utils/presetManager";
import { configManager, type ModelId } from "../../utils/configManager";

/* ────────────────────────────────────────────────
 *  Types shared between the two dialogs
 * ──────────────────────────────────────────────── */

export interface CurrentParams {
  steps: number;
  cfg_scale: number;
  sampler: string;
  scheduler: string;
  width: number;
  height: number;
  clip_skip: number;
}

/* ────────────────────────────────────────────────
 *  SavePresetDialog
 * ──────────────────────────────────────────────── */

interface SavePresetDialogProps {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  modelFile: string;
  currentParams: CurrentParams;
}

export function SavePresetDialog({
  open, onOpenChange, modelFile, currentParams,
}: SavePresetDialogProps) {
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const [success, setSuccess] = useState(false);

  const handleSave = useCallback(() => {
    if (!name.trim()) return;
    setSaving(true);
    try {
      savePreset({
        name: name.trim(),
        model_file: modelFile,
        parameters: { ...currentParams },
      });
      setSuccess(true);
      setTimeout(() => {
        setSuccess(false);
        setName("");
        onOpenChange(false);
      }, 800);
    } finally {
      setSaving(false);
    }
  }, [name, modelFile, currentParams, onOpenChange]);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-zinc-900 border-white/10 text-white max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-white">
            <Save className="size-5" />
            Сохранить пресет
          </DialogTitle>
          <DialogDescription className="text-zinc-400">
            Текущие параметры будут сохранены для модели{" "}
            <span className="text-zinc-300 font-medium">{configManager.getModelLabel("image", modelFile as ModelId)}</span>
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          <label className="text-sm text-zinc-400">Название пресета</label>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Мой пресет"
            className="bg-zinc-800 border-white/10 text-white"
            autoFocus
            onKeyDown={(e) => e.key === "Enter" && handleSave()}
          />

          <div className="rounded border border-white/5 bg-zinc-800/50 p-3 text-xs text-zinc-400 space-y-1">
            <div className="text-zinc-300 font-medium mb-1">Параметры:</div>
            <div>Шаги: {currentParams.steps} · CFG: {currentParams.cfg_scale}</div>
            <div>Сэмплер: {currentParams.sampler} · Планировщик: {currentParams.scheduler}</div>
            <div>Размер: {currentParams.width}×{currentParams.height} · Clip Skip: {currentParams.clip_skip}</div>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            className="border-white/10 text-zinc-400 hover:text-white"
          >
            Отмена
          </Button>
          <Button
            onClick={handleSave}
            disabled={!name.trim() || saving}
            className={success ? "bg-green-600 hover:bg-green-600" : ""}
          >
            {success ? (
              <><Check className="size-4" /> Сохранено</>
            ) : (
              <><Save className="size-4" /> Сохранить</>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/* ────────────────────────────────────────────────
 *  ManagePresetsDialog
 * ──────────────────────────────────────────────── */

interface ManagePresetsDialogProps {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  /** Callback when user selects "apply preset" */
  onApplyPreset?: (preset: ModelPreset) => void;
}

export function ManagePresetsDialog({
  open, onOpenChange, onApplyPreset,
}: ManagePresetsDialogProps) {
  const [presets, setPresets] = useState<ModelPreset[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [importStatus, setImportStatus] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Reload presets whenever dialog opens
  const handleOpenChange = useCallback((v: boolean) => {
    if (v) setPresets(getPresets());
    onOpenChange(v);
  }, [onOpenChange]);

  /* ── Edit ────────────────────────── */
  const startEdit = (p: ModelPreset) => {
    setEditingId(p.id);
    setEditName(p.name);
  };

  const saveEdit = (id: string) => {
    if (!editName.trim()) return;
    updatePreset(id, { name: editName.trim() });
    setPresets(getPresets());
    setEditingId(null);
  };

  const cancelEdit = () => setEditingId(null);

  /* ── Delete ──────────────────────── */
  const handleDelete = (id: string) => {
    deletePreset(id);
    setPresets(getPresets());
    setConfirmDeleteId(null);
  };

  /* ── Export ──────────────────────── */
  const handleExport = () => {
    const json = exportPresets();
    const blob = new Blob([json], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `gooni-presets-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  /* ── Import ──────────────────────── */
  const handleImportClick = () => fileInputRef.current?.click();

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const text = await file.text();
      const count = importPresets(text);
      setPresets(getPresets());
      setImportStatus(`Импортировано пресетов: ${count}`);
      setTimeout(() => setImportStatus(null), 3000);
    } catch (err) {
      setImportStatus(`Ошибка: ${err instanceof Error ? err.message : "Неверный формат файла"}`);
      setTimeout(() => setImportStatus(null), 4000);
    }
    // Reset file input so the same file can be picked again
    e.target.value = "";
  };

  /* ── Group presets by model ──────── */
  const grouped = presets.reduce<Record<string, ModelPreset[]>>((acc, p) => {
    const key = p.model_file;
    if (!acc[key]) acc[key] = [];
    acc[key].push(p);
    return acc;
  }, {});

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="bg-zinc-900 border-white/10 text-white max-w-lg max-h-[80vh] overflow-hidden flex flex-col">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-white">
            <Settings2 className="size-5" />
            Управление пресетами
          </DialogTitle>
          <DialogDescription className="text-zinc-400">
            {presets.length === 0
              ? "Нет сохранённых пресетов"
              : `Всего пресетов: ${presets.length}`}
          </DialogDescription>
        </DialogHeader>

        {/* Scrollable presets list */}
        <div className="flex-1 overflow-y-auto space-y-4 py-2 min-h-0">
          {Object.entries(grouped).map(([modelFile, items]) => (
            <div key={modelFile}>
              <div className="text-xs font-medium text-zinc-500 uppercase tracking-wider mb-2">
                {configManager.getModelLabel("image", modelFile as ModelId)}
              </div>
              <div className="space-y-1">
                {items.map((p) => (
                  <div
                    key={p.id}
                    className="flex items-center gap-2 rounded px-3 py-2 bg-zinc-800/60 hover:bg-zinc-800 transition-colors group"
                  >
                    {/* Name / edit */}
                    {editingId === p.id ? (
                      <div className="flex items-center gap-1 flex-1">
                        <Input
                          value={editName}
                          onChange={(e) => setEditName(e.target.value)}
                          className="h-7 text-sm bg-zinc-700 border-white/10 text-white"
                          autoFocus
                          onKeyDown={(e) => {
                            if (e.key === "Enter") saveEdit(p.id);
                            if (e.key === "Escape") cancelEdit();
                          }}
                        />
                        <Button size="icon" variant="ghost" className="size-7" onClick={() => saveEdit(p.id)}>
                          <Check className="size-3.5 text-green-400" />
                        </Button>
                        <Button size="icon" variant="ghost" className="size-7" onClick={cancelEdit}>
                          <X className="size-3.5 text-zinc-400" />
                        </Button>
                      </div>
                    ) : (
                      <>
                        <div className="flex-1 min-w-0">
                          <div className="text-sm text-white truncate">{p.name}</div>
                          <div className="text-xs text-zinc-500">
                            {p.parameters.steps} шагов · CFG {p.parameters.cfg_scale} · {p.parameters.width}×{p.parameters.height}
                          </div>
                        </div>

                        {/* Actions */}
                        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                          {onApplyPreset && (
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-7 text-xs text-blue-400 hover:text-blue-300"
                              onClick={() => onApplyPreset(p)}
                            >
                              Применить
                            </Button>
                          )}
                          <Button size="icon" variant="ghost" className="size-7" onClick={() => startEdit(p)}>
                            <Pencil className="size-3.5 text-zinc-400 hover:text-white" />
                          </Button>
                          {confirmDeleteId === p.id ? (
                            <div className="flex items-center gap-1">
                              <Button
                                size="icon"
                                variant="ghost"
                                className="size-7"
                                onClick={() => handleDelete(p.id)}
                              >
                                <Check className="size-3.5 text-red-400" />
                              </Button>
                              <Button
                                size="icon"
                                variant="ghost"
                                className="size-7"
                                onClick={() => setConfirmDeleteId(null)}
                              >
                                <X className="size-3.5 text-zinc-400" />
                              </Button>
                            </div>
                          ) : (
                            <Button
                              size="icon"
                              variant="ghost"
                              className="size-7"
                              onClick={() => setConfirmDeleteId(p.id)}
                            >
                              <Trash2 className="size-3.5 text-zinc-400 hover:text-red-400" />
                            </Button>
                          )}
                        </div>
                      </>
                    )}
                  </div>
                ))}
              </div>
            </div>
          ))}

          {presets.length === 0 && (
            <div className="text-center py-8 text-zinc-500 text-sm">
              Пока нет сохранённых пресетов.
              <br />
              Используйте кнопку «Сохранить как пресет» в панели управления.
            </div>
          )}
        </div>

        {/* Import status banner */}
        {importStatus && (
          <div className={`text-xs px-3 py-1.5 rounded ${
            importStatus.startsWith("Ошибка") ? "bg-red-900/30 text-red-400" : "bg-green-900/30 text-green-400"
          }`}>
            {importStatus}
          </div>
        )}

        {/* Hidden file input for import */}
        <input
          ref={fileInputRef}
          type="file"
          accept=".json"
          className="hidden"
          onChange={handleFileChange}
        />

        <DialogFooter className="flex-wrap gap-2">
          <div className="flex gap-2 sm:mr-auto">
            <Button
              variant="outline"
              size="sm"
              onClick={handleExport}
              disabled={presets.length === 0}
              className="border-white/10 text-zinc-400 hover:text-white"
            >
              <Download className="size-3.5" /> Экспорт
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleImportClick}
              className="border-white/10 text-zinc-400 hover:text-white"
            >
              <Upload className="size-3.5" /> Импорт
            </Button>
          </div>
          <Button
            variant="outline"
            onClick={() => onOpenChange(false)}
            className="border-white/10 text-zinc-400 hover:text-white"
          >
            Закрыть
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
