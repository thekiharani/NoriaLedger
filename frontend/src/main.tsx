import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { ApiError } from "@/lib/api";
import { makeRouter } from "./router";
import "./styles.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: (count, error) => !(error instanceof ApiError && [401, 403, 404, 417].includes(error.status)) && count < 2,
    },
  },
});

// Session expired -> back to login.
queryClient.getQueryCache().subscribe((event) => {
  const err = event.query.state.error;
  if (err instanceof ApiError && (err.status === 401 || (err.status === 403 && err.type === "AuthenticationError"))) {
    queryClient.setQueryData(["session"], { user: null, allow_signup: false });
    if (!window.location.pathname.startsWith("/login")) window.location.href = "/login";
  }
});

const router = makeRouter(queryClient);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
