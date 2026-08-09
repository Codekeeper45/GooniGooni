import { createBrowserRouter } from "react-router";
import { Root } from "./Root";
import { MediaGenApp } from "./components/MediaGenApp";
import { GalleryPage } from "./pages/GalleryPage";

export const router = createBrowserRouter([
  {
    path: "/",
    Component: Root,
    children: [
      { index: true, Component: MediaGenApp },
      { path: "gallery", Component: GalleryPage },
    ],
  },
]);
