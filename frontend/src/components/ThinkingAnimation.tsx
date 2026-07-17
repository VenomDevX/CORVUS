import { useEffect, useRef } from "react";

const FRAME_COUNT = 82; // frames 000 to 081
const W = 400;
const H = 320;
const frameUrl = (i: number) =>
  `./crow_hovering/Animate_SVG_crow_hovering_202607160206_${String(i).padStart(3, "0")}.svg`;

/**
 * Draws the crow frame sequence on a canvas, tinted to the foreground
 * color. Canvas is used instead of a CSS mask-image swap because a mask
 * that hasn't finished (re)loading paints the element unmasked — a solid
 * box flash.
 */
export function ThinkingAnimation({ 
  text = "Corvus is thinking…", 
  className = "h-8 w-10", 
  containerClassName = "flex flex-row items-center gap-3 py-1"
}: { 
  text?: React.ReactNode; 
  className?: string;
  containerClassName?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr = window.devicePixelRatio || 1;
    canvas.width = W * dpr;
    canvas.height = H * dpr;
    ctx.scale(dpr, dpr);

    // Inherited text color (text-fg on the canvas) is the tint.
    const fg = getComputedStyle(canvas).color;

    let cancelled = false;
    let timer: number | undefined;
    let frame = 0;

    const images = Array.from({ length: FRAME_COUNT }, (_, i) => {
      const img = new Image();
      img.src = frameUrl(i);
      return img;
    });

    // Nothing draws until every frame is decoded, so no partial frames.
    Promise.all(images.map((img) => img.decode().catch(() => undefined))).then(() => {
      if (cancelled) return;
      timer = window.setInterval(() => {
        const img = images[frame];
        frame = (frame + 1) % FRAME_COUNT;
        if (img.naturalWidth === 0) return;

        ctx.clearRect(0, 0, W, H);
        const s = Math.min(W / img.naturalWidth, H / img.naturalHeight);
        const w = img.naturalWidth * s;
        const h = img.naturalHeight * s;
        ctx.drawImage(img, (W - w) / 2, (H - h) / 2, w, h);
        // Recolor the black silhouette to the foreground color.
        ctx.globalCompositeOperation = "source-in";
        ctx.fillStyle = fg;
        ctx.fillRect(0, 0, W, H);
        ctx.globalCompositeOperation = "source-over";
      }, 40); // 25 fps
    });

    return () => {
      cancelled = true;
      if (timer) clearInterval(timer);
    };
  }, []);

  return (
    <div className={containerClassName}>
      <canvas ref={canvasRef} className={`${className} text-fg shrink-0`} />
      {text && <span className="text-sm font-medium text-fg-muted animate-pulse">{text}</span>}
    </div>
  );
}
