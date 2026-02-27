/**
 * control-panel/ui/ImageUploader.tsx
 * ────────────────────────────────────
 * Drag-and-drop / click-to-upload image component.
 */

import type React from "react";
import { RefreshCw, Upload, X } from "lucide-react";
import { ParamLabel } from "./ParamLabel";

interface ImageUploaderProps {
  image: string | null;
  onUpload: (data: string) => void;
  onRemove: () => void;
  fileRef: React.RefObject<HTMLInputElement>;
  label?: string;
  disabled?: boolean;
}

export function ImageUploader({
  image, onUpload, onRemove, fileRef, label, disabled = false,
}: ImageUploaderProps) {
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    if (disabled) return;
    const file = e.dataTransfer.files?.[0];
    if (file && file.type.startsWith("image/")) {
      const reader = new FileReader();
      reader.onload = (ev) => onUpload(ev.target?.result as string);
      reader.readAsDataURL(file);
    }
  };

  const handleFile = (file: File) => {
    if (!file.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.onload = (ev) => onUpload(ev.target?.result as string);
    reader.readAsDataURL(file);
  };

  return (
    <div>
      {label && <ParamLabel>{label}</ParamLabel>}
      {image ? (
        <div
          className="relative rounded-xl overflow-hidden"
          style={{ border: "1px solid rgba(79,140,255,0.2)" }}
        >
          <img src={image} alt={label || "Reference"} className="w-full h-36 object-cover" />
          <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent" />
          <div className="absolute bottom-2.5 right-2.5 flex gap-1.5">
            <button
              onClick={() => !disabled && fileRef.current?.click()}
              disabled={disabled}
              className="p-1.5 rounded-lg transition-all duration-150 disabled:opacity-50"
              style={{
                background: "rgba(0,0,0,0.5)",
                backdropFilter: "blur(8px)",
                color: "#9CA3AF",
                border: "1px solid rgba(255,255,255,0.1)",
              }}
            >
              <RefreshCw className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => !disabled && onRemove()}
              disabled={disabled}
              className="p-1.5 rounded-lg transition-all duration-150 disabled:opacity-50"
              style={{
                background: "rgba(0,0,0,0.5)",
                backdropFilter: "blur(8px)",
                color: "#EF4444",
                border: "1px solid rgba(239,68,68,0.2)",
              }}
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      ) : (
        <div
          onDrop={handleDrop}
          onDragOver={(e) => e.preventDefault()}
          onClick={() => !disabled && fileRef.current?.click()}
          className="rounded-xl flex flex-col items-center gap-3 py-8 cursor-pointer transition-all duration-200"
          style={{
            border: "2px dashed rgba(255,255,255,0.08)",
            background: "rgba(255,255,255,0.01)",
            opacity: disabled ? 0.5 : 1,
          }}
          onMouseEnter={(e) => {
            if (!disabled) {
              e.currentTarget.style.borderColor = "rgba(79,140,255,0.25)";
              e.currentTarget.style.background = "rgba(79,140,255,0.02)";
            }
          }}
          onMouseLeave={(e) => {
            if (!disabled) {
              e.currentTarget.style.borderColor = "rgba(255,255,255,0.08)";
              e.currentTarget.style.background = "rgba(255,255,255,0.01)";
            }
          }}
        >
          <div
            className="w-10 h-10 rounded-xl flex items-center justify-center"
            style={{ background: "rgba(79,140,255,0.06)", border: "1px solid rgba(79,140,255,0.12)" }}
          >
            <Upload className="w-4 h-4" style={{ color: "#4F8CFF" }} />
          </div>
          <div className="text-center">
            <p className="text-sm" style={{ color: "#9CA3AF" }}>
              Drop image or <span style={{ color: "#4F8CFF" }}>click to upload</span>
            </p>
            <p className="text-xs mt-1" style={{ color: "#4B5563" }}>PNG, JPG, WebP</p>
          </div>
        </div>
      )}
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        onChange={(e) => e.target.files?.[0] && handleFile(e.target.files[0])}
        className="hidden"
      />
    </div>
  );
}
