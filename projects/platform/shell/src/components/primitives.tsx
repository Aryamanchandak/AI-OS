import { motion } from "framer-motion";
import type { ReactNode } from "react";

export function Button({
  children,
  onClick,
  tone = "quiet",
  disabled = false,
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  tone?: "primary" | "quiet" | "danger";
  disabled?: boolean;
  type?: "button" | "submit";
}) {
  return (
    <button
      type={type}
      className={`button ${tone}`}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}

export function Metric({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="metric">
      <span>{label}</span>
      <strong>{value ?? "Unknown"}</strong>
    </div>
  );
}

export function AdapterFrame({
  title,
  eyebrow,
  icon,
  aside,
  children,
}: {
  title: string;
  eyebrow: string;
  icon: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <motion.section
      className="workspace"
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35 }}
    >
      <header className="workspace-head">
        <div className="section-icon">{icon}</div>
        <div>
          <p className="eyebrow">{eyebrow}</p>
          <h1>{title}</h1>
        </div>
      </header>
      {aside && <aside className="metrics">{aside}</aside>}
      <div className="workspace-body">{children}</div>
    </motion.section>
  );
}
