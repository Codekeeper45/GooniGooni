/**
 * control-panel/sections/ImageUploadSection.tsx
 * ───────────────────────────────────────────────
 * Conditional reference image uploaders based on current mode.
 */

import { useRef } from "react";
import { AnimatePresence } from "motion/react";
import { motion } from "motion/react";
import { X, Upload } from "lucide-react";
import { ImageUploader } from "../ui/ImageUploader";
import { ParamLabel } from "../ui/ParamLabel";
import type { VideoMode, ImageMode, GenerationType, ArbitraryFrameItem } from "../types";

interface Props {
  generationType: GenerationType;
  videoMode: VideoMode;
  imageMode: ImageMode;

  // Single reference image (i2v, img2img)
  referenceImage: string | null;
  onImageUpload: (data: string) => void;
  onImageRemove: () => void;
  fileRef: React.RefObject<HTMLInputElement>;

  // First + Last frame pair (first_last_frame mode)
  firstFrameImage: string | null;
  lastFrameImage: string | null;
  onFirstFrameUpload: (data: string) => void;
  onLastFrameUpload: (data: string) => void;
  onFirstFrameRemove: () => void;
  onLastFrameRemove: () => void;
  firstFrameRef: React.RefObject<HTMLInputElement>;
  lastFrameRef: React.RefObject<HTMLInputElement>;

  // Arbitrary keyframes
  arbitraryFrames: ArbitraryFrameItem[];
  onArbitraryFrameAdd: (frameIndex: number, image: string) => void;
  onArbitraryFrameRemove: (id: string) => void;
  onArbitraryFrameUpdate: (id: string, frameIndex: number) => void;
  numFrames: number;

  disabled: boolean;
}

export function ImageUploadSection({
  generationType, videoMode, imageMode,
  referenceImage, onImageUpload, onImageRemove, fileRef,
  firstFrameImage, lastFrameImage,
  onFirstFrameUpload, onLastFrameUpload,
  onFirstFrameRemove, onLastFrameRemove,
  firstFrameRef, lastFrameRef,
  arbitraryFrames, onArbitraryFrameAdd, onArbitraryFrameRemove, onArbitraryFrameUpdate,
  numFrames, disabled,
}: Props) {
  const arbitraryFrameRef = useRef<HTMLInputElement>(null);
  const [newArbitraryFrameIndex, setNewArbitraryFrameIndex] = React.useState(0);

  const needsReference = (generationType === "video" && videoMode === "i2v") ||
                         (generationType === "image" && imageMode === "img2img");
  const needsFirstLast  = generationType === "video" && videoMode === "first_last_frame";
  const needsArbitrary  = generationType === "video" && videoMode === "arbitrary_frame";

  const handleArbitraryFile = (file: File) => {
    const reader = new FileReader();
    reader.onload = (ev) => {
      const data = ev.target?.result as string;
      onArbitraryFrameAdd(newArbitraryFrameIndex, data);
      setNewArbitraryFrameIndex((idx) => Math.min(idx + 20, numFrames - 1));
    };
    reader.readAsDataURL(file);
  };

  return (
    <>
      {/* Single reference image */}
      <AnimatePresence>
        {needsReference && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <ImageUploader
              image={referenceImage}
              onUpload={onImageUpload}
              onRemove={onImageRemove}
              fileRef={fileRef}
              label="Reference Image"
              disabled={disabled}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* First + Last Frame */}
      <AnimatePresence>
        {needsFirstLast && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden space-y-4"
          >
            <ImageUploader
              image={firstFrameImage}
              onUpload={onFirstFrameUpload}
              onRemove={onFirstFrameRemove}
              fileRef={firstFrameRef}
              label="First Frame"
              disabled={disabled}
            />
            <ImageUploader
              image={lastFrameImage}
              onUpload={onLastFrameUpload}
              onRemove={onLastFrameRemove}
              fileRef={lastFrameRef}
              label="Last Frame"
              disabled={disabled}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* Arbitrary frames */}
      <AnimatePresence>
        {needsArbitrary && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <ParamLabel>Arbitrary Frames (Multi-Keyframe)</ParamLabel>

            <div className="space-y-3 mb-3">
              {arbitraryFrames.map((frame) => (
                <div
                  key={frame.id}
                  className="rounded-xl p-3"
                  style={{ background: "rgba(79,140,255,0.04)", border: "1px solid rgba(79,140,255,0.15)" }}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <span className="text-xs" style={{ color: "#6B7280" }}>Frame Index:</span>
                    <input
                      type="number"
                      value={frame.frameIndex}
                      onChange={(e) => onArbitraryFrameUpdate(frame.id, parseInt(e.target.value))}
                      min={0}
                      max={numFrames - 1}
                      disabled={disabled}
                      className="flex-1 rounded-lg px-2.5 py-1.5 text-xs outline-none disabled:opacity-50"
                      style={{ background: "#1C212C", border: "1px solid rgba(255,255,255,0.06)", color: "#E5E7EB" }}
                    />
                    <button
                      onClick={() => onArbitraryFrameRemove(frame.id)}
                      disabled={disabled}
                      className="p-1.5 rounded-lg transition-all duration-150 disabled:opacity-50"
                      style={{ background: "rgba(239,68,68,0.1)", color: "#EF4444", border: "1px solid rgba(239,68,68,0.2)" }}
                    >
                      <X className="w-3.5 h-3.5" />
                    </button>
                  </div>
                  <img src={frame.image} alt={`Frame ${frame.frameIndex}`} className="w-full h-24 object-cover rounded-lg" />
                </div>
              ))}
            </div>

            <div className="rounded-xl p-4" style={{ background: "#1C212C", border: "1px solid rgba(255,255,255,0.06)" }}>
              <div className="flex gap-2 mb-3">
                <div className="flex-1">
                  <p className="text-xs mb-1.5" style={{ color: "#6B7280" }}>Frame Index (0-{numFrames - 1})</p>
                  <input
                    type="number"
                    value={newArbitraryFrameIndex}
                    onChange={(e) => setNewArbitraryFrameIndex(parseInt(e.target.value))}
                    min={0}
                    max={numFrames - 1}
                    disabled={disabled}
                    className="w-full rounded-lg px-3 py-2 text-sm outline-none disabled:opacity-50"
                    style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.06)", color: "#E5E7EB" }}
                  />
                </div>
              </div>
              <button
                onClick={() => arbitraryFrameRef.current?.click()}
                disabled={disabled}
                className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg text-sm transition-all duration-150 disabled:opacity-50"
                style={{ background: "rgba(79,140,255,0.08)", border: "1px solid rgba(79,140,255,0.2)", color: "#4F8CFF" }}
              >
                <Upload className="w-4 h-4" />
                Add Keyframe Image
              </button>
              <input
                ref={arbitraryFrameRef}
                type="file"
                accept="image/*"
                onChange={(e) => e.target.files?.[0] && handleArbitraryFile(e.target.files[0])}
                className="hidden"
              />
            </div>
            <p className="text-xs mt-2" style={{ color: "#6B7280" }}>
              💡 Add multiple reference images at different frame positions. Model will interpolate between them.
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

// Need React in scope for useState
import React from "react";
