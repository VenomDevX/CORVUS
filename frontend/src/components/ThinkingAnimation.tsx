import { useEffect, useRef, useState } from "react";

const FRAME_COUNT = 82; // frames 000 to 081
const W = 400;
const H = 320;
const frameUrl = (i: number) =>
  `./crow_hovering/Animate_SVG_crow_hovering_202607160206_${String(i).padStart(3, "0")}.svg`;

const FACTS = [
  "Crows can recognize individual human faces.",
  "A group of crows is called a murder.",
  "Crows have been known to use tools.",
  "Corvus is pondering...",
  "Searching the depths of the local LLM...",
  "The first computer bug was a real moth.",
  "Crows hold grudges against humans who wrong them.",
  "Honey never spoils.",
  "Octopuses have three hearts.",
  "Bananas are berries, but strawberries aren't.",
  "Wombat poop is cube-shaped.",
  "A day on Venus is longer than a year on Venus.",
  "There are more trees on Earth than stars in the Milky Way.",
  "Water can boil and freeze at the same time.",
  "A jiffy is an actual unit of time.",
  "The Eiffel Tower can grow 15 cm in the summer.",
  "Sharks existed before trees.",
  "A cloud can weigh more than a million pounds.",
  "Cows have best friends.",
  "The moon is slowly moving away from Earth.",
  "Apples float because they are 25% air.",
  "Sloths can hold their breath longer than dolphins.",
  "Some cats are allergic to humans.",
  "It rains diamonds on Jupiter and Saturn.",
  "The shortest commercial flight is 57 seconds.",
  "A crocodile cannot stick its tongue out.",
  "Butterflies taste with their feet.",
  "Cats have 32 muscles in each ear.",
  "Tigers have striped skin, not just striped fur.",
  "A sneeze travels at about 100 miles per hour.",
  "Astronauts get taller in space.",
  "Pigs can't look up into the sky.",
  "Humans share 50% of their DNA with bananas.",
  "A flea can accelerate faster than a space shuttle.",
  "Most elephants weigh less than a blue whale's tongue.",
  "Dolphins sleep with one eye open.",
  "An ostrich's eye is bigger than its brain.",
  "Rabbits cannot vomit.",
  "Peanuts aren't technically nuts, they are legumes.",
  "A snail can sleep for three years.",
  "Sea otters hold hands when they sleep.",
  "The unicorn is the national animal of Scotland.",
  "Space smells like seared steak.",
  "The longest English word is 189,819 letters long.",
  "Koalas sleep up to 22 hours a day.",
  "Glass balls can bounce higher than rubber ones.",
  "There is a planet made of diamonds.",
  "Your nose can remember 50,000 different scents.",
  "Polar bear skin is black.",
  "Grapes light on fire in the microwave."
];

/**
 * Draws the crow frame sequence on a canvas, tinted to the foreground
 * color. Canvas is used instead of a CSS mask-image swap because a mask
 * that hasn't finished (re)loading paints the element unmasked — a solid
 * box flash.
 */
export function ThinkingAnimation({ 
  text, 
  className = "h-8 w-10", 
  containerClassName = "flex flex-row items-center gap-3 py-1"
}: { 
  text?: React.ReactNode; 
  className?: string;
  containerClassName?: string;
}) {
  const [fact, setFact] = useState(() => FACTS[Math.floor(Math.random() * FACTS.length)]);

  useEffect(() => {
    const interval = setInterval(() => {
      setFact(FACTS[Math.floor(Math.random() * FACTS.length)]);
    }, 4000);
    return () => clearInterval(interval);
  }, []);

  const displayText = text !== undefined ? text : fact;

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
      {displayText && <span className="text-xs font-medium text-fg-muted animate-pulse">{displayText}</span>}
    </div>
  );
}
