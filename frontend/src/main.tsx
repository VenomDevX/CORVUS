import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import WidgetApp from "./WidgetApp";
import OverlayApp from "./OverlayApp";
import "./styles/index.css";
import { applyThemeVars } from "./lib/theme";
import { useCorvus } from "./state/store";

applyThemeVars(useCorvus.getState().theme);

const isWidget = window.location.hash.startsWith("#/widget");
const isOverlay = window.location.hash.startsWith("#/overlay");

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {isOverlay ? <OverlayApp /> : isWidget ? <WidgetApp /> : <App />}
  </React.StrictMode>,
);
