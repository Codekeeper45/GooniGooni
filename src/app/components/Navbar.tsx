import { Grid3X3, Settings, Sparkles } from "lucide-react";
import { useNavigate } from "react-router";
import { useGallery } from "../context/GalleryContext";

export function Navbar({ onSettings }: { onSettings: () => void }) {
  const navigate = useNavigate();
  const { gallery } = useGallery();

  return (
    <header className="flex h-16 flex-none items-center border-b border-white/[0.06] bg-[#0f1117]/95 px-4 backdrop-blur-xl sm:px-6">
      <button type="button" onClick={() => navigate("/")} className="flex items-center gap-2.5">
        <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-gradient-to-br from-blue-500 to-indigo-500 shadow-lg shadow-blue-500/25">
          <Sparkles className="h-4 w-4 text-white" />
        </span>
        <span className="text-sm tracking-tight text-gray-100">Gooni Gooni</span>
        <span className="rounded-md border border-blue-500/20 bg-blue-500/10 px-1.5 py-0.5 text-[9px] text-blue-300">
          PONY
        </span>
      </button>
      <div className="flex-1" />
      <button
        type="button"
        onClick={() => navigate("/gallery")}
        className="flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-gray-400 hover:bg-white/5 hover:text-gray-200"
      >
        <Grid3X3 className="h-4 w-4" />
        Gallery
        {gallery.length > 0 && (
          <span className="rounded-full bg-blue-500/15 px-1.5 text-[10px] text-blue-300">
            {gallery.length}
          </span>
        )}
      </button>
      <button
        type="button"
        onClick={onSettings}
        className="ml-1 flex items-center gap-2 rounded-lg px-3 py-2 text-xs text-gray-400 hover:bg-white/5 hover:text-gray-200"
      >
        <Settings className="h-4 w-4" />
        Settings
      </button>
    </header>
  );
}
