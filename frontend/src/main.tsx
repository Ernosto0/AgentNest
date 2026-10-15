import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import "@/i18n";
import "./index.css";
import { Providers } from "./app/providers";
import { createQueryClient } from "./app/queryClient";
import { createAppRouter } from "./app/router";

const root = document.getElementById("root");
if (!root) throw new Error("#root element not found");

createRoot(root).render(
  <StrictMode>
    <Providers client={createQueryClient()}>
      <RouterProvider router={createAppRouter()} />
    </Providers>
  </StrictMode>,
);
