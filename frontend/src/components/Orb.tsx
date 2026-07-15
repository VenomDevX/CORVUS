import { useEffect, useRef } from "react";
import type { OrbState } from "../lib/tokens";

interface OrbProps {
  state: OrbState;
  /** 0–1 live audio level; drives listening/speaking pulse */
  level?: number;
  size?: number;
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

export function Orb({ state, level = 0.5, size = 220 }: OrbProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const requestRef = useRef<number>();
  const angleRef = useRef(0);
  const lastTimeRef = useRef(performance.now());
  
  // Use a ref to always have the latest props inside the animation loop without restarting it
  const latestProps = useRef({ state, level, size });
  
  useEffect(() => {
    latestProps.current = { state, level, size };
  }, [state, level, size]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    // Handle high DPI displays
    const dpr = window.devicePixelRatio || 1;
    
    // The canvas needs to be large enough to handle scaling (max scale ~ 1.5)
    const baseSize = latestProps.current.size;
    const canvasSize = baseSize * 1.5; 
    
    canvas.width = canvasSize * dpr;
    canvas.height = canvasSize * dpr;
    canvas.style.width = `${canvasSize}px`;
    canvas.style.height = `${canvasSize}px`;
    ctx.scale(dpr, dpr);

    const animate = (time: number) => {
      const dt = time - lastTimeRef.current;
      lastTimeRef.current = time;

      const { state: currState, level: currLevel, size: currSize } = latestProps.current;
      
      ctx.clearRect(0, 0, canvasSize, canvasSize);

      // Animation parameters based on state
      let rotSpeed = 0.0005; // Base rotation speed
      let scaleMult = 1.0;
      
      if (currState === "idle") {
        rotSpeed = 0.0004;
        // Subtle breathing
        scaleMult = 1.0 + Math.sin(time / 800) * 0.03;
      } else if (currState === "listening") {
        rotSpeed = 0.0008;
        // Reacts to mic level slightly
        scaleMult = 1.0 + (currLevel * 0.15);
      } else if (currState === "thinking") {
        rotSpeed = 0.0025; // Spin faster
        scaleMult = 1.0 + Math.sin(time / 200) * 0.02; // Fast jitter/pulse
      } else if (currState === "speaking") {
        rotSpeed = 0.001;
        // No size bounce — speaking animates via the particle waves below
        scaleMult = 1.0;
      }

      angleRef.current += rotSpeed * dt;
      const angle = angleRef.current;
      
      const cosA = Math.cos(angle);
      const sinA = Math.sin(angle);
      
      const centerX = canvasSize / 2;
      const centerY = canvasSize / 2;
      
      // Radius of the sphere on screen
      const radius = (currSize * 0.45) * scaleMult;

      ctx.fillStyle = "#FFFFFF";

      for (let i = 0; i < PARTICLES.length; i++) {
        const p = PARTICLES[i];

        // Rotate around Y axis
        const xRot = p.x * cosA - p.z * sinA;
        const zRot = p.x * sinA + p.z * cosA;
        const yRot = p.y;

        let displX = 0;
        let displY = 0;
        if (currState === "thinking" || currState === "speaking") {
           displX = Math.sin(time * 0.01 + p.y * 10) * 0.05;
           displY = Math.cos(time * 0.01 + p.x * 10) * 0.05;
        }

        // Perspective projection; zRot ranges roughly -1..1
        const camZ = 2.5;
        const perspective = camZ / (camZ - zRot);

        const projX = centerX + (xRot + displX) * radius * perspective;
        const projY = centerY + (yRot + displY) * radius * perspective;

        // Depth shading: back dots fade to near-invisible dust
        const zNormalized = (zRot + 1) / 2;
        const depth = 0.45 + zNormalized * 0.55;

        // Slow independent twinkle per grain
        const twinkle =
          0.75 + 0.25 * Math.sin(time * p.twinkleSpeed + p.twinklePhase);

        ctx.globalAlpha = Math.min(p.alpha * depth * twinkle, 1);

        const s = p.size * (0.6 + zNormalized * 0.7);
        ctx.fillRect(projX - s / 2, projY - s / 2, s, s);
      }

      ctx.globalAlpha = 1;

      requestRef.current = requestAnimationFrame(animate);
    };

    requestRef.current = requestAnimationFrame(animate);

    return () => {
      if (requestRef.current) cancelAnimationFrame(requestRef.current);
    };
  }, []);

  return (
    <div
      role="img"
      aria-label={`Corvus orb — ${state}`}
      data-orb-state={state}
      className="relative flex items-center justify-center"
      style={{ width: size * 1.4, height: size * 1.4 }}
    >
       <canvas ref={canvasRef} className="pointer-events-none" />
    </div>
  );
}

