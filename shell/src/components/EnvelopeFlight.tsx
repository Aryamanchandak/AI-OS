import { motion } from "framer-motion";
import { Sparkles } from "lucide-react";

export function EnvelopeFlight({ onDone }: { onDone: () => void }) {
  return (
    <motion.div
      className="flight"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      onAnimationComplete={() => window.setTimeout(onDone, 1800)}
      role="status"
      aria-live="polite"
      data-testid="envelope-flight"
    >
      <div className="flight-copy">
        <p className="eyebrow">Approved and sent</p>
        <h2>Your highlight is on its way.</h2>
      </div>
      <motion.div
        className="envelope"
        initial={{ x: "-45vw", y: 90, rotate: -9, scale: 0.65 }}
        animate={{
          x: ["-45vw", "0vw", "38vw"],
          y: [90, -35, -180],
          rotate: [-9, 4, 13],
          scale: [0.65, 1, 0.62],
          opacity: [0, 1, 0],
        }}
        transition={{ duration: 1.65, ease: [0.16, 1, 0.3, 1] }}
      >
        <span className="envelope-flap" />
        <Sparkles className="spark one" />
        <Sparkles className="spark two" />
      </motion.div>
    </motion.div>
  );
}
