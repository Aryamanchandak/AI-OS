import { ArrowRight, KeyRound } from "lucide-react";
import { useState } from "react";

import { TOKEN_KEY } from "../storage";

export function TokenGate({ onUnlock }: { onUnlock: (token: string) => void }) {
  const [value, setValue] = useState("");

  return (
    <main className="token-gate">
      <section className="token-card">
        <div className="sigil"><KeyRound /></div>
        <p className="eyebrow">Local gateway</p>
        <h1>Enter your AI OS key.</h1>
        <p>The key stays in this browser tab and protects every ingestion request.</p>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            const token = value.trim();
            if (token) {
              sessionStorage.setItem(TOKEN_KEY, token);
              onUnlock(token);
            }
          }}
        >
          <label htmlFor="token">Bearer token</label>
          <input
            id="token"
            type="password"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            autoFocus
            autoComplete="off"
          />
          <button className="button primary" type="submit">
            Enter the workspace <ArrowRight size={17} />
          </button>
        </form>
      </section>
    </main>
  );
}
