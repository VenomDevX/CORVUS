import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import WidgetApp from "./WidgetApp";
import "./styles/index.css";
import { applyThemeVars } from "./lib/theme";
import { useCorvus } from "./state/store";

applyThemeVars(useCorvus.getState().theme);

const isWidget = window.location.hash.startsWith("#/widget");

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>{isWidget ? <WidgetApp /> : <App />}</React.StrictMode>,
);
