import { vi } from "vitest";

import type { RunReport, Snapshot } from "../api/client";

export type Route =
  | { kind: "json"; body: unknown }
  | { kind: "error"; status: number; detail: string }
  | { kind: "network" };

/**
 * A scripted gateway.
 *
 * Snapshots are supplied as a queue so a test can express "accepted, then
 * settled" the way the real 202-then-poll sequence behaves; the last entry
 * repeats for every later poll.
 */
export function fakeGateway(options: {
  snapshots: Snapshot[];
  start?: Route;
  decide?: Route;
  retry?: Route;
  report?: Route | RunReport;
}) {
  const snapshots = [...options.snapshots];
  const calls: { path: string; method: string }[] = [];

  const respond = (route: Route | undefined, fallback: unknown): Response => {
    const chosen: Route = route ?? { kind: "json", body: fallback };
    if (chosen.kind === "network") throw new TypeError("Failed to fetch");
    if (chosen.kind === "error") {
      return new Response(JSON.stringify({ detail: chosen.detail }), {
        status: chosen.status,
        headers: { "Content-Type": "application/json" },
      });
    }
    return new Response(JSON.stringify(chosen.body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  const current = () => snapshots[0];
  const advance = () => {
    if (snapshots.length > 1) snapshots.shift();
    return current();
  };
  const accepted = (name: string): Snapshot => ({
    ...current(),
    operation: { ...current().operation, state: "submitting", name },
  });

  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input);
    const method = init?.method ?? "GET";
    calls.push({ path, method });

    if (path.endsWith("/run") && method === "GET") {
      return respond(undefined, advance());
    }
    // A 202 from the real service reports the operation as in flight, because
    // ReviewService marks it under the same lock that accepts the call.
    if (path.endsWith("/run/start")) return respond(options.start, accepted("start"));
    if (path.endsWith("/run/decision")) return respond(options.decide, accepted("decision"));
    if (path.endsWith("/run/retry")) return respond(options.retry, accepted("retry"));
    if (path.includes("/report")) {
      const route = options.report;
      const isRoute = route !== undefined && "kind" in (route as Route);
      return respond(isRoute ? route as Route : undefined, route ?? {});
    }
    if (path.includes("/evidence/")) {
      return new Response(new Blob(["image"]), { status: 200 });
    }
    throw new Error(`unrouted request: ${method} ${path}`);
  });

  vi.stubGlobal("fetch", fetchMock);
  return {
    calls,
    fetchMock,
    /** Replace the queue, e.g. to make a retry succeed on the next poll. */
    setSnapshots(next: Snapshot[]) {
      snapshots.splice(0, snapshots.length, ...next);
    },
    called(path: string, method = "POST") {
      return calls.some((call) => call.path.endsWith(path) && call.method === method);
    },
  };
}
