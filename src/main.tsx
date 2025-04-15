import React from "react";
import { createRoot } from "react-dom/client";
import { SalesNavFrontendLive } from "./SalesNavFrontendLive";

// Haupt-Render-Komponente für das Frontend
const container = document.getElementById("root") as HTMLElement;
const root = createRoot(container);

root.render(
  <React.StrictMode>
    <SalesNavFrontendLive />
  </React.StrictMode>
);
