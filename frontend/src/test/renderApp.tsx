import { render } from "@testing-library/react";
import { RouterProvider } from "react-router-dom";
import { Providers } from "@/app/providers";
import { createQueryClient } from "@/app/queryClient";
import { createTestRouter } from "@/app/router";
import { setCsrfToken } from "@/api/client";

/** Render the real routes, providers and guards at `path`; only the network is stubbed. */
export function renderApp(path: string) {
  setCsrfToken(null);
  const client = createQueryClient();
  const router = createTestRouter([path]);
  const view = render(
    <Providers client={client}>
      <RouterProvider router={router} />
    </Providers>,
  );
  return { ...view, router, client };
}
