import { useEffect, useRef } from "react";
import type { OrbState } from "../lib/tokens";
import { useCorvus } from "../state/store";

interface OrbProps {
  state: OrbState;
  /** 0–1 live audio level; drives listening/speaking pulse */
  level?: number;
  size?: number;
  backgroundMode?: boolean;
}

interface Particle {
  x: number;
  y: number;
  z: number;
  size: number;
  alpha: number;
  twinklePhase: number;
  twinkleSpeed: number;
}

// Stochastic dust-on-a-shell distribution: uniform random directions (no
// lattice pattern), most particles pinned near the surface, a small fraction
// drifting outward so the silhouette has a fuzzy, scattered edge.
function makeDustSphere(samples: number): Particle[] {
  const particles: Particle[] = [];

  for (let i = 0; i < samples; i++) {
    // Uniform direction on the sphere via normalized gaussian vector
    let dx = 0;
    let dy = 0;
    let dz = 0;
    let len = 0;
    do {
      dx = Math.random() * 2 - 1;
      dy = Math.random() * 2 - 1;
      dz = Math.random() * 2 - 1;
      len = Math.hypot(dx, dy, dz);
    } while (len < 0.0001 || len > 1);
    dx /= len;
    dy /= len;
    dz /= len;

    // Radial placement: mostly a tight shell, ~10% loose outer dust
    let r: number;
    if (Math.random() < 0.1) {
      r = 1 + Math.random() * Math.random() * 0.14;
    } else {
      r = 1 - Math.random() * Math.random() * 0.12;
    }

    // Pole glints: dots near the top/bottom get brighter and slightly larger;
    // a narrow equatorial band thins out, like the reference's dark seam.
    const poleBoost = Math.pow(Math.abs(dy), 4) * 1.8;
    const equatorDim = 1 - 0.55 * Math.exp(-((dy / 0.07) ** 2));

    // Mostly sub-pixel dust with rare brighter grains
    const size = 0.6 + Math.random() * Math.random() * 1.3 + poleBoost * 0.6;
    const alpha =
      (0.4 + Math.random() * 0.6) * equatorDim * (0.6 + poleBoost);

    particles.push({
      x: dx * r,
      y: dy * r,
      z: dz * r,
      size,
      alpha: Math.min(alpha, 1),
      twinklePhase: Math.random() * Math.PI * 2,
      twinkleSpeed: 0.0008 + Math.random() * 0.0025,
    });
  }
  return particles;
}

const PARTICLES = makeDustSphere(14000);

// For smoothing the explosion transition
function lerp(start: number, end: number, amt: number) {
  return (1 - amt) * start + amt * end;
}

