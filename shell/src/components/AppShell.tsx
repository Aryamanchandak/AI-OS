import type { ReactNode } from "react";

export function AppShell({
  children,
  onLock,
  active = "ingestion",
}: {
  children: ReactNode;
  onLock: () => void;
  active?: "ingestion" | "channels" | "llm" | "observability" | "help";
}) {
  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/">
          <span>ARYA</span><strong>AI OS</strong>
        </a>
        <nav aria-label="Primary">
          <a className={active === "ingestion" ? "active" : ""} href="/ingestion"><span>01</span> Ingestion</a>
          <a className={active === "channels" ? "active" : ""} href="/channels"><span>02</span> Channels</a>
          <a className={active === "llm" ? "active" : ""} href="/llm"><span>03</span> LLM</a>
          <a className={active === "observability" ? "active" : ""} href="/observability"><span>04</span> Observability</a>
          <span className="future">Finance</span>
          <span className="future">Planner</span>
          <span className="future">Study</span>
          <a className={active === "help" ? "active" : ""} href="/help">Help</a>
        </nav>
        <button className="lock" onClick={onLock}>Lock</button>
      </header>
      <main className="main">{children}</main>
    </div>
  );
}
