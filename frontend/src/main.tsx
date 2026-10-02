import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "@/App";
// Bundled, not fetched: no third-party request on load, and the console
// renders identically on a machine with no outbound network.
import "@fontsource-variable/geist";
import "@fontsource-variable/bricolage-grotesque";
import "@fontsource-variable/jetbrains-mono";
import "@/styles/globals.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
