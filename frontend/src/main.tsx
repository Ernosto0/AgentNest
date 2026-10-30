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

const appRoot = createRoot(root);

// Local specimens only: the production build removes this branch and its module.
if (import.meta.env.DEV && new URLSearchParams(window.location.search).get("ui-reference") === "1") {
  void import("./dev/DesignReference").then(({ DesignReference }) => {
    appRoot.render(<StrictMode><DesignReference /></StrictMode>);
  });
} else {
  appRoot.render(
    <StrictMode>
      <Providers client={createQueryClient()}>
        <RouterProvider router={createAppRouter()} />
      </Providers>
    </StrictMode>,
  );
}
