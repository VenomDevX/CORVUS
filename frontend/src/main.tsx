import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import WidgetApp from "./WidgetApp";
import OverlayApp from "./OverlayApp";
import "./styles/index.css";
import { applyThemeVars } from "./lib/theme";
import { useCorvus } from "./state/store";

applyThemeVars({
  theme: useCorvus.getState().theme,
  accentColor: useCorvus.getState().accentColor,
  fontFamily: useCorvus.getState().fontFamily,
  uiRoundness: useCorvus.getState().uiRoundness,
  appOpacity: useCorvus.getState().appOpacity,
  animationSpeed: useCorvus.getState().animationSpeed,
  uiScale: useCorvus.getState().uiScale
});

const isWidget = window.location.hash.startsWith("#/widget");
const isOverlay = window.location.hash.startsWith("#/overlay");

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {isOverlay ? <OverlayApp /> : isWidget ? <WidgetApp /> : <App />}
  </React.StrictMode>,
);
