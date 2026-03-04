import { useEffect, useState } from "react";
import { RouterProvider } from "react-router";
import { router } from "./routes";
import { GalleryProvider } from "./context/GalleryContext";
import { GenerationProvider } from "./context/GenerationContext";
import { ensureGenerationSession } from "./utils/sessionClient";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { useOnboarding, OnboardingScreen } from "./components/OnboardingScreen";

export default function App() {
  const [sessionReady, setSessionReady] = useState(false);
  const { showOnboarding, dismissOnboarding } = useOnboarding();

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
        Загрузка сессии...
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <GalleryProvider>
        <GenerationProvider>
          {showOnboarding && <OnboardingScreen onDismiss={dismissOnboarding} />}
          <RouterProvider router={router} />
        </GenerationProvider>
      </GalleryProvider>
    </ErrorBoundary>
  );
}
