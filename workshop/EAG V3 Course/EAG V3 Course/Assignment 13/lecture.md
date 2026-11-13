Session 13: Graphs, Memory, Semantic Chunking, and A2A
1. What this session is
In Session 9 we built an agent that could plan and use tools. In Session 11 we gave it channels. In Session 12 we put walls around the components that should not trust one another. This session makes the agent continue: continue after one worker returns, continue after the process restarts, continue across a second conversation, and continue when part of the work belongs to an agent built by somebody else. A fundamental extension of our graph-based architecture.

We build and run glc_v3, locally (post evaluation v4 will merge everything). It keeps the gateway and channel work from the previous sessions (without the security added) and adds four pieces that have to work together:

a live task graph that grows from outcomes instead of pretending the whole future is known at the start,
a memory service that knows what may be saved, who owns it, where it came from, and what has replaced it,
Rohan's semantic chunking V2, where a local model finds topic boundaries before Nomic embeds the chunks,
an A2A boundary, so a remote agent can join the graph through thet Agent2Agent protocol without inheriting local authority.
The code for glc_v3 is shared. The examples in this session are replays from the running gateway, with prompts, graph events, five Gemini keys routed as five independently metered providers, local Phi-4 segmentation, local Nomic embeddings, persisted FAISS search, and an official A2A gRPC task.


The same asyncio prompt, planned two ways. Leave it on Screenplay planner to watch the old planner invent three fetch tasks before search has run — their inputs do not exist yet. Flip to Live graph and press Run it live: search runs alone, and only after it returns three URLs does the graph earn its three fetches, then a distiller, then an answer. Every node arrives because an outcome justified it.

2. First, watch the old graph lie
Give a Session 9-style planner this prompt:

Search for 'Python asyncio best practices', read the top 3 results,
and give me a short numbered list of the advice they agree on.
The planner usually returns a complete graph immediately.

search

fetch result 1

fetch result 2

fetch result 3

distill

answer

It looks intelligent, but one detail makes it risky. Before search runs, the system does not know which URLs exist. It has invented three future tasks whose inputs may be wrong.

The same failure becomes expensive on a less tidy prompt. A planner sees “research three cities” and spawns ten workers, a verifier, a formatter, and three fallbacks. The first two results may already settle the question, but every future node has to finish. A planner that draws the whole graph once is not a great strategy; it assumes determinism, but the very reason to work with LLMs was, the world is non-deterministic!

The correction is almost embarrassingly simple:

The graph may contain only work the system can justify now. An outcome earns the next piece of graph.

For the asyncio prompt, glc_v3 starts with one node.

run_started
  └── graph_patched: add [search]
        └── task_started: search
The search returns three URLs. Only then does the graph gain three fetches.

task_succeeded: search (3 URLs discovered)
  └── graph_patched: add [fetch_1, fetch_2, fetch_3]
        ├── task_started: fetch_1
        ├── task_started: fetch_2
        └── task_started: fetch_3
All three fetches start together because they are now independent and justified. They do not wait for one another to finish before the runtime notices an outcome. The executor waits for FIRST_COMPLETED, gives that result to the planner, keeps the other workers alive, and fills any worker slot opened by the new patch. When the evidence is complete, the graph adds a distiller, then an answer worker.

The result contained six practices the sources agreed on:

use asyncio for I/O-bound work,
never block the event loop,
actually await or schedule coroutines,
use async context managers,
bound concurrency, and
handle task exceptions.
More important is the order in which the evidence came into existence. The graph did not know the URLs until search returned them.

That is what live means here. It does not mean an animated DAG on a dashboard. It means the data structure changes because the world answered back. This is how Claude Code, Hermes and other Agent works and one of the biggest drawback of our EAG V1/2/3 code till now.

3. The live graph, from first principles
A graph needs only four nouns.

Noun	Plain meaning
Task	One named unit of work with a stable ID, a skill, and typed input.
Event	Something that has already happened: a run began, a task succeeded, a task failed, an external result arrived.
Snapshot	The graph exactly as it is now: nodes, states, edges, and whether the run is finished.
Patch	The only legal way the planner changes the graph after seeing one event.
The patch is the important choice. The model does not receive a Python object it can mutate. It proposes a small, validated change.

@dataclass(frozen=True)
class GraphPatch:
    add: tuple[TaskSpec, ...] = ()
    connect: tuple[tuple[str, str], ...] = ()
    cancel: tuple[str, ...] = ()
    wait: tuple[str, ...] = ()
    resume: tuple[str, ...] = ()
    finish: bool = False
    reason: str = ""
Read those fields as six ordinary sentences.

add: this outcome made new work possible.
connect: this new work depends on this earlier work.
cancel: this outcome made some work unnecessary.
wait: this node is alive, but the next event must come from outside this process.
resume: the external event has arrived; the parked node can continue.
finish: the completion contract is now satisfied.
The node states are equally literal.

