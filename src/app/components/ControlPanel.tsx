import { Dices, ImagePlus, Sparkles, Trash2 } from "lucide-react";
import { PONY_CONTRACT, type ImageMode, type OutputFormat, type Sampler } from "../api";

export interface GenerationForm {
  mode: ImageMode;
  prompt: string;
  negativePrompt: string;
  width: number;
  height: number;
  steps: number;
  cfgScale: number;
  sampler: Sampler;
  clipSkip: number;
  denoisingStrength: number;
  seed: number;
  outputFormat: OutputFormat;
  referenceImage: string | null;
  referenceName: string | null;
}

interface ControlPanelProps {
  form: GenerationForm;
  disabled: boolean;
  validationError: string | null;
  onChange: <K extends keyof GenerationForm>(key: K, value: GenerationForm[K]) => void;
  onReferenceFile: (file: File | null) => void;
  onGenerate: () => void;
}

const inputClass =
  "w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5 text-sm text-gray-200 outline-none transition focus:border-blue-500/60 focus:bg-white/[0.06]";

function RangeField({
  label,
  value,
  min,
  max,
  step,
  disabled,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  disabled: boolean;
  onChange: (value: number) => void;
}) {
  return (
    <label className="block space-y-2">
      <div className="flex items-center justify-between text-xs">
        <span className="text-gray-400">{label}</span>
        <span className="rounded-md bg-white/5 px-2 py-0.5 text-blue-300">{value}</span>
      </div>
      <input
        type="range"
        value={value}
        min={min}
        max={max}
        step={step}
        disabled={disabled}
        onChange={(event) => onChange(Number(event.target.value))}
        className="w-full accent-blue-500 disabled:opacity-50"
      />
    </label>
  );
}

