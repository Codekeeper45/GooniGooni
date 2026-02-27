/**
 * control-panel/ui/ParamLabel.tsx
 * ────────────────────────────────
 * Small uppercase section label used throughout the control panel.
 */

import type React from "react";

export function ParamLabel({ children }: { children: React.ReactNode }) {
  return (
    <p
      className="text-[11px] uppercase tracking-widest mb-2.5"
      style={{ color: "#6B7280", fontFamily: "'Space Grotesk', sans-serif" }}
    >
      {children}
    </p>
  );
}