pending → running → succeeded
                  ↘ failed
pending/running   → cancelled
pending/running   → waiting → pending → running
waiting is not failure and it is not a slow coroutine. It means the local runtime has deliberately released the worker while it waits for a human approval, a webhook, an A2A push, or any other external event. That distinction is what lets an agent sleep for six hours without holding a Python task or a machine open for six hours.

The executor loop
The whole runtime idea fits in one loop.

while not finished:
    launch_ready_nodes(up_to=max_workers)
    done = await asyncio.wait(in_flight, return_when=asyncio.FIRST_COMPLETED)

    for outcome in done:
        event = store.record_outcome(outcome)
        patch = await planner.plan(store.snapshot(), event)
        store.apply_patch(patch, trigger_event=event.sequence)
        cancel_workers_the_patch_cancelled()
There is no wave-wide barrier. Suppose London, Paris, and Berlin researchers start together. London finishes first and reveals that the task needs a currency normalizer. The graph may add and launch that normalizer while Paris and Berlin are still running. gather() over a fixed list cannot do that, because the list and the barrier were chosen before any result existed.

The planner is powerful, and fenced
glc_v3 uses two planners together.

The deterministic capability planner understands known intents and invariants: a file must be indexed before it is recalled; evidence must exist before the answer; a birthday fact must be durable before calendar files are written. It is the safe fallback.

The constrained model planner receives the original goal, current snapshot, and newest event. It may propose only registered roles and a valid GraphPatch. Unknown skills, duplicate task IDs, invalid edges, widened file access, and malformed output are rejected. If the model cannot produce a legal patch, the deterministic planner continues the run.

This division is deliberate. The model decides what is useful. Code decides what is possible.

A live graph has to survive death
An in-memory graph is a demo. A real graph is an event journal plus current state.

Every run persists:

the original prompt and ownership scope,
every task and edge,
every state transition,
every result and failure,
every patch and the event that triggered it.
The last item makes patch application idempotent. If event 42 already triggered a patch, replaying event 42 after a crash does not add the same nodes twice. On restart, succeeded nodes stay succeeded. Nodes that were running return to pending, because the process died before it could record an outcome. Terminal events that landed before their planner patch are replayed before new work launches.

The invariant is:

An outcome is durable before it is allowed to create more work.

That one ordering prevents the two ugliest crash bugs: losing a result that already happened, and launching its follow-up twice.


Press Next event through the actual shape of the asyncio run, and watch the durable journal fill beside the graph. Switch to Slow sibling to see a child launch before the other frontier node finishes; switch to Crash replay to restart mid-run and watch a durable outcome replay without its patch being applied twice.

4. Five Gemini keys as workers
Session 9 theoretucally allowed more than one Gemini API key and was converted to reality by one of our student Pradeep E. glc_v3 keeps that path and makes it visible to the agent runtime. Loading .env with python-dotenv discovers the configured slots and registers them as gemini_1, gemini_2, and so on. Secret values are never logged. The router sees separate provider budgets and rotates work across them.

In the proof run, all five configured keys were active with gemini-3.1-flash-lite. The three-city prompt produced this graph:

London researcher (Gemini 1) ─┐
Berlin researcher (Gemini 2) ─┼→ distiller (Gemini 4) → answer (Gemini 5)
Paris researcher  (Gemini 3) ─┘
All three task_started events appeared before the first task_succeeded. The result estimated London at roughly 9.2–9.8 million, Berlin at 3.69–3.78 million, and Paris at about 2.06 million, identifying Berlin and Paris as the closest pair by about 1.64 million.

The gateway does not confuse parallelism with unlimited fan-out. max_workers bounds the local frontier. Provider budgets, rate state, and cost accounting remain gateway concerns. A planner may ask for twenty independent researchers; the executor admits only as many as the configured system can support.

Do not put keys in a list inside an agent prompt and ask the model to choose. Provider selection is infrastructure. The agent receives the provider name in its trace after routing, never the credential.


Run the three-city prompt and watch three researchers start together across gemini_1, gemini_2, and gemini_3, each metering its own provider budget. Lower max_workers and the third researcher waits for a slot instead of launching. The trace shows the routing decision; the credential never appears.

5. The memory problem is smaller than it sounds
Ask the agent:

My mom's birthday is 15 May 2026. Remember that and give me a calendar
reminder for two weeks before and on the day.
A weak memory implementation embeds the whole conversation and puts it in a vector database. The next time “mom” appears, it retrieves whichever chunk is mathematically nearby. That is not memory. It is similarity search over an ungoverned transcript.

The useful question is simpler:

What should survive this turn, for whom, and with what evidence?

The answer has five parts.