export function Orb({ state, level = 0.5, size = 220, backgroundMode = false }: OrbProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const requestRef = useRef<number>();
  const angleRef = useRef(0);
  const lastTimeRef = useRef(performance.now());
  
  const theme = useCorvus((s) => s.theme);
  const latestProps = useRef({ state, level, size, backgroundMode, theme });
  
  // Interpolated values for smooth explosion transition
  const animStateRef = useRef({
    scale: 1.0,
    opacity: 1.0,
    particleSpread: 1.0,
  });
  
  useEffect(() => {
    latestProps.current = { state, level, size, backgroundMode, theme };
  }, [state, level, size, backgroundMode, theme]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const container = containerRef.current;
    if (!canvas || !container) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let canvasWidth = 0;
    let canvasHeight = 0;

    const updateSize = () => {
      const dpr = window.devicePixelRatio || 1;
      const { size: currSize, backgroundMode: currBg } = latestProps.current;
      
      if (currBg) {
        const rect = container.getBoundingClientRect();
        canvasWidth = rect.width;
        canvasHeight = rect.height;
      } else {
        canvasWidth = currSize * 1.5;
        canvasHeight = currSize * 1.5;
      }
      
      canvas.width = canvasWidth * dpr;
      canvas.height = canvasHeight * dpr;
      canvas.style.width = `${canvasWidth}px`;
      canvas.style.height = `${canvasHeight}px`;
      ctx.setTransform(1, 0, 0, 1, 0, 0); // reset transform before scale
      ctx.scale(dpr, dpr);
    };

    updateSize();

    const resizeObserver = new ResizeObserver(() => {
      if (latestProps.current.backgroundMode) {
        updateSize();
      }
    });
    resizeObserver.observe(container);

    const animate = (time: number) => {
      const dt = time - lastTimeRef.current;
      lastTimeRef.current = time;

      const { state: currState, level: currLevel, size: currSize, backgroundMode: currBg } = latestProps.current;
      
      // We calculate a target scale based on the screen size so it fills the screen
      const maxDim = Math.max(canvasWidth, canvasHeight);
      const targetScale = currBg ? (maxDim / (currSize * 0.45)) * 0.8 : 1.0;
      
      // When in background mode, drop opacity but keep them visible
      const targetOpacity = currBg ? 0.75 : 1.0;
      const targetSpread = currBg ? 2.5 : 1.0; 
      
      // Slower, more majestic explosion
      const lerpSpeed = 0.015; 
      animStateRef.current.scale = lerp(animStateRef.current.scale, targetScale, lerpSpeed);
      animStateRef.current.opacity = lerp(animStateRef.current.opacity, targetOpacity, lerpSpeed);
      animStateRef.current.particleSpread = lerp(animStateRef.current.particleSpread, targetSpread, lerpSpeed);

      ctx.clearRect(0, 0, canvasWidth, canvasHeight);

      let rotSpeed = 0.0005; 
      let stateScaleMult = 1.0;
      
      if (currState === "idle") {
        rotSpeed = 0.0004;
        stateScaleMult = 1.0 + Math.sin(time / 800) * 0.03;
      } else if (currState === "listening") {
        rotSpeed = 0.0008;
        stateScaleMult = 1.0 + (currLevel * 0.15);
      } else if (currState === "thinking") {
        rotSpeed = currBg ? 0.001 : 0.0025; 
        stateScaleMult = 1.0 + Math.sin(time / 200) * 0.02;
      } else if (currState === "speaking") {
        rotSpeed = 0.001;
        stateScaleMult = 1.0;
      }

      angleRef.current += rotSpeed * dt;
      const angle = angleRef.current;
      
      const cosA = Math.cos(angle);
      const sinA = Math.sin(angle);
      
      const centerX = canvasWidth / 2;
      const centerY = canvasHeight / 2;
      
      const baseRadius = (currSize * 0.45);
      const radius = baseRadius * stateScaleMult * animStateRef.current.scale;
      
      const spread = animStateRef.current.particleSpread;
      const globalOp = animStateRef.current.opacity;

      let orbColor = "#FFFFFF";
      switch(latestProps.current.theme) {
        case "light": orbColor = "#000000"; break;
        case "pink": orbColor = "#831843"; break;
        case "green": orbColor = "#ECFDF5"; break;
        case "blue": orbColor = "#F8FAFC"; break;
        case "purple": orbColor = "#F5F3FF"; break;
        case "dark":
        default:
          orbColor = "#FFFFFF"; break;
      }
      ctx.fillStyle = orbColor;

      for (let i = 0; i < PARTICLES.length; i++) {
        const p = PARTICLES[i];

        // Expand the sphere outward by the spread factor
        const px = p.x * spread;
        const py = p.y * spread;
        const pz = p.z * spread;

        const xRot = px * cosA - pz * sinA;
        const zRot = px * sinA + pz * cosA;
        const yRot = py;

        let displX = 0;
        let displY = 0;
        if (currState === "thinking" || currState === "speaking") {
           displX = Math.sin(time * 0.01 + p.y * 10) * 0.05 * spread;
           displY = Math.cos(time * 0.01 + p.x * 10) * 0.05 * spread;
        }

        const camZ = 2.5 * spread; 
        const perspective = camZ / (camZ - zRot);

        const projX = centerX + (xRot + displX) * radius * perspective;
        const projY = centerY + (yRot + displY) * radius * perspective;

        const zNormalized = (zRot / spread + 1) / 2;
        const depth = 0.45 + zNormalized * 0.55;

        const twinkle =
          0.75 + 0.25 * Math.sin(time * p.twinkleSpeed + p.twinklePhase);

        ctx.globalAlpha = Math.min(p.alpha * depth * twinkle, 1) * globalOp;

        // Keep particle sizes from getting too enormous by squaring the scale factor
        const particleScale = Math.pow(animStateRef.current.scale, 0.4);
        const s = p.size * (0.6 + zNormalized * 0.7) * particleScale;
        
        ctx.fillRect(projX - s / 2, projY - s / 2, s, s);
      }

      ctx.globalAlpha = 1;
      requestRef.current = requestAnimationFrame(animate);
    };

    requestRef.current = requestAnimationFrame(animate);

    return () => {
      if (requestRef.current) cancelAnimationFrame(requestRef.current);
      resizeObserver.disconnect();
    };
  }, []);

  return (
    <div
      ref={containerRef}
      role="img"
      aria-label={`Corvus orb — ${state}`}
      data-orb-state={state}
      className={`flex items-center justify-center ${backgroundMode ? "absolute inset-0 w-full h-full overflow-hidden pointer-events-none z-0" : "relative"}`}
      style={!backgroundMode ? { width: size * 1.4, height: size * 1.4 } : undefined}
    >
       <canvas ref={canvasRef} className="pointer-events-none" />
    </div>
  );
}
