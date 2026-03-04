/**
 * ModeSwitcher — Renders Local / Remote generation mode tabs.
 * Tabs are determined by the current environment:
 *   - local: shows both "Local" and "Remote"
 *   - production: shows only "Remote"
 *
 * @see contracts/frontend-contracts.md#ModeSwitcher
 */

import React from "react";
import { Tabs, TabsList, TabsTrigger } from "./ui/tabs";
import { getAvailableModes, getDefaultMode, type GenerationModeId } from "../utils/environment";

// ═══════════════════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════════════════

export interface ModeSwitcherProps {
  /** Called when the user selects a different mode tab. */
  onModeChange: (mode: GenerationModeId) => void;
  /** Override the environment default mode (optional). */
  defaultMode?: GenerationModeId;
  /** The currently active mode (controlled). */
  activeMode?: GenerationModeId;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Labels
// ═══════════════════════════════════════════════════════════════════════════════

const MODE_LABELS: Record<GenerationModeId, string> = {
  local: "Локально",
  remote: "Облако",
};

const MODE_DESCRIPTIONS: Record<GenerationModeId, string> = {
  local: "Генерация через ComfyUI на вашем компьютере",
  remote: "Генерация через облачный GPU (Modal)",
};

// ═══════════════════════════════════════════════════════════════════════════════
// Component
// ═══════════════════════════════════════════════════════════════════════════════

export function ModeSwitcher({ onModeChange, defaultMode, activeMode }: ModeSwitcherProps) {
  const availableModes = getAvailableModes();
  const envDefault = getDefaultMode();
  const selected = activeMode ?? defaultMode ?? envDefault;

  // Nothing to switch when only one mode
  if (availableModes.length <= 1) {
    return null;
  }

  return (
    <Tabs
      value={selected}
      onValueChange={(value) => onModeChange(value as GenerationModeId)}
      className="w-full"
    >
      <TabsList className="w-full bg-[#1A1D27] border border-[#2A2D3A]">
        {availableModes.map((mode) => (
          <TabsTrigger
            key={mode}
            value={mode}
            title={MODE_DESCRIPTIONS[mode]}
            className="flex-1 data-[state=active]:bg-[#7C3AED] data-[state=active]:text-white text-gray-400"
          >
            {MODE_LABELS[mode]}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  );
}
