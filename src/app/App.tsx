import { RouterProvider } from "react-router";
import { router } from "./routes";
import { GalleryProvider } from "./context/GalleryContext";
import { GenerationProvider } from "./context/GenerationContext";

export default function App() {
  return (
    <GalleryProvider>
      <GenerationProvider>
        <RouterProvider router={router} />
      </GenerationProvider>
    </GalleryProvider>
  );
}