Type: this is a fact, not a chat transcript and not a policy.
Scope: it belongs to this tenant, project, user, and agent.
Source: the user said it in this API run.
State: it is current until corrected, then the old value is superseded rather than erased.
Authority: an agent may propose this fact; it may not write security policy or forge audit history.
That is the whole memory architecture in one sentence:

Memory is a typed, owned, sourced record. Search is only how we find candidate records later.

The birthday run began with two independent nodes: recall anything already known and write the explicit new fact. The fact write returned:

{
  "kind": "fact",
  "text": "Mom's birthday is 15 May 2026.",
  "sources": ["api://agent/runs"]
}
Only after that durable write did the graph add calendar_writer, which created two real .ics artifacts for 1 May and 15 May. A second run asked:

When is mom's birthday?
The answer was:

You told me that your mom's birthday is 15 May 2026 [source: api://agent/runs].
Notice what it did not cite: its own earlier answer. The source stayed the user's statement.

6. Seven kinds, because different things must behave differently
The easiest way to understand the store is a cabinet with seven drawers. They share storage machinery and do not share permissions or duration/lifetime.

Drawer	What belongs there	Typical lifetime	Who may write
Working	Scratch state needed inside one run	Minutes or one run	Runtime
Episode	What happened in a run, including the user's request and produced answer	Long enough for history and replay	Runtime
Fact	A stable claim such as a birthday, preference, or project decision	Until corrected or expired	Authorized agent/gateway
Playbook	A procedure that worked and is worth reusing	Until revised	Authorized learning path
Policy	A rule that constrains behavior	Until an operator changes it	Operator/system only
Audit	What the system actually did	Retention policy	Gateway append-only
Document chunk	A sourced span of an indexed document	Current document version	Indexer
Why not one memories table with a free-text tag? Because the difference is operational.

A fact can be superseded.
A policy needs a stronger writer.
An audit event cannot be edited by the model.
A working note should disappear.
A document chunk needs a source span and neighbouring chunks. If the differences live only in a prompt, compaction can erase them exactly as Session 11's safety failures warned us.

Every record has this shape:

MemoryRecord(
    kind=MemoryKind.FACT,
    scope=MemoryScope(
        tenant_id="course",
        project_id="s13",
        user_id="rohan",
        agent_id="assistant",
    ),
    text="Mom's birthday is 15 May 2026.",
    sources=[SourceRef(uri="api://agent/runs", author="rohan")],
    principal=Principal(id="assistant", role="agent"),
    confidence=1.0,
)
Scope first, similarity second
The dangerous retrieval pipeline is:

search every vector → take nearest records → check whether caller may see them
Even if unauthorized text is removed at the end, scores, timing, counts, logs, and model context may already reveal that it exists. glc_v3 reverses the order conceptually:

caller identity → allowed scope and kinds → current records → candidate search
→ neighbour expansion → evidence cards
Tenant, project, user, agent, and optional run form the ownership path. A broader caller may intentionally read a narrower level only when code grants that relationship. A prompt saying “I am the operator” changes nothing, because Principal comes from the authenticated gateway, not model text.

Write less, but write deliberately
Not every turn becomes a fact. The runtime always keeps enough episode history for replay, but durable fact and playbook writes need a reason:

the user explicitly said “remember”,
a stable preference or correction will change future work,
a project decision would otherwise be rediscovered,
a repeated successful procedure deserves promotion into a playbook.
Raw tool output, temporary paths, guesses, and easily re-fetched public facts do not become durable personal memory by default.

Correction means supersession
If the user later says the birthday is 16 May, the store does not overwrite the old row and destroy history. It writes a new current fact with supersedes_id pointing to the earlier record, and marks the earlier record superseded. Normal recall sees only the current value. Audit and debugging can still explain what changed and when.

mem_001  15 May  status=superseded
    ↑ superseded by
mem_014  16 May  status=current
Deletion and expiry are separate operations. A correction is not evidence that the earlier record never existed.

Retrieval returns evidence, not loose text
A memory hit sent to a reasoning worker carries record ID, kind, text, source URI, score, and scope. The final answer can cite it. The model is asked to distinguish three things:

stated: the source directly says it,
derived: deterministic code computed it from stated values,
inferred: the model is making a plausible connection the source does not state.
This distinction mattered in the five-paper benchmark. Nomic retrieval correctly surfaced semantically related papers for a question about credit assignment, even though the phrase was absent. The final answer still said the supplied papers did not explicitly discuss credit assignment, explained what each paper actually covered, and labelled the relationship as inference. Good retrieval finds useful candidates. It does not manufacture support.


Open the seven drawers to see how each type behaves. Then switch to the lifecycle view: write a birthday, correct it, change the caller scope, and recall it. The record history stays visible while the authorized answer changes. Toggle FAISS is the source of truth to see why the architecture breaks.

