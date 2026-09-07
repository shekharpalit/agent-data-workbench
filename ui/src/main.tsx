import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import App from "./App";
import { sessionToken } from "./api";
import "./styles.css";

const token = sessionToken(
  location.hash,
  sessionStorage.getItem("agent-data-workbench-token") || "",
);
if (token) sessionStorage.setItem("agent-data-workbench-token", token);
if (location.hash)
  history.replaceState(null, "", location.pathname + location.search);
const client = new QueryClient({
  defaultOptions: {
    queries: { retry: false, staleTime: 10_000, refetchOnWindowFocus: false },
    mutations: { retry: false },
  },
});
const root = document.getElementById("root");
if (!root) throw new Error("Workbench mount point is missing.");
createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={client}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