export function ControlPanel({
  form,
  disabled,
  validationError,
  onChange,
  onReferenceFile,
  onGenerate,
}: ControlPanelProps) {
  const { limits } = PONY_CONTRACT;

  return (
    <aside className="w-full overflow-y-auto border-r border-white/[0.06] bg-[#151922] lg:w-[430px] lg:flex-none">
      <div className="space-y-6 p-5">
        <section>
          <p className="mb-3 text-[11px] uppercase tracking-[0.18em] text-gray-500">Model</p>
          <div className="rounded-xl border border-blue-500/25 bg-blue-500/[0.08] p-3">
            <div className="flex items-center gap-3">
              <div className="rounded-lg bg-blue-500/15 p-2 text-blue-400">
                <Sparkles className="h-4 w-4" />
              </div>
              <div>
                <p className="text-sm text-gray-100">Pony Diffusion V6 XL</p>
                <p className="text-xs text-gray-500">Single supported image pipeline</p>
              </div>
            </div>
          </div>
        </section>

        <section>
          <p className="mb-3 text-[11px] uppercase tracking-[0.18em] text-gray-500">Mode</p>
          <div className="grid grid-cols-2 gap-2 rounded-xl bg-black/20 p-1">
            {(["txt2img", "img2img"] as ImageMode[]).map((mode) => (
              <button
                key={mode}
                type="button"
                disabled={disabled}
                onClick={() => onChange("mode", mode)}
                className={`rounded-lg px-3 py-2 text-xs transition ${
                  form.mode === mode
                    ? "bg-blue-500 text-white shadow-lg shadow-blue-500/20"
                    : "text-gray-400 hover:bg-white/5 hover:text-gray-200"
                }`}
              >
                {mode === "txt2img" ? "Text to image" : "Image to image"}
              </button>
            ))}
          </div>
        </section>

        <section className="space-y-4">
          <label className="block space-y-2">
            <span className="text-xs text-gray-400">Prompt</span>
            <textarea
              value={form.prompt}
              maxLength={limits.prompt_max_length}
              rows={5}
              disabled={disabled}
              onChange={(event) => onChange("prompt", event.target.value)}
              placeholder="score_9, score_8_up, detailed anime illustration..."
              className={`${inputClass} resize-y`}
            />
            <span className="block text-right text-[10px] text-gray-600">
              {form.prompt.length}/{limits.prompt_max_length}
            </span>
          </label>
          <label className="block space-y-2">
            <span className="text-xs text-gray-400">Negative prompt</span>
            <textarea
              value={form.negativePrompt}
              maxLength={limits.negative_prompt_max_length}
              rows={3}
              disabled={disabled}
              onChange={(event) => onChange("negativePrompt", event.target.value)}
              placeholder="low quality, blurry, malformed hands..."
              className={`${inputClass} resize-y`}
            />
          </label>
        </section>

        {form.mode === "img2img" && (
          <section className="space-y-3">
            <p className="text-xs text-gray-400">Reference image</p>
            {form.referenceImage ? (
              <div className="relative overflow-hidden rounded-xl border border-white/10">
                <img
                  src={form.referenceImage}
                  alt="Reference"
                  className="h-48 w-full object-cover"
                />
                <div className="absolute inset-x-0 bottom-0 flex items-center justify-between bg-black/70 px-3 py-2">
                  <span className="max-w-[280px] truncate text-xs text-gray-300">
                    {form.referenceName}
                  </span>
                  <button
                    type="button"
                    disabled={disabled}
                    onClick={() => onReferenceFile(null)}
                    className="rounded-lg p-1.5 text-red-300 hover:bg-red-500/15"
                    aria-label="Remove reference image"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            ) : (
              <label className="flex cursor-pointer flex-col items-center gap-2 rounded-xl border border-dashed border-white/15 p-6 text-gray-500 transition hover:border-blue-500/40 hover:bg-blue-500/5">
                <ImagePlus className="h-6 w-6" />
                <span className="text-xs">Upload PNG, JPEG or WebP up to 10 MB</span>
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  disabled={disabled}
                  onChange={(event) => onReferenceFile(event.target.files?.[0] || null)}
                  className="hidden"
                />
              </label>
            )}
          </section>
        )}

        <section className="space-y-4">
          <div>
            <p className="mb-2 text-xs text-gray-400">Resolution</p>
            <div className="grid grid-cols-3 gap-2">
              {PONY_CONTRACT.resolutions.map(({ label, width, height }) => (
                <button
                  key={label}
                  type="button"
                  disabled={disabled}
                  onClick={() => {
                    onChange("width", width);
                    onChange("height", height);
                  }}
                  className={`rounded-lg border px-2 py-2 text-[11px] transition ${
                    form.width === width && form.height === height
                      ? "border-blue-500/50 bg-blue-500/10 text-blue-300"
                      : "border-white/10 text-gray-500 hover:bg-white/5"
                  }`}
                >
                  {label}
                  <span className="mt-0.5 block text-[9px] opacity-70">
                    {width}×{height}
                  </span>
                </button>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <label className="space-y-1.5">
              <span className="text-xs text-gray-500">Width</span>
              <input
                type="number"
                min={limits.width.min}
                max={limits.width.max}
                step={limits.width.step}
                value={form.width}
                disabled={disabled}
                onChange={(event) => onChange("width", Number(event.target.value))}
                className={inputClass}
              />
            </label>
            <label className="space-y-1.5">
              <span className="text-xs text-gray-500">Height</span>
              <input
                type="number"
                min={limits.height.min}
                max={limits.height.max}
                step={limits.height.step}
                value={form.height}
                disabled={disabled}
                onChange={(event) => onChange("height", Number(event.target.value))}
                className={inputClass}
              />
            </label>
          </div>
          <RangeField
            label="Inference steps"
            value={form.steps}
            min={limits.steps.min}
            max={limits.steps.max}
            step={limits.steps.step}
            disabled={disabled}
            onChange={(value) => onChange("steps", value)}
          />
          <RangeField
            label="CFG scale"
            value={form.cfgScale}
            min={limits.cfg_scale.min}
            max={limits.cfg_scale.max}
            step={limits.cfg_scale.step}
            disabled={disabled}
            onChange={(value) => onChange("cfgScale", value)}
          />
          <label className="block space-y-1.5">
            <span className="text-xs text-gray-400">Sampler</span>
            <select
              value={form.sampler}
              disabled={disabled}
              onChange={(event) => onChange("sampler", event.target.value as Sampler)}
              className={inputClass}
            >
              {PONY_CONTRACT.samplers.map((sampler) => (
                <option key={sampler}>{sampler}</option>
              ))}
            </select>
          </label>
          <RangeField
            label="Clip skip"
            value={form.clipSkip}
            min={limits.clip_skip.min}
            max={limits.clip_skip.max}
            step={limits.clip_skip.step}
            disabled={disabled}
            onChange={(value) => onChange("clipSkip", value)}
          />
          {form.mode === "img2img" && (
            <RangeField
              label="Denoising strength"
              value={form.denoisingStrength}
              min={limits.denoising_strength.min}
              max={limits.denoising_strength.max}
              step={limits.denoising_strength.step}
              disabled={disabled}
              onChange={(value) => onChange("denoisingStrength", value)}
            />
          )}
          <div className="grid grid-cols-[1fr_auto] gap-2">
            <label className="space-y-1.5">
              <span className="text-xs text-gray-400">Seed (-1 = random)</span>
              <input
                type="number"
                min={limits.seed.min}
                max={limits.seed.max}
                value={form.seed}
                disabled={disabled}
                onChange={(event) => onChange("seed", Number(event.target.value))}
                className={inputClass}
              />
            </label>
            <button
              type="button"
              disabled={disabled}
              onClick={() => onChange("seed", Math.floor(Math.random() * 2147483648))}
              className="mt-[22px] rounded-xl border border-white/10 px-3 text-gray-400 hover:bg-white/5 hover:text-blue-300"
              title="Generate random seed"
            >
              <Dices className="h-4 w-4" />
            </button>
          </div>
          <label className="block space-y-1.5">
            <span className="text-xs text-gray-400">Output format</span>
            <select
              value={form.outputFormat}
              disabled={disabled}
              onChange={(event) =>
                onChange("outputFormat", event.target.value as OutputFormat)
              }
              className={inputClass}
            >
              {PONY_CONTRACT.output_formats.map((format) => (
                <option key={format} value={format}>
                  {format === "png" ? "PNG — lossless" : "JPEG — smaller file"}
                </option>
              ))}
            </select>
          </label>
        </section>

        {validationError && (
          <p className="rounded-xl border border-red-500/20 bg-red-500/[0.08] px-3 py-2 text-xs text-red-300">
            {validationError}
          </p>
        )}

        <button
          type="button"
          disabled={disabled}
          onClick={onGenerate}
          className="flex w-full items-center justify-center gap-2 rounded-xl bg-gradient-to-r from-blue-500 to-indigo-500 px-4 py-3 text-sm text-white shadow-lg shadow-blue-500/20 transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <Sparkles className="h-4 w-4" />
          {disabled ? "Generation in progress" : "Generate image"}
        </button>
      </div>
    </aside>
  );
}