7. How this relates to Claude Code and Hermes
By mid-2026 the best coding agents have converged on a useful pattern: keep a small, inspectable memory index in startup context and load detail only when it becomes relevant.

Claude Code separates human-authored CLAUDE.md instructions from agent-authored auto memory. Its project memory has a concise MEMORY.md entry point and optional topic files read on demand; project, user, and organization instructions have explicit filesystem scopes. Its own documentation is also careful that these files are context, not enforcement. Permissions and hooks carry the guarantees. See How Claude remembers your project.

Hermes keeps bounded MEMORY.md and USER.md stores, nudges the agent to curate useful learnings, searches past sessions, and promotes successful procedures into skills. The useful idea is the closed learning loop: experience may become a reusable procedure instead of remaining dead transcript. See Hermes persistent memory.

glc_v3 takes the shared insight and adds the guarantees our gateway needs.

Pattern	Claude Code / Hermes insight	glc_v3 addition
Small startup context	Keep the always-loaded memory curated	Retrieve typed evidence for the current task; do not inject the database
Human rules vs learned notes	Separate instructions from agent learning	Policy is a separate type with operator-only writes
Scoped project knowledge	Memory belongs to a repo/profile	Tenant/project/user/agent/run ownership is checked in code
On-demand detail	Read topic files or session history when useful	Hybrid lexical/ANN recall plus neighbouring document spans
Learning loop	Promote experience into skills	Episode → reviewed playbook promotion, with provenance
Inspectability	Plain files and memory UI	Source refs, versions, supersession, event and retrieval traces
The point is not that SQLite and FAISS are “more advanced” than Markdown. Plain files are excellent when one user should inspect and edit a compact set of project instructions. A gateway serving many users, documents, agents, and remote collaborators needs typed ownership, concurrent retrieval, versioning, and auditable writes. The architecture changes because the trust boundary changes.

There are two stores, not one winner:

SQLite is the source of truth: records, scopes, sources, states, versions, and transactions.
FAISS is a rebuildable index: vector IDs and Nomic embeddings that make candidate search fast.
If FAISS disappears, rebuild it from current authorized records. If SQLite disappears, the system has lost its memory.

8. Documents are memory only after they are made retrievable
Now run the prompt that exposed the old memory system most clearly:

Index the file papers/attention.md and tell me what the three key
contributions of the Transformer architecture are according to this paper.
The saved file is an arXiv abstract page, not a clean paper. It contains navigation and page furniture around the title and abstract. The indexing pipeline therefore has five steps, and chunking is only one of them.

extract useful document → choose semantic boundaries → write one document version
→ embed chunks with Nomic → make that version visible
The actual file had 898 words. Extraction kept the 213-word title and abstract region and recorded that 685 wrapper words were excluded. Phi-4 then produced four chunks of 46, 102, 40, and 25 words. Each chunk kept exact character and word spans into the prepared source.

The graph was:

index_file → scoped recall → paper_distiller (Gemini 1) → answer (Gemini 2)
The answer identified the attention-only architecture, its parallelizability compared with recurrence, and its training efficiency and performance. Re-indexing the unchanged file returned idempotent=true; it did not create four more records.

This is the rule:

Extraction decides what is content. Chunking decides which content belongs together. Embedding makes the resulting pieces searchable.

Confusing those three jobs is why many RAG systems are impossible to debug.

9. Rohan's semantic chunking V2, slowly
The method first appeared in EAG V1 Session 8. It does not compare every adjacent sentence with embeddings, and it does not ask an LLM to rewrite the document into summaries. It asks one narrow question over a moderately large block:

“Does a clearly different second topic begin inside this block? If yes, return the exact second part. If no, return nothing.”

That gives us a very simple algorithm.

Step 1: take a block
Take up to 512 words from the original Markdown, preserving its exact bytes. Do not cut through an open code fence, a Markdown table, or a heading that can begin the next block cleanly.

[ up to 512 original words ........................................ ]
Five hundred and twelve is a budget, not a desired chunk size. The model may find a boundary at word 170. It may find none, in which case the full block is one chunk.

Step 2: ask the local model for only the suffix
glc_v3 uses the Phi-4 model already running in Ollama. Temperature is zero. The important part of the prompt is not “split this text”. It is “copy the exact second topic starting at its first sentence or heading, and say nothing if there is only one broad topic.”

second = phi4.second_topic(block)
Suppose the model returns the final 167 words. The code checks that those 167 words are a verbatim suffix of the block.

complete_suffix = bool(second) and block.rstrip().endswith(second.rstrip())
split_at = block.rstrip().rfind(second.rstrip()) if complete_suffix else -1
This is the no-hallucination fence. If the model paraphrases, adds a label, drops punctuation, or returns text from the middle, the boundary is rejected and the block remains intact. rfind, rather than find, handles a phrase that appeared earlier in the same block.

