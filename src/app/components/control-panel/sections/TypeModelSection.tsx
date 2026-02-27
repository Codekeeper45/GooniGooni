/**
 * control-panel/sections/TypeModelSection.tsx
 * ─────────────────────────────────────────────
 * Image/Video type selector + Model selector + Mode selector.
 */

import { Video, Image as ImageLucide } from "lucide-react";
import { ToggleGroup } from "../ui/ToggleGroup";
import { ParamLabel } from "../ui/ParamLabel";
import type { GenerationType, VideoModel, ImageModel, VideoMode, ImageMode } from "../types";

interface Props {
  generationType: GenerationType;
  setGenerationType: (t: GenerationType) => void;
  videoModel: VideoModel;
  setVideoModel: (m: VideoModel) => void;
  imageModel: ImageModel;
  setImageModel: (m: ImageModel) => void;
  videoMode: VideoMode;
  setVideoMode: (m: VideoMode) => void;
  imageMode: ImageMode;
  setImageMode: (m: ImageMode) => void;
  disabled: boolean;
}

export function TypeModelSection({
  generationType, setGenerationType,
  videoModel, setVideoModel,
  imageModel, setImageModel,
  videoMode, setVideoMode,
  imageMode, setImageMode,
  disabled,
}: Props) {
  return (
    <>
      {/* Type toggle: Image / Video */}
      <div
        className="grid grid-cols-2 gap-1 p-1 rounded-xl"
        style={{ background: "#1C212C", border: "1px solid rgba(255,255,255,0.05)" }}
      >
        {(
          [
            { id: "image" as GenerationType, icon: ImageLucide, label: "Image" },
            { id: "video" as GenerationType, icon: Video, label: "Video" },
          ] as const
        ).map((tab) => (
          <button
            key={tab.id}
            onClick={() => !disabled && setGenerationType(tab.id)}
            disabled={disabled}
            className="flex items-center justify-center gap-2 py-2.5 px-2 rounded-lg text-sm transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
            style={
              generationType === tab.id
                ? { background: "#151922", border: "1px solid rgba(79,140,255,0.2)", color: "#E5E7EB", boxShadow: "0 2px 8px rgba(0,0,0,0.3)" }
                : { background: "transparent", border: "1px solid transparent", color: "#4B5563" }
            }
          >
            <tab.icon className="w-3.5 h-3.5 flex-shrink-0" />
            <span className="truncate text-sm">{tab.label}</span>
          </button>
        ))}
      </div>

      {/* Model */}
      <div>
        <ParamLabel>Model</ParamLabel>
        {generationType === "video" ? (
          <ToggleGroup
            options={[
              { value: "anisora", label: "AniSora V3.2" },
              { value: "phr00t", label: "Phr00t WAN 2.2" },
            ]}
            value={videoModel}
            onChange={setVideoModel}
            disabled={disabled}
          />
        ) : (
          <ToggleGroup
            options={[
              { value: "pony", label: "Pony V6 XL" },
              { value: "flux", label: "Flux.1 dev" },
            ]}
            value={imageModel}
            onChange={setImageModel}
            disabled={disabled}
          />
        )}
      </div>

      {/* Mode */}
      <div>
        <ParamLabel>Mode</ParamLabel>
        {generationType === "video" ? (
          <ToggleGroup
            options={[
              { value: "t2v", label: "Text2Video" },
              { value: "i2v", label: "Image2Video" },
              { value: "first_last_frame", label: "First+Last" },
              ...(videoModel === "anisora"
                ? [{ value: "arbitrary_frame" as VideoMode, label: "Arbitrary" }]
                : []),
            ]}
            value={videoMode}
            onChange={setVideoMode}
            disabled={disabled}
          />
        ) : (
          <ToggleGroup
            options={[
              { value: "txt2img", label: "Text to Image" },
              { value: "img2img", label: "Image to Image" },
            ]}
            value={imageMode}
            onChange={setImageMode}
            disabled={disabled}
          />
        )}
      </div>
    </>
  );
}
