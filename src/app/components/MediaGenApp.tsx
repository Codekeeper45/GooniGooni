import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Eye, EyeOff, Loader2, X } from "lucide-react";
import {
  ApiError,
  PONY_CONTRACT,
  cancelTask,
  fetchAsset,
  generateImage,
  getTaskStatus,
  loadApiSettings,
  saveApiSettings,
  testConnection,
  type ApiSettings,
  type GenerationPayload,
  type ResultSummary,
} from "../api";
import { useGallery } from "../context/GalleryContext";
import { ControlPanel, type GenerationForm } from "./ControlPanel";
import { Navbar } from "./Navbar";
import { OutputPanel, type UiStatus } from "./OutputPanel";

const ACTIVE_TASK_KEY = "gooni_active_task_v2";

const DEFAULT_FORM: GenerationForm = {
  mode: PONY_CONTRACT.model.default_mode as GenerationForm["mode"],
  prompt: "",
  negativePrompt: PONY_CONTRACT.defaults.negative_prompt,
  width: PONY_CONTRACT.defaults.width,
  height: PONY_CONTRACT.defaults.height,
  steps: PONY_CONTRACT.defaults.steps,
  cfgScale: PONY_CONTRACT.defaults.cfg_scale,
  sampler: PONY_CONTRACT.defaults.sampler as GenerationForm["sampler"],
  clipSkip: PONY_CONTRACT.defaults.clip_skip,
  denoisingStrength: PONY_CONTRACT.defaults.denoising_strength,
  seed: PONY_CONTRACT.defaults.seed,
  outputFormat: PONY_CONTRACT.defaults.output_format as GenerationForm["outputFormat"],
  referenceImage: null,
  referenceName: null,
};

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function validateForm(form: GenerationForm): string | null {
  if (!form.prompt.trim()) return "Prompt is required.";
  const limits = PONY_CONTRACT.limits;
  if (
    form.width < limits.width.min ||
    form.width > limits.width.max ||
    form.width % limits.width.step !== 0
  ) {
    return "Width must be 512–1536 and divisible by 8.";
  }
  if (
    form.height < limits.height.min ||
    form.height > limits.height.max ||
    form.height % limits.height.step !== 0
  ) {
    return "Height must be 512–1536 and divisible by 8.";
  }
  if (form.width * form.height > limits.max_pixels) {
    return `Width × height must not exceed ${limits.max_pixels.toLocaleString()} pixels on the configured GPU.`;
  }
  if (form.mode === "img2img" && !form.referenceImage) {
    return "Upload a reference image for image-to-image mode.";
  }
  if (form.seed < limits.seed.min || form.seed > limits.seed.max) {
    return "Seed must be -1 or an integer up to 2147483647.";
  }
  return null;
}

function buildPayload(form: GenerationForm): GenerationPayload {
  return {
    model: "pony",
    type: "image",
    mode: form.mode,
    prompt: form.prompt.trim(),
    negative_prompt: form.negativePrompt.trim(),
    width: form.width,
    height: form.height,
    steps: form.steps,
    cfg_scale: form.cfgScale,
    sampler: form.sampler,
    clip_skip: form.clipSkip,
    denoising_strength: form.denoisingStrength,
    seed: form.seed,
    output_format: form.outputFormat,
    reference_image: form.mode === "img2img" ? form.referenceImage : null,
  };
}

function SettingsDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState<ApiSettings>(loadApiSettings);
  const [showKey, setShowKey] = useState(false);
  const [testState, setTestState] = useState<"idle" | "testing" | "ok" | "error">("idle");
  const [testMessage, setTestMessage] = useState("");

  useEffect(() => {
    if (open) {
      setDraft(loadApiSettings());
      setTestState("idle");
      setTestMessage("");
    }
  }, [open]);

  if (!open) return null;

  const save = () => {
    saveApiSettings(draft);
    onClose();
  };

  const test = async () => {
    saveApiSettings(draft);
    setTestState("testing");
    setTestMessage("");
    try {
      await testConnection();
      setTestState("ok");
      setTestMessage("Backend and API key are valid.");
    } catch (error) {
      setTestState("error");
      setTestMessage(error instanceof Error ? error.message : "Connection failed");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-2xl border border-white/10 bg-[#151922] shadow-2xl">
        <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-4">
          <div>
            <p className="text-sm text-gray-100">Backend settings</p>
            <p className="mt-0.5 text-xs text-gray-500">Stored only in this browser</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-2 text-gray-500 hover:bg-white/5 hover:text-gray-200"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="space-y-4 p-5">
          <label className="block space-y-2">
            <span className="text-xs text-gray-400">Modal API URL</span>
            <input
              value={draft.apiUrl}
              onChange={(event) => setDraft({ ...draft, apiUrl: event.target.value })}
              placeholder="https://your-workspace--gooni-api.modal.run"
              className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5 text-sm text-gray-200 outline-none focus:border-blue-500/50"
            />
          </label>
          <label className="block space-y-2">
            <span className="text-xs text-gray-400">API key</span>
            <div className="relative">
              <input
                type={showKey ? "text" : "password"}
                value={draft.apiKey}
                onChange={(event) => setDraft({ ...draft, apiKey: event.target.value })}
                placeholder="Matches Modal secret gooni-api-key"
                className="w-full rounded-xl border border-white/10 bg-white/[0.04] px-3 py-2.5 pr-11 text-sm text-gray-200 outline-none focus:border-blue-500/50"
              />
              <button
                type="button"
                onClick={() => setShowKey((value) => !value)}
                className="absolute right-2 top-1/2 -translate-y-1/2 rounded-lg p-2 text-gray-500 hover:text-gray-200"
                aria-label={showKey ? "Hide API key" : "Show API key"}
              >
                {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
          </label>
          <p className="rounded-xl bg-white/[0.03] px-3 py-2 text-[11px] leading-relaxed text-gray-500">
            The key is sent only in the X-API-Key header. It is never appended to image
            URLs or browser history.
          </p>
          {testState !== "idle" && (
            <p
              className={`flex items-center gap-2 rounded-xl px-3 py-2 text-xs ${
                testState === "ok"
                  ? "bg-emerald-500/10 text-emerald-300"
                  : testState === "error"
                    ? "bg-red-500/10 text-red-300"
                    : "bg-blue-500/10 text-blue-300"
              }`}
            >
              {testState === "testing" && <Loader2 className="h-4 w-4 animate-spin" />}
              {testState === "ok" && <CheckCircle2 className="h-4 w-4" />}
              {testState === "testing" ? "Testing connection..." : testMessage}
            </p>
          )}
        </div>
        <div className="flex justify-end gap-2 border-t border-white/[0.06] px-5 py-4">
          <button
            type="button"
            onClick={test}
            disabled={testState === "testing"}
            className="rounded-xl border border-white/10 px-4 py-2 text-xs text-gray-300 hover:bg-white/5 disabled:opacity-50"
          >
            Test connection
          </button>
          <button
            type="button"
            onClick={save}
            className="rounded-xl bg-blue-500 px-4 py-2 text-xs text-white hover:bg-blue-400"
          >
            Save
          </button>
        </div>
      </div>
    </div>
  );
}

export function MediaGenApp() {
  const [form, setForm] = useState<GenerationForm>(DEFAULT_FORM);
  const [uiStatus, setUiStatus] = useState<UiStatus>("idle");
  const [statusText, setStatusText] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [result, setResult] = useState<(ResultSummary & { objectUrl: string }) | null>(
    null,
  );
  const [settingsOpen, setSettingsOpen] = useState(false);
  const runToken = useRef(0);
  const resultUrl = useRef<string | null>(null);
  const { refresh: refreshGallery } = useGallery();

  const replaceResultUrl = (url: string | null) => {
    if (resultUrl.current) URL.revokeObjectURL(resultUrl.current);
    resultUrl.current = url;
  };

  const finishWithError = (message: string) => {
    localStorage.removeItem(ACTIVE_TASK_KEY);
    setActiveTaskId(null);
    setUiStatus("error");
    setError(message);
    setStatusText("Generation failed");
  };

  const pollTask = async (taskId: string, token: number) => {
    let transientFailures = 0;
    while (runToken.current === token) {
      try {
        const response = await getTaskStatus(taskId);
        transientFailures = 0;
        if (runToken.current !== token) return;
        setStatusText(response.message);

        if (response.status === "done") {
          if (!response.result || !response.result_url) {
            finishWithError("Backend returned done without result metadata.");
            return;
          }
          const blob = await fetchAsset(response.result_url);
          if (runToken.current !== token) return;
          const objectUrl = URL.createObjectURL(blob);
          replaceResultUrl(objectUrl);
          setResult({ ...response.result, objectUrl });
          setUiStatus("success");
          setActiveTaskId(null);
          localStorage.removeItem(ACTIVE_TASK_KEY);
          await refreshGallery();
          return;
        }
        if (response.status === "failed") {
          finishWithError(response.error || response.message);
          return;
        }
        if (response.status === "cancelled") {
          setUiStatus("cancelled");
          setActiveTaskId(null);
          localStorage.removeItem(ACTIVE_TASK_KEY);
          return;
        }
      } catch (caught) {
        transientFailures += 1;
        const message = caught instanceof Error ? caught.message : "Status request failed";
        if (caught instanceof ApiError && [401, 403].includes(caught.status)) {
          finishWithError(`${message}. Check Settings.`);
          return;
        }
        if (transientFailures >= 5) {
          finishWithError(
            `Lost connection after 5 retries: ${message}. The backend task may still be running.`,
          );
          return;
        }
        setStatusText(`Connection interrupted. Retrying (${transientFailures}/5)...`);
        await sleep(Math.min(3000 * 2 ** (transientFailures - 1), 15000));
        continue;
      }
      await sleep(3000);
    }
  };

  useEffect(() => {
    const savedTask = localStorage.getItem(ACTIVE_TASK_KEY);
    if (savedTask && loadApiSettings().apiUrl) {
      setActiveTaskId(savedTask);
      setUiStatus("generating");
      setStatusText("Restoring active generation...");
      const token = ++runToken.current;
      void pollTask(savedTask, token);
    }
    return () => {
      runToken.current += 1;
      replaceResultUrl(null);
    };
    // Restore exactly once when the application mounts.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const updateForm = <K extends keyof GenerationForm>(
    key: K,
    value: GenerationForm[K],
  ) => {
    setForm((current) => {
      const next = { ...current, [key]: value };
      if (key === "mode" && value === "txt2img") {
        next.referenceImage = null;
        next.referenceName = null;
      }
      return next;
    });
    setValidationError(null);
  };

  const handleReferenceFile = (file: File | null) => {
    if (!file) {
      updateForm("referenceImage", null);
      updateForm("referenceName", null);
      return;
    }
    if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
      setValidationError("Reference must be PNG, JPEG or WebP.");
      return;
    }
    if (file.size > PONY_CONTRACT.limits.reference_max_bytes) {
      setValidationError("Reference image must be smaller than 10 MB.");
      return;
    }
    const reader = new FileReader();
    reader.onerror = () => setValidationError("Could not read the reference image.");
    reader.onload = () => {
      updateForm("referenceImage", String(reader.result));
      updateForm("referenceName", file.name);
    };
    reader.readAsDataURL(file);
  };

  const startGeneration = async () => {
    const invalid = validateForm(form);
    if (invalid) {
      setValidationError(invalid);
      return;
    }
    if (!loadApiSettings().apiUrl) {
      setSettingsOpen(true);
      setValidationError("Configure the backend URL before generating.");
      return;
    }

    const token = ++runToken.current;
    replaceResultUrl(null);
    setResult(null);
    setError(null);
    setValidationError(null);
    setUiStatus("generating");
    setStatusText("Submitting generation...");
    try {
      const queued = await generateImage(buildPayload(form));
      if (runToken.current !== token) return;
      setActiveTaskId(queued.task_id);
      localStorage.setItem(ACTIVE_TASK_KEY, queued.task_id);
      setStatusText(queued.message);
      await pollTask(queued.task_id, token);
    } catch (caught) {
      if (runToken.current !== token) return;
      const message = caught instanceof Error ? caught.message : "Could not submit generation";
      finishWithError(message);
      if (caught instanceof ApiError && [0, 401, 403].includes(caught.status)) {
        setSettingsOpen(true);
      }
    }
  };

  const stopGeneration = async () => {
    if (!activeTaskId) return;
    setStatusText("Cancelling generation...");
    try {
      await cancelTask(activeTaskId);
      runToken.current += 1;
      setUiStatus("cancelled");
      setActiveTaskId(null);
      localStorage.removeItem(ACTIVE_TASK_KEY);
    } catch (caught) {
      setStatusText("Generation is still running");
      setError(caught instanceof Error ? caught.message : "Could not cancel generation");
    }
  };

  const downloadResult = () => {
    if (!result) return;
    const anchor = document.createElement("a");
    anchor.href = result.objectUrl;
    anchor.download = `gooni-${result.id}.${result.output_format === "jpeg" ? "jpg" : "png"}`;
    anchor.click();
  };

  return (
    <div className="flex min-h-screen flex-col bg-[#0f1117] text-gray-100">
      <Navbar onSettings={() => setSettingsOpen(true)} />
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <ControlPanel
          form={form}
          disabled={uiStatus === "generating"}
          validationError={validationError}
          onChange={updateForm}
          onReferenceFile={handleReferenceFile}
          onGenerate={startGeneration}
        />
        <OutputPanel
          status={uiStatus}
          statusText={statusText}
          error={error}
          result={result}
          onCancel={stopGeneration}
          onRetry={startGeneration}
          onDownload={downloadResult}
        />
      </div>
      <SettingsDialog open={settingsOpen} onClose={() => setSettingsOpen(false)} />
    </div>
  );
}
