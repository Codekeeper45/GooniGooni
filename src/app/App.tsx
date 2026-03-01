import { useEffect, useState } from "react";
import { RouterProvider } from "react-router";
import { router } from "./routes";
import { GalleryProvider } from "./context/GalleryContext";
import { GenerationProvider } from "./context/GenerationContext";
import { ensureGenerationSession } from "./utils/sessionClient";

export default function App() {
  const [sessionReady, setSessionReady] = useState(false);

  useEffect(() => {
    let active = true;
    ensureGenerationSession()
      .catch(() => {
        // Let the app render even if the first bootstrap request fails.
      })
      .finally(() => {
        if (active) {
          setSessionReady(true);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  if (!sessionReady) {
    return (
      <div
        className="min-h-screen flex items-center justify-center"
        style={{ background: "#0B0E14", color: "#9CA3AF", fontFamily: "'Space Grotesk', sans-serif" }}
      >
        Initializing session...
      </div>
    );
  }

  return (
    <GalleryProvider>
      <GenerationProvider>
        <RouterProvider router={router} />
      </GenerationProvider>
    </GalleryProvider>
  );
}
