import { createContext, useContext, useEffect, useRef, useState } from "react";
import {
  deleteGalleryItem,
  fetchAsset,
  getGallery,
  loadApiSettings,
  type GalleryItem,
} from "../api";

interface GalleryContextValue {
  gallery: GalleryItem[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  removeFromGallery: (id: string) => Promise<void>;
  clearGallery: () => Promise<void>;
}

const GalleryContext = createContext<GalleryContextValue | null>(null);

export function GalleryProvider({ children }: { children: React.ReactNode }) {
  const [gallery, setGallery] = useState<GalleryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const objectUrls = useRef<string[]>([]);

  const clearObjectUrls = () => {
    objectUrls.current.forEach((url) => URL.revokeObjectURL(url));
    objectUrls.current = [];
  };

  const refresh = async () => {
    if (!loadApiSettings().apiUrl) {
      clearObjectUrls();
      setGallery([]);
      setError("Configure the backend in Settings.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const allItems: GalleryItem[] = [];
      let page = 1;
      let hasMore = true;
      while (hasMore) {
        const response = await getGallery(page, 100);
        allItems.push(...response.items);
        hasMore = response.has_more;
        page += 1;
      }
      const newObjectUrls: string[] = [];
      const hydrated: GalleryItem[] = [];
      // Keep browser and API concurrency bounded when a large gallery is opened.
      for (let offset = 0; offset < allItems.length; offset += 8) {
        const batch = await Promise.all(
          allItems.slice(offset, offset + 8).map(async (item) => {
            try {
              const blob = await fetchAsset(item.preview_url);
              const thumbnailObjectUrl = URL.createObjectURL(blob);
              newObjectUrls.push(thumbnailObjectUrl);
              return { ...item, thumbnailObjectUrl };
            } catch {
              return item;
            }
          }),
        );
        hydrated.push(...batch);
      }
      clearObjectUrls();
      objectUrls.current = newObjectUrls;
      setGallery(hydrated);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load gallery");
    } finally {
      setLoading(false);
    }
  };

  const removeFromGallery = async (id: string) => {
    await deleteGalleryItem(id);
    await refresh();
  };

  const clearGallery = async () => {
    const ids = gallery.map((item) => item.id);
    const failures: string[] = [];
    for (const id of ids) {
      try {
        await deleteGalleryItem(id);
      } catch {
        failures.push(id);
      }
    }
    await refresh();
    if (failures.length) {
      throw new Error(`Could not delete ${failures.length} gallery item(s).`);
    }
  };

  useEffect(() => {
    void refresh();
    const listener = () => void refresh();
    window.addEventListener("gooni-api-settings-changed", listener);
    return () => {
      window.removeEventListener("gooni-api-settings-changed", listener);
      clearObjectUrls();
    };
    // Initial load is intentional.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <GalleryContext.Provider
      value={{ gallery, loading, error, refresh, removeFromGallery, clearGallery }}
    >
      {children}
    </GalleryContext.Provider>
  );
}

export function useGallery(): GalleryContextValue {
  const context = useContext(GalleryContext);
  if (!context) throw new Error("useGallery must be used inside GalleryProvider");
  return context;
}
