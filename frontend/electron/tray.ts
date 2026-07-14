import { Menu, Tray, nativeTheme } from "electron";

let tray: Tray | null = null;

interface TrayOptions {
  onShow: () => void;
  onQuit: () => void;
  iconPath: (variant: "light" | "dark", size: 16 | 32) => string;
}

/** Windows taskbar tray: light mark on dark taskbars, dark mark on light ones. */
function currentVariant(): "light" | "dark" {
  return nativeTheme.shouldUseDarkColors ? "light" : "dark";
}

export function createTray(opts: TrayOptions) {
  tray = new Tray(opts.iconPath(currentVariant(), 16));
  tray.setToolTip("Corvus");

  const menu = Menu.buildFromTemplate([
    { label: "Show Corvus", click: opts.onShow },
    { type: "separator" },
    { label: "Quit Corvus", click: opts.onQuit },
  ]);
  tray.setContextMenu(menu);
  tray.on("click", opts.onShow);

  nativeTheme.on("updated", () => {
    tray?.setImage(opts.iconPath(currentVariant(), 16));
  });
}

export function destroyTray() {
  tray?.destroy();
  tray = null;
}
