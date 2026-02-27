/**
 * control-panel/index.ts
 * ──────────────────────
 * Public barrel export for the control-panel module.
 */

export { ControlPanel } from "./ControlPanel";
export type {
  ControlPanelProps,
  GenerationType,
  VideoModel,
  ImageModel,
  VideoMode,
  ImageMode,
  GenerationStatus,
  ArbitraryFrameItem,
} from "./types";

// UI atoms (for use elsewhere if needed)
export { RangeSlider }  from "./ui/RangeSlider";
export { ToggleGroup }  from "./ui/ToggleGroup";
export { ParamLabel }   from "./ui/ParamLabel";
export { ImageUploader } from "./ui/ImageUploader";