Step 3: finalize the first topic
Everything before the returned suffix becomes a chunk.

[ first topic: finalized ][ second topic: not finalized yet ]
No overlap is added. No sentence is regenerated. The chunk is a span of source text.

Step 4: roll the suffix forward
The returned second topic becomes the beginning of the next block, followed by unread source text until the 512-word budget is reached.

next block = [ rolled-over second topic ][ new source words ... ]
Then ask the same question again. This continues until the document ends.

Step 5: embed only after the boundaries exist
Nomic receives the final chunks, using the correct retrieval prefixes for documents and queries. It does not choose the boundaries. This order matters because vector similarity answers “which meanings are near one another?” while chunking asks “where did the author stop discussing one retrievable subject and begin another?” Those questions are related and not identical.

The complete loop is:

while unread_text:
    block = take_up_to_512_words_without_breaking_markdown(unread_text)
    suffix = phi4.return_exact_second_topic_or_nothing(block)

    if suffix_is_verbatim_end_of(block):
        save(block_before_suffix)
        unread_text = source_starting_at(suffix)
    else:
        save(block)
        unread_text = source_after(block)

embed(saved_chunks_with_nomic)
Why the semantic floor exists
Blocks below 40 words are kept without another model call. At that size the cost of asking for a broad-topic judgment is larger than the likely retrieval gain, and short conclusions or final notes are valid chunks. The manifest records below_semantic_floor so a caller can distinguish that deliberate choice from “Phi-4 saw one topic”.

What the manifest proves
Every chunk records:

ordinal and previous/next ordinal,
heading if present,
exact prepared-source character and word spans,
block word count,
segmenter mode and model,
decision: suffix_rollover, one_topic, below_semantic_floor, or a named safe fallback,
hashes of the original and prepared document.
This lets one test reconstruct the indexed document from its non-overlapping spans and prove that no source text vanished or appeared twice. Semantic quality still needs retrieval evaluation; source integrity does not need an LLM judge.


Move the returned suffix boundary. The first topic finalizes and the suffix rolls into the next block. Try the Paraphrased suffix preset: the integrity check rejects it rather than silently losing text. One topic and Below floor show the other two manifest decisions.

10. A document version appears all at once
Indexing can fail halfway through: Ollama may be unavailable, an embedding call may fail, or the process may die after writing chunk three of ten. Retrieval must never see half of a new version.

glc_v3 therefore stages one document version inside a transaction.

begin transaction
  identify source URI + content hash
  extract and chunk
  write every chunk and source span
  write embeddings/index mapping
  mark previous version superseded
  mark new version current
commit
If any step fails, the transaction rolls back and the previous complete version remains current. An unchanged source hash returns the existing version. A changed source creates a new version and supersedes the old one without deleting its history.

Neighbour expansion is version-aware. If semantic search hits chunk 6, the memory service may add chunks 5 and 7 for context, but only from the same current document version and only after the same scope check. Adjacency is not permission to cross into an older or foreign document.

In the corpus run the agent first listed a directory, discovered five papers, and only then patched in five index nodes. It persisted 19 chunks: Attention 4, Chain-of-Thought 2, DPO 4, LoRA 4, and ReAct 5. Cross-document questions then used the same source-aware retrieval path rather than a special demo index.


Index a document and watch the transaction stage a whole version before it commits. Inject a failure at any step: the transaction rolls back and retrieval keeps the previous complete version. Re-index an unchanged source to see idempotent=true, and watch neighbour expansion stay inside the current version.

11. Why A2A exists
MCP answers a question we met in Session 9: which tools can this agent call? A2A answers a different question: how does this agent give a stateful task to another autonomous agent?

A tool call is usually one request and one response inside the caller's control plane. A remote agent may plan internally, ask for clarification, stream progress, produce several artifacts, wait for a human, and finish after the caller has restarted. Treating that as a giant tool function loses the state that makes it an agent collaboration.

The Agent2Agent protocol began at Google and moved under Linux Foundation governance in June 2025. By April 2026 the foundation reported support from more than 150 organizations and integrations across the major cloud platforms. More important for our code, the released protocol is now A2A 1.0, not the older 0.2/0.3 draft that many tutorials still show. The official Python SDK supports JSON-RPC, HTTP+JSON/REST, and gRPC bindings. See the A2A 1.0 specification, official Python SDK, and Linux Foundation adoption update.

The durable A2A nouns are:

Noun	Plain meaning
Agent Card	A discoverable JSON advertisement of identity, interfaces, skills, media types, and authentication requirements.
Message	One user or agent turn, made of typed parts such as text or data.
Task	The durable unit of remote work, with an ID and lifecycle.
Artifact	A result produced by the task: text, structured data, or a file-like part.
Context ID	The remote conversation or collaboration context to which tasks belong.
12. The Agent Card is like a menu
An A2A client first fetches:

