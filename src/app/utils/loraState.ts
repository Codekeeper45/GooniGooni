/**
 * Shared LoRA selection state — bridge between ControlPanel (writes) and
 * GenerationContext (reads at generation time).
 *
 * Using a module-level variable instead of React context to avoid
 * adding complexity to the existing GenerationContext interface.
 */

export interface ActiveLoRA {
  path: string;
  filename: string;
  strength_model: number;
  strength_clip: number;
}

let _activeLoRAs: ActiveLoRA[] = [];

export function setActiveLoRAs(loras: ActiveLoRA[]): void {
  _activeLoRAs = loras;
}

export function getActiveLoRAs(): ActiveLoRA[] {
  return _activeLoRAs;
}
