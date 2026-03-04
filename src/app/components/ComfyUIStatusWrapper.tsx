/**
 * Dev-only wrapper: combines ComfyUIStatus + useComfyUIAvailability.
 * This file is only imported via dynamic import with @vite-ignore in dev mode.
 */

import { ComfyUIStatus } from "./ComfyUIStatus";
import { useComfyUIAvailability } from "../hooks/useComfyUIAvailability";

export default function ComfyUIStatusWrapper({ generationMode }: { generationMode: string }) {
  const comfyAvailability = useComfyUIAvailability(generationMode === "local");
  if (generationMode !== "local") return null;
  return (
    <div className="mt-1">
      <ComfyUIStatus
        status={comfyAvailability.status}
        onClick={comfyAvailability.checkNow}
      />
    </div>
  );
}