GET https://agent.example.com/.well-known/agent-card.json
A compact 1.0 card looks like this:

{
  "name": "Research Agent",
  "description": "Finds and synthesizes public technical evidence",
  "version": "3.0.0",
  "supportedInterfaces": [
    {
      "url": "https://agent.example.com/a2a",
      "protocolBinding": "JSONRPC",
      "protocolVersion": "1.0"
    },
    {
      "url": "dns:///agent.example.com:443",
      "protocolBinding": "GRPC",
      "protocolVersion": "1.0"
    }
  ],
  "capabilities": {
    "streaming": true,
    "pushNotifications": true
  },
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["text/plain", "application/json"],
  "skills": [
    {
      "id": "technical-research",
      "name": "Technical research",
      "description": "Collects evidence and returns a sourced synthesis",
      "tags": ["research", "citations"]
    }
  ],
  "securitySchemes": {
    "bearer": { "httpAuthSecurityScheme": { "scheme": "Bearer" } }
  },
  "securityRequirements": [{"schemes": {"bearer": {}}}]
}
The client validates the card with the official generated type, then negotiates a mutually supported binding and protocol version. The first supported interface is the server's preference; the client still has to support it.

The card makes three claims: where the agent speaks, what it says it can do, and how a caller authenticates. It grants nothing inside the caller's machine.

An Agent Card is a menu. Authentication proves who is ordering. Authorization decides what ingredients may leave the kitchen.

Version 1.0 allows Agent Cards to carry JWS signatures. A verified signature proves that the signed card bytes came from the holder of the signing key and were not altered. It does not prove that the advertised skill is competent, safe, or entitled to local memory. Trust still needs issuer policy, key rotation, revocation, allowlisting, and task-level authorization. The protocol's canonical model includes the signature and security fields; glc_v3 validates the official schema and keeps its own trust policy at the gateway boundary.


Click the three regions of the card: where the agent speaks, what it says it can do, and how a caller authenticates. Flip the signature between valid, tampered, and unsigned. Even a verified signature grants no local-memory authority, and the callout keeps that boundary in view.

13. Three interaction modes, one task lifecycle
The “three modes” are not three different kinds of agent. They are three ways a client learns that the same durable task changed.

Synchronous
The client sends a message and the server returns the current task or response in the same request. Use it when work is fast enough for one network round trip.

client ── SendMessage ──> remote agent
client <── completed task + artifact ── remote agent
Streaming with SSE
For HTTP bindings, the server keeps a Server-Sent Events stream open and emits task status and artifact updates. Use it when work takes seconds or minutes and the user benefits from progress.

client ── SendStreamingMessage ──> remote agent
client <── working ── artifact delta ── completed
SSE is one-way server-to-client streaming over ordinary HTTP. New client messages are still new HTTP requests.

Asynchronous push
The client registers a webhook configuration and releases the connection. The remote server calls the webhook when state changes. Use it when either side may sleep, restart, or wait a long time.

client ── message + push config ──> remote agent
client <── accepted / task id

... minutes or hours ...

client webhook <── signed task update ── remote agent
The receiver must authenticate the sender, verify the signature, suppress duplicates with an idempotency key, and return quickly. Delivery is at-least-once in practical distributed systems, so “I received this webhook” can happen more than once. glc_v3 uses receiver bearer credentials, HMAC-SHA256 signatures, stable idempotency keys, exponential retry, and a durable duplicate-suppression ledger.

gRPC is a binding, not a fourth lifecycle
A2A 1.0 defines the same abstract operations over gRPC. The canonical lf.a2a.v1.A2AService includes send, streaming send, task get, cancel, subscribe, push-configuration operations, and extended card retrieval. gRPC gives generated protobuf types, HTTP/2 multiplexing, and native streaming; it does not change what a task or artifact means.

glc_v3 uses the official generated service and a2a-sdk==1.1.0. It did not invent Python dictionaries that merely resemble A2A.

14. A remote agent joins the live graph
This prompt was run against the gateway:

Slow remote report: explain in two lines why an agent card is not permission
to access local memory.
The local planner added a remote_specialist node and put it in waiting. That released the local worker. The A2A client negotiated the remote card and sent the task over the official gRPC service. The remote task persisted independently.

local graph                         remote A2A server
-----------                         -----------------
remote_specialist: waiting  ──────> SendMessage
                                    task: working
                                    artifact produced
SubscribeToTask             <────── task: completed
external event arrives
GraphPatch(resume=[remote_specialist])
remote_specialist: running → succeeded
graph: finished
The returned artifact was:

An Agent Card advertises capabilities and transports; it grants no local-memory authority.
The coordinator must send only explicitly authorized task context and validate the returned artifact.
That proof connects all four parts of this session.

