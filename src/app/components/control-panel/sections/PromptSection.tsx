/**
 * control-panel/sections/PromptSection.tsx
 * ──────────────────────────────────────────
 * Main prompt textarea + negative prompt inside advanced.
 */

interface Props {
  prompt: string;
  setPrompt: (p: string) => void;
  negativePrompt: string;
  setNegativePrompt: (p: string) => void;
  useAdvancedSettings: boolean;
  disabled: boolean;
  promptFocused: boolean;
  setPromptFocused: (f: boolean) => void;
}

export function PromptSection({
  prompt, setPrompt, negativePrompt, setNegativePrompt,
  useAdvancedSettings, disabled, promptFocused, setPromptFocused,
}: Props) {
  return (
    <div>
      <div
        className="rounded-2xl overflow-hidden transition-all duration-200"
        style={{
          border: promptFocused ? "1px solid rgba(79,140,255,0.35)" : "1px solid rgba(255,255,255,0.06)",
          background: "#1C212C",
          boxShadow: promptFocused ? "0 0 0 3px rgba(79,140,255,0.08)" : "none",
        }}
      >
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onFocus={() => setPromptFocused(true)}
          onBlur={() => setPromptFocused(false)}
          disabled={disabled}
          placeholder="Describe what you want to generate..."
          rows={5}
          maxLength={2000}
          className="w-full bg-transparent p-4 resize-none outline-none text-sm disabled:opacity-60 placeholder-[#374151]"
          style={{ color: "#E5E7EB", fontFamily: "'Space Grotesk', sans-serif" }}
        />
        <div
          className="flex items-center justify-end px-4 py-2.5 border-t"
          style={{ borderColor: "rgba(255,255,255,0.05)" }}
        >
          <span className="text-[10px]" style={{ color: "#374151" }}>
            {prompt.length}/2000
          </span>
        </div>
      </div>
    </div>
  );
}
