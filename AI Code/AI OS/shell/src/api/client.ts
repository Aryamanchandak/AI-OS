import type { components } from "./schema";

const ROOT = "/api/ingestion";

export type Snapshot = components["schemas"]["RunSnapshotBody"];
export type View = components["schemas"]["ViewBody"];
export type Operation = Snapshot["operation"];
export type Pending = NonNullable<View["pending"]>;
export type Stage = components["schemas"]["StageBody"];
export type BookIdentityPending = components["schemas"]["BookIdentityPending"];
export type ImageOcrPending = components["schemas"]["ImageOcrPending"];
export type ImagePassage = components["schemas"]["ImagePassageBody"];
export type TextFilePending = components["schemas"]["TextFilePending"];
export type PhaseHandoffPending = components["schemas"]["PhaseHandoffPending"];
export type PhaseHandoffPayload = components["schemas"]["PhaseHandoffPayload"];
export type KnowledgeProposalPending = components["schemas"]["KnowledgeProposalPending"];
export type KnowledgeEnvelopePayload = components["schemas"]["KnowledgeEnvelopePayload"];
export type KnowledgeProposalPayload = components["schemas"]["KnowledgeProposalPayload"];
export type SiblingProposal = components["schemas"]["SiblingProposalBody"];
export type PhotoPassage = components["schemas"]["PhotoPassageBody"];
export type ReviewSignalBody = components["schemas"]["ReviewSignalBody"];
export type CleanupPending = components["schemas"]["CleanupPending"];
export type CleanupReviewPayload = components["schemas"]["CleanupReviewPayload"];
export type CleanupUnavailablePayload = components["schemas"]["CleanupUnavailablePayload"];
export type CleanupOccurrence = components["schemas"]["CleanupOccurrenceBody"];
export type Mapping = components["schemas"]["MappingBody"];
export type MappingList = components["schemas"]["MappingListBody"];
export type MappingCreate = components["schemas"]["MappingCreateBody"];
export type MappingUpdate = components["schemas"]["MappingUpdateBody"];
// The durable terminal record. Generated from the gateway contract rather than
// hand-written, so a backend report change breaks the build instead of quietly
// rendering nothing.
export type RunReport = components["schemas"]["RunReportBody"];
type GeneratedDecision = components["schemas"]["DecisionBody"];
export type Decision = Omit<GeneratedDecision, "resolver" | "note" | "expected_revision"> & { resolver?: string; note?: string; expected_revision: number };

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    // The operation the user was attempting. The error surface names it so a
    // bare "Request failed (500)" is still attributable.
    readonly request: string,
  ) {
    super(message);
  }
}

async function request<T>(
  path: string,
  token: string,
  name: string,
  init?: RequestInit,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${ROOT}${path}`, {
      ...init,
      headers: { "Authorization": `Bearer ${token}`, "Content-Type": "application/json", ...init?.headers },
    });
  } catch (cause) {
    // A network-level rejection carries no status. Zero marks "never reached
    // the gateway", which is a different recovery than any HTTP status.
    throw new ApiError(
      cause instanceof Error ? cause.message : "The gateway did not answer.",
      0,
      name,
    );
  }
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { detail?: string };
    throw new ApiError(body.detail || `Request failed (${response.status})`, response.status, name);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  snapshot: (token: string) => request<Snapshot>("/run", token, "Poll run"),
  start: (token: string) => request<Snapshot>("/run/start", token, "Start run", { method: "POST" }),
  retry: (token: string) => request<Snapshot>("/run/retry", token, "Retry stage", { method: "POST" }),
  decide: (token: string, body: Decision) => request<Snapshot>("/run/decision", token, "Submit decision", { method: "POST", body: JSON.stringify(body) }),
  report: (token: string, runId: string) =>
    request<RunReport>(`/run/${encodeURIComponent(runId)}/report`, token, "Fetch run report"),
  evidence: async (token: string, runId: string, itemId: string) => {
    const response = await fetch(`${ROOT}/evidence/${encodeURIComponent(runId)}/${encodeURIComponent(itemId)}`, { headers: { Authorization: `Bearer ${token}` } });
    if (!response.ok) throw new ApiError("Image evidence is no longer current.", response.status, "Load evidence");
    return URL.createObjectURL(await response.blob());
  },
  listMappings: (token: string, query = "") =>
    request<MappingList>(`/cleanup/mappings?query=${encodeURIComponent(query)}`, token, "List mappings"),
  createMapping: (token: string, body: MappingCreate) =>
    request<Mapping>("/cleanup/mappings", token, "Create mapping", { method: "POST", body: JSON.stringify(body) }),
  updateMapping: (token: string, mappingId: string, body: MappingUpdate) =>
    request<Mapping>(`/cleanup/mappings/${encodeURIComponent(mappingId)}`, token, "Update mapping", { method: "PATCH", body: JSON.stringify(body) }),
  deleteMapping: (token: string, mappingId: string) =>
    request<void>(`/cleanup/mappings/${encodeURIComponent(mappingId)}`, token, "Delete mapping", { method: "DELETE" }),
};
