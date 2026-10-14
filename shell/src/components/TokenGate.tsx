import { ArrowRight, KeyRound } from "lucide-react";
import { useState } from "react";

import { TOKEN_KEY } from "../storage";

export function TokenGate({
  onUnlock,
  storageKey = TOKEN_KEY,
  eyebrow = "Local gateway",
  title = "Enter your AI OS key.",
  description = "The key stays in this browser tab and protects every ingestion request.",
}: {
  onUnlock: (token: string) => void;
  storageKey?: string;
  eyebrow?: string;
  title?: string;
  description?: string;
}) {
  const [value, setValue] = useState("");

  return (
    <main className="token-gate">
      <section className="token-card">
        <div className="sigil"><KeyRound /></div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p>{description}</p>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            const token = value.trim();
            if (token) {
              sessionStorage.setItem(storageKey, token);
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
