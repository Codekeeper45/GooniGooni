import { createBrowserRouter } from "react-router";
import { Root } from "./Root";
import { MediaGenApp } from "./components/MediaGenApp";
import { GalleryPage } from "./pages/GalleryPage";
import { AdminLoginPage } from "./admin/AdminLoginPage";
import { AdminDashboard } from "./admin/AdminDashboard";

export const router = createBrowserRouter([
  {
    path: "/",
    Component: Root,
    children: [
      { index: true, Component: MediaGenApp },
      { path: "gallery", Component: GalleryPage },
    ],
  },
  // Admin routes (standalone — no root layout, no API key needed on frontend)
  { path: "/admin", Component: AdminLoginPage },
  { path: "/admin/dashboard", Component: AdminDashboard },
]);
