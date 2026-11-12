import { Component, type ErrorInfo, type ReactNode } from "react";

export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error(error, info); }
  render() {
    if (this.state.failed) return <main className="fatal"><p className="eyebrow">Interface fault</p><h1>The shell lost its place.</h1><p>Refresh to reconnect. No ingestion decision was submitted by this error.</p></main>;
    return this.props.children;
  }
}
