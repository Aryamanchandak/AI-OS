import { Component, type ErrorInfo, type ReactNode } from 'react';

type Props = { children: ReactNode };
type State = { error?: Error };

export class ErrorBoundary extends Component<Props, State> {
  state: State = {};

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('PRAXIS interface failure', error, info);
  }

  render(): ReactNode {
    if (this.state.error) {
      return (
        <main className="fatal-state">
          <p className="eyebrow">Interface halted</p>
          <h1>PRAXIS lost the thread.</h1>
          <p>{this.state.error.message}</p>
          <button type="button" onClick={() => window.location.reload()}>Reload cleanly</button>
        </main>
      );
    }
    return this.props.children;
  }
}
