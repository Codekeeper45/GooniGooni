import { useRef, useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "motion/react";
import {
  Play,
  Pause,
  Volume2,
  VolumeX,
  Volume1,
  Maximize2,
  Minimize2,
} from "lucide-react";

interface VideoPlayerProps {
  src: string;
  poster?: string;
  className?: string;
}

function formatTime(s: number): string {
  if (!isFinite(s) || isNaN(s)) return "0:00";
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, "0")}`;
}

export function VideoPlayer({ src, poster, className = "" }: VideoPlayerProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const progressRef = useRef<HTMLDivElement>(null);

  const [isPlaying, setIsPlaying] = useState(false);
  const [isMuted, setIsMuted] = useState(false);
  const [volume, setVolume] = useState(0.8);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [showControls, setShowControls] = useState(true);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showVolumeSlider, setShowVolumeSlider] = useState(false);
  const [buffered, setBuffered] = useState(0);
  const [isEnded, setIsEnded] = useState(false);

  // Auto-hide controls
  const resetHideTimer = useCallback(() => {
    if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    setShowControls(true);
    if (isPlaying) {
      hideTimerRef.current = setTimeout(() => {
        setShowControls(false);
        setShowVolumeSlider(false);
      }, 3000);
    }
  }, [isPlaying]);

  useEffect(() => {
    return () => {
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    };
  }, []);

  useEffect(() => {
    if (!isPlaying) {
      setShowControls(true);
      if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
    }
  }, [isPlaying]);

  // Fullscreen change listener
  useEffect(() => {
    const handler = () => {
      setIsFullscreen(!!document.fullscreenElement);
    };
    document.addEventListener("fullscreenchange", handler);
    return () => document.removeEventListener("fullscreenchange", handler);
  }, []);

  const togglePlay = () => {
    const v = videoRef.current;
    if (!v) return;
    if (isEnded) {
      v.currentTime = 0;
      setIsEnded(false);
    }
    if (isPlaying) {
      v.pause();
    } else {
      v.play().catch(() => {});
    }
    resetHideTimer();
  };

  const toggleMute = () => {
    const v = videoRef.current;
    if (!v) return;
    if (isMuted) {
      v.muted = false;
      v.volume = volume || 0.5;
      setIsMuted(false);
    } else {
      v.muted = true;
      setIsMuted(true);
    }
    resetHideTimer();
  };

  const handleVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = parseFloat(e.target.value);
    const v = videoRef.current;
    if (!v) return;
    v.volume = val;
    v.muted = val === 0;
    setVolume(val);
    setIsMuted(val === 0);
  };

  const handleProgressClick = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    const v = videoRef.current;
    if (!v || !isFinite(duration)) return;
    const newTime = ratio * duration;
    v.currentTime = newTime;
    setCurrentTime(newTime);
    resetHideTimer();
  };

  const toggleFullscreen = async () => {
    const el = containerRef.current;
    if (!el) return;
    if (!document.fullscreenElement) {
      await el.requestFullscreen().catch(() => {});
    } else {
      await document.exitFullscreen().catch(() => {});
    }
    resetHideTimer();
  };

  const VolumeIcon = isMuted || volume === 0 ? VolumeX : volume < 0.5 ? Volume1 : Volume2;
  const progress = duration > 0 ? (currentTime / duration) * 100 : 0;
  const bufferedPct = duration > 0 ? (buffered / duration) * 100 : 0;

  return (
    <div
      ref={containerRef}
      className={`relative w-full h-full bg-black overflow-hidden group ${className}`}
      onMouseMove={resetHideTimer}
      onMouseEnter={resetHideTimer}
      onMouseLeave={() => {
        if (isPlaying) {
          if (hideTimerRef.current) clearTimeout(hideTimerRef.current);
          setShowControls(false);
          setShowVolumeSlider(false);
        }
      }}
    >
      {/* Video element */}
      <video
        ref={videoRef}
        src={src}
        poster={poster}
        className="w-full h-full object-contain"
        playsInline
        onPlay={() => setIsPlaying(true)}
        onPause={() => setIsPlaying(false)}
        onEnded={() => {
          setIsPlaying(false);
          setIsEnded(true);
          setShowControls(true);
        }}
        onTimeUpdate={() => {
          const v = videoRef.current;
          if (!v) return;
          setCurrentTime(v.currentTime);
          if (v.buffered.length > 0) {
            setBuffered(v.buffered.end(v.buffered.length - 1));
          }
        }}
        onLoadedMetadata={() => {
          const v = videoRef.current;
          if (!v) return;
          setDuration(v.duration);
          v.volume = volume;
        }}
        onClick={togglePlay}
        style={{ cursor: "pointer" }}
      />

      {/* Center play/pause big button */}
      <AnimatePresence>
        {(!isPlaying || isEnded) && (
          <motion.div
            key="center-play"
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.9 }}
            transition={{ duration: 0.2 }}
            className="absolute inset-0 flex items-center justify-center pointer-events-none"
          >
            <div
              className="w-20 h-20 rounded-full flex items-center justify-center"
              style={{
                background: "rgba(0,0,0,0.55)",
                backdropFilter: "blur(12px)",
                border: "1.5px solid rgba(255,255,255,0.2)",
                boxShadow: "0 4px 32px rgba(0,0,0,0.5)",
              }}
            >
              <Play className="w-8 h-8 text-white ml-1" />
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Pause flash on click while playing */}
      <AnimatePresence>
        {isPlaying && showControls && (
          <motion.button
            key="click-area"
            className="absolute inset-0"
            onClick={togglePlay}
            style={{ background: "transparent", cursor: "pointer", border: "none" }}
          />
        )}
      </AnimatePresence>

      {/* Bottom gradient + controls */}
      <AnimatePresence>
        {showControls && (
          <motion.div
            key="controls"
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 8 }}
            transition={{ duration: 0.2 }}
            className="absolute bottom-0 left-0 right-0"
            style={{
              background:
                "linear-gradient(to top, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0.4) 60%, transparent 100%)",
              paddingTop: 48,
            }}
          >
            {/* Progress/timeline */}
            <div className="px-4 pb-2">
              <div
                ref={progressRef}
                className="relative h-1 rounded-full cursor-pointer group/bar"
                style={{ background: "rgba(255,255,255,0.15)" }}
                onClick={handleProgressClick}
              >
                {/* Buffered */}
                <div
                  className="absolute top-0 left-0 h-full rounded-full"
                  style={{
                    width: `${bufferedPct}%`,
                    background: "rgba(255,255,255,0.2)",
                  }}
                />
                {/* Played */}
                <div
                  className="absolute top-0 left-0 h-full rounded-full"
                  style={{
                    width: `${progress}%`,
                    background: "linear-gradient(90deg, #4F8CFF, #6366F1)",
                    boxShadow: "0 0 6px rgba(79,140,255,0.6)",
                    transition: "width 0.1s linear",
                  }}
                />
                {/* Thumb */}
                <div
                  className="absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full opacity-0 group-hover/bar:opacity-100 transition-opacity"
                  style={{
                    left: `${progress}%`,
                    transform: "translate(-50%, -50%)",
                    background: "#fff",
                    boxShadow: "0 0 6px rgba(79,140,255,0.8)",
                  }}
                />
              </div>
            </div>

            {/* Controls row */}
            <div className="flex items-center gap-3 px-4 pb-4">
              {/* Play/pause */}
              <button
                onClick={togglePlay}
                className="flex items-center justify-center w-8 h-8 rounded-lg transition-all duration-150 flex-shrink-0"
                style={{ color: "#fff" }}
                onMouseEnter={(e) =>
                  (e.currentTarget.style.background = "rgba(255,255,255,0.1)")
                }
                onMouseLeave={(e) =>
                  (e.currentTarget.style.background = "transparent")
                }
              >
                {isPlaying ? (
                  <Pause className="w-4 h-4" />
                ) : (
                  <Play className="w-4 h-4 ml-0.5" />
                )}
              </button>

              {/* Time */}
              <span
                className="text-xs flex-shrink-0 tabular-nums"
                style={{
                  color: "rgba(255,255,255,0.75)",
                  fontFamily: "'Space Grotesk', sans-serif",
                  letterSpacing: "0.02em",
                }}
              >
                {formatTime(currentTime)} / {formatTime(duration)}
              </span>

              {/* Flex spacer */}
              <div className="flex-1" />

              {/* Volume */}
              <div
                className="flex items-center gap-2"
                onMouseEnter={() => setShowVolumeSlider(true)}
                onMouseLeave={() => setShowVolumeSlider(false)}
              >
                <AnimatePresence>
                  {showVolumeSlider && (
                    <motion.div
                      initial={{ opacity: 0, width: 0 }}
                      animate={{ opacity: 1, width: 64 }}
                      exit={{ opacity: 0, width: 0 }}
                      transition={{ duration: 0.18 }}
                      className="overflow-hidden flex items-center"
                    >
                      <input
                        type="range"
                        min={0}
                        max={1}
                        step={0.02}
                        value={isMuted ? 0 : volume}
                        onChange={handleVolumeChange}
                        className="w-16 h-1 accent-blue-400 cursor-pointer"
                        style={{ accentColor: "#4F8CFF" }}
                      />
                    </motion.div>
                  )}
                </AnimatePresence>

                <button
                  onClick={toggleMute}
                  className="flex items-center justify-center w-8 h-8 rounded-lg transition-all duration-150 flex-shrink-0"
                  style={{ color: "#fff" }}
                  onMouseEnter={(e) =>
                    (e.currentTarget.style.background = "rgba(255,255,255,0.1)")
                  }
                  onMouseLeave={(e) =>
                    (e.currentTarget.style.background = "transparent")
                  }
                >
                  <VolumeIcon className="w-4 h-4" />
                </button>
              </div>

              {/* Fullscreen */}
              <button
                onClick={toggleFullscreen}
                className="flex items-center justify-center w-8 h-8 rounded-lg transition-all duration-150 flex-shrink-0"
                style={{ color: "#fff" }}
                onMouseEnter={(e) =>
                  (e.currentTarget.style.background = "rgba(255,255,255,0.1)")
                }
                onMouseLeave={(e) =>
                  (e.currentTarget.style.background = "transparent")
                }
              >
                {isFullscreen ? (
                  <Minimize2 className="w-4 h-4" />
                ) : (
                  <Maximize2 className="w-4 h-4" />
                )}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}