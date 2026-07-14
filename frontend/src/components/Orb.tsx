import { motion } from "framer-motion";
import { color, motion as motionTokens, type OrbState } from "../lib/tokens";

interface OrbProps {
  state: OrbState;
  /** 0–1 live audio level; drives listening/speaking pulse (Milestone 5 feeds real audio). */
  level?: number;
  size?: number;
}

const [gradA, gradB, gradC, gradD] = color.gradient.orb;

/**
 * The Corvus orb. Four states, from design/tokens.json motion.orb:
 * idle — slow breathing; listening — level-reactive pulse; thinking —
 * rotating conic shimmer; speaking — multi-ring waveform pulse.
 */
export function Orb({ state, level = 0.5, size = 220 }: OrbProps) {
  const idle = motionTokens.orb.idle;
  const listenAmp = 1 + (motionTokens.orb.listening.scaleRange[1] - 1) * level;
  const speakAmp = 1 + (motionTokens.orb.speaking.scaleRange[1] - 1) * level;

  const coreVariants = {
    idle: {
      scale: idle.scaleRange,
      opacity: idle.opacityRange,
      transition: { duration: 4, repeat: Infinity, repeatType: "mirror" as const, ease: "easeInOut" },
    },
    listening: {
      scale: [0.98, listenAmp],
      opacity: [0.9, 1],
      transition: { duration: 0.6, repeat: Infinity, repeatType: "mirror" as const, ease: "easeOut" },
    },
    thinking: {
      scale: 1,
      opacity: 1,
      transition: { duration: 0.3 },
    },
    speaking: {
      scale: [0.96, speakAmp],
      opacity: [0.92, 1],
      transition: { duration: 0.45, repeat: Infinity, repeatType: "mirror" as const, ease: "easeInOut" },
    },
  };

  const haloVariants = {
    idle: { scale: [1.05, 1.12], opacity: [0.25, 0.4] },
    listening: { scale: [1.05, 1.2], opacity: [0.3, 0.55] },
    thinking: { scale: [1.02, 1.08], opacity: [0.3, 0.45] },
    speaking: { scale: [1.08, 1.25], opacity: [0.35, 0.6] },
  };

  return (
    <div
      role="img"
      aria-label={`Corvus orb — ${state}`}
      data-orb-state={state}
      className="relative flex items-center justify-center"
      style={{ width: size * 1.4, height: size * 1.4 }}
    >
      {/* Outer halo */}
      <motion.div
        className="absolute rounded-full"
        style={{
          width: size,
          height: size,
          background: `radial-gradient(circle, ${gradB}55 0%, transparent 70%)`,
          filter: "blur(24px)",
        }}
        animate={haloVariants[state]}
        transition={{ duration: 2.4, repeat: Infinity, repeatType: "mirror", ease: "easeInOut" }}
      />

      {/* Speaking ring */}
      {state === "speaking" && (
        <motion.div
          className="absolute rounded-full border-2"
          style={{ width: size * 1.15, height: size * 1.15, borderColor: `${gradB}66` }}
          animate={{ scale: [1, 1.18], opacity: [0.6, 0] }}
          transition={{ duration: 0.9, repeat: Infinity, ease: "easeOut" }}
        />
      )}

      {/* Thinking shimmer (rotating conic sheen) */}
      {state === "thinking" && (
        <motion.div
          className="absolute rounded-full"
          style={{
            width: size * 1.06,
            height: size * 1.06,
            background: `conic-gradient(from 0deg, transparent 0%, ${gradA}88 12%, transparent 30%, transparent 55%, ${gradB}55 68%, transparent 85%)`,
            filter: "blur(6px)",
          }}
          animate={{ rotate: 360 }}
          transition={{ duration: 2.4, repeat: Infinity, ease: "linear" }}
        />
      )}

      {/* Core sphere */}
      <motion.div
        className="rounded-full"
        style={{
          width: size,
          height: size,
          background: `radial-gradient(circle at 38% 32%, ${gradA} 0%, ${gradB} 32%, ${gradC} 68%, ${gradD} 100%)`,
          boxShadow: `0 0 ${size / 4}px ${gradB}59, inset 0 0 ${size / 5}px ${gradD}CC`,
        }}
        variants={coreVariants}
        animate={state}
      />

      {/* Specular highlight */}
      <div
        className="pointer-events-none absolute rounded-full"
        style={{
          width: size * 0.5,
          height: size * 0.3,
          top: "22%",
          left: "30%",
          background: `radial-gradient(ellipse, #FFFFFF2E 0%, transparent 70%)`,
          filter: "blur(4px)",
        }}
      />
    </div>
  );
}
