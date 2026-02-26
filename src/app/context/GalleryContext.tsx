import { createContext, useContext, useState, useEffect } from "react";
import type { GenerationType } from "../components/ControlPanel";
import { sessionFetch } from "../utils/sessionClient";

export interface GalleryItem {
  id: string;
  url: string;
  thumbnailUrl?: string; // separate thumbnail for video type
  prompt: string;
  type: GenerationType;
  model: string;
  width: number;
  height: number;
  seed: number;
  createdAt: Date;
}

interface GalleryContextType {
  gallery: GalleryItem[];
  addToGallery: (item: GalleryItem) => void;
  clearGallery: () => void;
  removeFromGallery: (id: string) => void;
}

const GalleryContext = createContext<GalleryContextType | null>(null);

function deserializeGallery(raw: string): GalleryItem[] {
  try {
    const parsed = JSON.parse(raw);
    return parsed.map((item: any) => ({
      ...item,
      createdAt: new Date(item.createdAt),
    }));
  } catch {
    return [];
  }
}

export function GalleryProvider({ children }: { children: React.ReactNode }) {
  const [gallery, setGallery] = useState<GalleryItem[]>(() => {
    const saved = localStorage.getItem("mg_gallery_v2");
    return saved ? deserializeGallery(saved) : [];
  });

  useEffect(() => {
    localStorage.setItem("mg_gallery_v2", JSON.stringify(gallery));
  }, [gallery]);

  const addToGallery = (item: GalleryItem) => {
    setGallery((prev) => [item, ...prev]);
  };

  const clearGallery = () => {
    setGallery([]);
  };

  const removeFromGallery = (id: string) => {
    setGallery((prev) => prev.filter((item) => item.id !== id));
    // Best-effort server cleanup — don't block UI on failure
    sessionFetch(`/gallery/${id}`, { method: "DELETE" }).catch(() => {});
  };

  return (
    <GalleryContext.Provider value={{ gallery, addToGallery, clearGallery, removeFromGallery }}>
      {children}
    </GalleryContext.Provider>
  );
}

export function useGallery(): GalleryContextType {
  const ctx = useContext(GalleryContext);
  if (!ctx) throw new Error("useGallery must be used inside GalleryProvider");
  return ctx;
}
