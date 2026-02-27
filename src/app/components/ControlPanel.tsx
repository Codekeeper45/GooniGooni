/**
 * ControlPanel.tsx (root) — backward-compatible re-export
 * ─────────────────────────────────────────────────────────
 * The full implementation has been split into:
 *   src/app/components/control-panel/
 * This file re-exports everything so existing import paths still work.
 */
export {
  ControlPanel,
  RangeSlider,
  ToggleGroup,
  ParamLabel,
  ImageUploader,
} from "./control-panel";

export type {
  ControlPanelProps,
  GenerationType,
  VideoModel,
  ImageModel,
  VideoMode,
  ImageMode,
  GenerationStatus,
  ArbitraryFrameItem,
} from "./control-panel";
