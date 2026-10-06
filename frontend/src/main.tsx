import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";

import { AppProviders, createQueryClient } from "./app/providers";
import { createAppRouter } from "./app/router";
import { configureI18n } from "./lib/i18n/t";

configureI18n({ search: window.location.search });

// One query client serves the providers and the session loader of the route table (DG-FE-02, DG-FE-04).
const queryClient = createQueryClient();
const router = createAppRouter(queryClient);

const container = document.getElementById("root");
if (container === null) {
  throw new Error("index.html has no #root element");
}
createRoot(container).render(
  <StrictMode>
    <AppProviders queryClient={queryClient}>
      <RouterProvider router={router} />
    </AppProviders>
  </StrictMode>,
);