The graph did not block a worker while the remote system worked.
The external outcome resumed one exact durable node.
The local memory service did not become remotely searchable.
The artifact returned as untrusted evidence, not as a command.
The A2A bridge may send only the context explicitly assembled for that task after local scope checks. It may never hand the remote agent a memory-store handle, database credential, broad retrieval endpoint, or “search everything and decide what you need” capability. The result is validated against expected media and size, stored with remote provenance, and then given to the local planner.


Step the remote task through discovery, negotiation, waiting, completion, and resume, and watch the local worker release the moment the node parks in waiting. Switch between synchronous, streaming, and async-push delivery. Tick Send a local memory handle to see the exact trust-boundary violation before the request is sent.

15. Federated agents across organizations
The interesting A2A case is not two agents in one repository. It is a purchasing agent inside one organization asking a supplier agent in another organization for a quote, while a compliance agent in a third organization validates a certificate.

Audit organization

Supplier organization

Buyer organization

A2A task: approved fields only

A2A task: certificate hash

signed quote artifact

validation artifact

User

glc_v3 coordinator

Scoped local memory

Quote agent

Certificate agent

Federation adds boundaries that a local multi-agent framework can ignore and A2A cannot solve for you.

Identity: which workload and organization is calling? Use TLS plus short-lived workload or OAuth identity; a bearer token copied into three agents is not federation.
Authorization: which skill, tenant, task, fields, and retention period are allowed? Bind permission to the final task parameters.
Data minimization: send the smallest authorized task context, not the local conversation and certainly not the memory index.
Residency and retention: the receiving organization may store the task. Decide that before sending personal or regulated data.
Artifact trust: a signed response proves origin and integrity, not truth. Validate schema, scan files, and preserve provenance.
Observability: carry trace IDs across the boundary without leaking prompts into telemetry.
Cancellation: local cancellation requests remote cancellation; it cannot pretend work already performed or data already received never happened.
A2A standardizes the envelope and lifecycle. Contracts, identity, authorization, and evidence quality remain system design.


Three organizations, no shared authority. Click each of the seven federation concerns to see which arrows and boxes it governs. Data minimization marks the scoped local memory as never crossing a boundary; artifact trust highlights the two signed results returning to the coordinator.

16. Honest failures are part of the architecture
Two benchmark prompts are more valuable than another success screenshot.

The Tokyo prompt asked for family activities, Saturday's weather, and the most appropriate choice. The activity and weather researchers ran together on Gemini 2 and Gemini 1, followed by a Gemini 3 distiller and Gemini 4 answer worker. The search snippets linked to forecast sites but did not contain Saturday's actual weather values. The final answer gave three indoor-capable activities and said it could not make a definite weather-based choice. It offered only the conditional advice that an indoor activity is safer if the weather is poor.

That is a success. The system preserved the difference between “a page probably contains the answer” and “the evidence I received contains the answer.”

The second prompt tried to read /nonexistent/path.txt. The sandbox path guard raised PermissionError. The failure became a graph event and the answer reported it. The planner did not widen the filesystem scope, invent file content, or hide the failed node.

For every run, proof means all four of these are inspectable:

the exact prompt,
the graph and every agent/provider assignment,
the ordered event and patch trace,
the final answer with evidence and honest limitations.
“The prompt worked” is not proof. A correct answer produced by an unjustified graph, leaked memory, or invented evidence is still a failed agent system.

17. Run glc_v3 locally
Ollama must already be running. The semantic segmenter expects Phi-4 and the memory index expects Nomic. Check the installed model names on your machine and set the two variables only if your tags differ.

cd glc_v3
uv sync

ollama list
export S13_CHUNK_MODEL=phi4:latest
export S13_LIVE_SEMANTIC_CHUNKING=1

uv run glc serve
The gateway loads .env through python-dotenv. Never print the file, paste it into a prompt, or include it in proof output. Multiple Gemini variables become separate provider slots automatically.

Health and capabilities:

curl http://127.0.0.1:8111/healthz
curl http://127.0.0.1:8111/.well-known/agent-card.json
Run an agent prompt with an explicit scope:

curl -s http://127.0.0.1:8111/v1/agent/runs \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "When is mom's birthday?",
    "tenant_id": "course",
    "project_id": "s13",
    "user_id": "student-01",
    "agent_id": "assistant"
  }'
The response includes a run ID. Inspect its graph and events:

curl -s http://127.0.0.1:8111/v1/agent/runs/<run-id>
Index a document through the same gateway:

curl -s http://127.0.0.1:8111/v1/agent/documents \
  -H 'Content-Type: application/json' \
  -d '{
    "text": "# Topic one\n...\n# Topic two\n...",
    "source_uri": "file:///course/example.md",
    "source_author": "student-01",
    "tenant_id": "course",
    "project_id": "s13",
    "user_id": "student-01",
    "agent_id": "assistant"
  }'
