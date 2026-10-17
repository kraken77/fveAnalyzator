import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import DevBanner from "./components/DevBanner";
import App from "./App.tsx";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {/* Pas "Vývojová verze" nad celým app — vidět i na /login i /p/{code} */}
    <DevBanner />
    <App />
  </StrictMode>,
);
