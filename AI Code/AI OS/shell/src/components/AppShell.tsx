import type { ReactNode } from "react";

export function AppShell({
  children,
  onLock,
}: {
  children: ReactNode;
  onLock: () => void;
}) {
  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/">
          <span>ARYA</span><strong>AI OS</strong>
        </a>
        <nav aria-label="Primary">
          <a className="active" href="/ingestion"><span>01</span> Ingestion</a>
          <span className="future">Finance</span>
          <span className="future">Planner</span>
          <span className="future">Study</span>
        </nav>
        <button className="lock" onClick={onLock}>Lock</button>
      </header>
      <main className="main">{children}</main>
    </div>
  );
}