Use the API for the session exercises. Calling internal store methods from a notebook bypasses the gateway identity and proves less than it appears to prove.

18. The proof suite
Before changing the code, establish the floor:

cd glc_v3
uv run pytest -q
The reference build passed 289 tests. The number will grow as student fixes arrive; the contract matters more than freezing the count. Tests cover the old gateway behavior as well as the new layers, so Session 13 does not earn its features by quietly breaking Sessions 9–12.

The non-browser benchmark reuses prompts from the older sessions because a new harness must first show that it can do the old work at least as well. Its cases include:

Prompt family	What it proves
Fetch Claude Shannon and extract dates/contributions	Outcome-driven fetch → distill → answer with URL evidence
Search asyncio, then read top three	URLs discovered before fetch nodes exist; bounded parallel fetch
Tokyo activities plus weather	Parallel specialists and evidence-bounded refusal
Remember birthday, create reminders, ask later	Typed fact write, artifacts, cross-run recall, original provenance
Index Attention paper	Extraction, Phi-4 semantic boundaries, Nomic retrieval, grounded synthesis
Index five-paper corpus	Runtime discovery, atomic idempotent indexing, cross-document recall
Compare CoT and ReAct	Multi-document synthesis without losing paper identity
Ask about absent credit assignment	Semantic retrieval without pretending semantic proximity is textual support
Research three populations	Three simultaneous agents and five Gemini slots
Compare Mumbai/Cairo/Lagos growth	Structured validator catches incomparable definitions and missing data
Read a forbidden/missing path	Safe graph failure without hallucination
Slow remote report	Official A2A task parks, completes, resumes, and returns a bounded artifact
Run the reproducible local benchmark only against sources you are permitted to access and avoid the browser/computer-use cases for this session:

uv run python ../S13/proofs/run_benchmark.py
uv run python ../S13/proofs/run_a2a_proof.py
Your report must retain raw machine-readable traces, but the student-facing submission is one concise proof table and selected event replays, not a claim that everything passed.

19. The assignment
First the code:

glc_v3
S13Code
S13Proof
Github Links:

glc_v3 << nothing to be done, just reference
S13Code << you need to open PR
Build one meaningful extension to glc_v3 and prove it through a use case. The extension may improve the live planner, memory, semantic indexing, or A2A federation. A submission without an end-to-end run does not score, even if its unit tests pass.

Part 1: reproduce the floor
Run the test suite and the non-browser benchmark. Pick four cases: one live expansion, one durable-memory round trip, one semantic document query, and the A2A waiting/resume case. For each, retain the prompt, graph, ordered event trace, provider/agent assignments, evidence, and final answer.

Then explain one honest limitation the trace exposed. “No limitation” means the trace was not read carefully.

Part 2: extend one boundary
Choose one track.

Live graph track. Add an outcome-driven behavior that the current planner cannot express well: speculative work with deterministic cancellation, a human-approval wait, a quorum, a retry policy that distinguishes transient from permanent failure, or a budget-aware branch. Prove that future nodes do not exist before their inputs and that cancelled work does not leak a late result into the graph.

Memory track. Add a reviewed promotion path, expiry/forgetting workflow, contradiction handling, retrieval evaluation, or a new scoped backend. Prove a write, an authorized recall, a denied cross-scope recall, a correction with preserved history, and provenance in the final answer.

Semantic indexing track. Improve extraction for a real document type, add a retrieval benchmark, or strengthen boundary handling without changing Rohan V2's suffix-rollover invariant. Prove exact source coverage, no overlap, idempotent re-indexing, rollback on injected failure, and better retrieval on at least ten labeled queries against a fixed-word baseline.

A2A track. Connect a second framework or language through A2A 1.0, add verified signed-card trust policy, or implement a durable push receiver. Prove discovery, version/binding negotiation, authentication failure, task progress, completion artifact, cancellation, duplicate push suppression, process restart, and that the remote agent cannot retrieve local memory outside the explicit task context.

Part 3: attack your own claim
Write one adversarial test against the exact feature you added. Try a duplicate event, stale document version, wrong tenant, malformed model patch, paraphrased semantic suffix, tampered card, replayed webhook, or result arriving after cancellation. Show the failure before the fix and the same attack failing afterward.

What you submit
Submit one pull request and one README section inside it. Do not create a folder of explanatory reference documents.

The README section contains:

the user-visible capability in one paragraph,
the exact prompt or API request,
the graph and ordered event trace,
the actual final result,
the evidence and provider/agent assignments,
the adversarial failure and fix,
the commands that reproduce everything from a fresh checkout.
Secrets, .env, raw credentials, personal memory, and unrestricted local paths never enter the pull request. Synthetic test identities are mandatory.