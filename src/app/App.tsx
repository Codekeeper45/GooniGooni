import { RouterProvider } from "react-router";
import { router } from "./routes";
import { GalleryProvider } from "./context/GalleryContext";

export default function App() {
  return (
    <GalleryProvider>
      <RouterProvider router={router} />
    </GalleryProvider>
  );
}
