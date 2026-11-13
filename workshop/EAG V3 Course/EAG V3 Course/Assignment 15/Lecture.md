Session 15: Model Routing, Agent Economics & Observability

1. What This Session Is

Core Idea

This session adds an economic control layer to the agent.

Earlier sessions gave the agent:

An execution graph
Memory
A user interface
This session answers:

Which model should be called, what will it cost, and should the call be allowed?
The Three Concepts

1. Routing

Routing decides:

request -> which model/provider should handle it?
Example:

simple summarisation -> cheap model
difficult reasoning  -> frontier model
2. Metering

Metering records what happened:

model used
input tokens
output tokens
latency
cost
It is similar to an electricity meter. It does not stop consumption. It records it.

3. Budgeting

Budgeting decides whether the call is permitted.

projected call cost <= remaining budget -> allow
projected call cost > remaining budget  -> refuse or downgrade
The important point is that this decision happens before the provider call.

What “Economically Self-Aware” Means

The model itself is not calculating money.

The surrounding agent system knows:

How much money remains
What capability each node needs
Which models are affordable
When execution must stop
So the system is economically aware, not necessarily the LLM.

The Three Services

glc_v4

The gateway.

All model requests pass through it. It handles:

Provider selection
Model routing
Pricing
Budget checks
Metering
Caching
Failover
Think of it as an API gateway specifically for LLM calls.

S15Code

The agent runtime.

It runs the agent graph:

planner -> node -> tool/model call -> result -> next node
When it needs an LLM, it calls glc_v4.

Jaeger

Jaeger is a trace viewer and trace storage system.

It shows one agent run as a hierarchy:

agent run
  -> planner
  -> answer node
      -> model call
For each part, it can show:

Time taken
Model used
Tokens consumed
Cost
Errors
Jaeger does not execute the agent. It helps inspect what happened inside a run. These three services and their ports are introduced directly in the session.

Architecture

User request
    |
    v
S15Code agent runtime
    |
    v
glc_v4 gateway
    |
    v
Model provider

S15Code + glc_v4
    |
    v
Jaeger traces
What Students Must Understand

The agent requests capability. The gateway decides what is affordable, records the cost, and exposes the decision through traces.
That is the foundation for every later section.


Three strategies over the same twelve tasks. Switch the metric from cost per call to cost per resolved task — the move that normally reverses the ranking — and watch the ranking hold. Then open the break-even explorer and drag the price spread: the trap this session was written to demonstrate needs a spread near 1.3×, and the ladder we measured is 9.2× wide.
Section 2: The Gateway Can Bill You for No Visible Answer

What Happened

The gateway sent this request:

{
  "messages": [
    {
      "role": "user",
      "content": "In exactly two sentences, explain why a budget must be enforced in code."
    }
  ],
  "max_tokens": 512,
  "temperature": 0,
  "provider": "cerebras"
}
The provider returned:

out_tokens = 512
stop_reason = max_tokens
text = ""
cost = $0.00027350
So:

The model generated 512 tokens
The provider charged for them
The visible answer was empty
The call still returned successfully
Where Did the Tokens Go?

Some models generate two kinds of output:

hidden reasoning
visible answer
The model spent the entire 512-token allowance on its hidden reasoning.

It reached the token ceiling before writing anything into the visible answer field.

512-token ceiling
|-----------------------------|
| hidden reasoning            |
| no space left for answer    |
What Is stop_reason = max_tokens?

It means:

The model stopped because it consumed the maximum output-token allowance.
It does not mean the task was completed.

Compare:

stop_reason = end_turn
This normally means the model decided it had finished its response.

Why Was the Visible Text Empty?

The provider response had separate channels.

Conceptually:

{
  "reasoning": "...hidden generated tokens...",
  "content": ""
}
The gateway parser only read:

msg["content"]
It ignored the reasoning field.

Therefore:

generated tokens = 512
visible content = 0 characters
bill = real
The gateway did not invent the charge. It simply failed to notice that all paid output was invisible.

Why Did Turning Reasoning Off Fix It?

With reasoning disabled, the model wrote directly into the answer channel:

out_tokens = 86
stop_reason = end_turn
text = 505 characters
cost = $0.00006050
The same model and prompt became 4.52× cheaper and produced an actual answer.

What Was the Gateway Bug?

The caller requested:

reasoning = "off"
But _apply_reasoning() returned early.

That meant the gateway sent no reasoning-control field to the provider.

So "off" effectively became:

use provider default
The provider default was to reason.

What Is a Provider Dialect?

Different providers express the same instruction using different fields.

One may expect:

{
  "reasoning_effort": "none"
}
Another may expect:

{
  "chat_template_kwargs": {
    "thinking": false
  }
}
These are two different API dialects for the same intent:

Do not spend tokens on internal reasoning.
The gateway should translate one common caller instruction into whichever format the provider understands.

What Does “Healing the Request” Mean?

The gateway initially sends both possible fields.

The provider may reject one:

chat_template_kwargs is unsupported
The gateway removes that field and retries.

The provider may then reject another value:

reasoning_effort must be low, medium, or high
The gateway adjusts again and retries.

send request
   |
   v
provider rejects field A
   |
remove field A
   |
   v
provider rejects value B
   |
replace value B
   |
   v
request succeeds
A single retry is insufficient because the provider may reveal only one incompatibility at a time.

Core Takeaway

1. Cost belongs to a call

The same model can cost differently depending on:

Reasoning mode
Output ceiling
Prompt structure
Cache state
Actual output length
2. HTTP 200 does not mean useful work happened

The request succeeded technically, but failed economically and functionally.

3. Meter both cost and usefulness

The system must compare:

tokens charged
visible output
stop reason
task result
Otherwise, a fully billed empty answer looks like a successful call.

4. Provider-specific syntax belongs inside the gateway

The agent should say:

reasoning = off
The gateway should determine how Cerebras, Groq, Gemini, or another provider represents that instruction.


The same model, the same prompt, the dial unset and then set. Watch the token-budget bar: the shaded region is reasoning you paid for and never saw, and in the first pane it consumes the entire ceiling. The code panels show the early return that caused it and the healing loop that fixes it.
Section 3: Why Cheaper Tokens Can Still Produce a Bigger Bill

The Apparent Contradiction

Two things happened together:

Token prices dropped sharply
Total AI spending increased
That is possible because usage grew faster than prices fell.

The Core Equation

total cost
=
number of calls
× tokens per call
× price per token
Reducing only the last term does not guarantee a lower bill.

Example:

old system:
1 call × 100 tokens × ₹1
= ₹100

agent system:
10 calls × 100 tokens × ₹0.10
= ₹100
The token became 90% cheaper, but the system made 10× more calls. Nothing was saved.

Why an Agent Is a Call Multiplier

A normal chatbot may make one model call:

user request -> answer
An agent may do:

user request
  -> plan
  -> choose tool
  -> execute tool
  -> inspect result
  -> verify
  -> rewrite
  -> final answer
One user request can therefore create several model calls.

It may also repeatedly send:

The conversation history
Tool definitions
Retrieved documents
Previous intermediate results
Repository or workspace context
This is why one coding-agent request can carry very large input context.

The Wrong Metric: Cost per Token

Suppose Model A costs less per token.

That does not tell us:

How many calls it needs
How verbose it is
How often it fails
Whether it triggers retries
Whether another model must correct it
Whether a human must intervene
So cost per token describes the raw material, not the completed work.

A Better Metric: Cost per Call

cost per call
=
total model spend / number of calls
This is better, but still incomplete.

A cheap call that fails is not useful merely because it was cheap.

The Correct Metric: Cost per Resolved Task

cost per resolved task
=
total spend / number of successfully completed tasks
Example:

MODEL	CALLS	SPEND	TASKS RESOLVED	COST/RESOLVED TASK
Expensive	10	$10	10	$1.00
Cheap	20	$6	4	$1.50
The cheap model has a lower cost per call:

$6 / 20 = $0.30
But a higher cost per resolved task:

$6 / 4 = $1.50
The expensive model is economically better because it completes more work.

What Does “Resolved” Mean?

A task is resolved when the answer satisfies its actual success condition.

Examples:

Code passes the tests
Correct file is generated
Customer issue is fixed
Required information is returned
Agent reaches the intended final state
A response being fluent or long does not mean the task was resolved.

What Is FinOps?

FinOps means operational control and accountability for technology spending.

Originally, it focused mostly on cloud infrastructure:

Compute
Storage
Databases
Network usage
For agents, it extends to:

Cost by user
Cost by agent
Cost by session
Cost by task type
Cost per resolved task
Waste from retries and failed calls
The session's point is that AI spend must be attributed to the actual unit of work, not only to providers or token totals.

Core Takeaway

Token prices measure the cost of generation. Cost per resolved task measures the economics of the system.
The first can improve while the second becomes worse.


Two lines moving in opposite directions, and the Pareto map of the July 2026 landscape underneath them. Roughly 96% of priced models are dominated — cheaper and better options exist — leaving about thirteen on the frontier, and the frontier now turns over quarterly.
Section 4: Read the Gateway You Already Have

Core Point

Before adding budget control and tracing, inspect what the existing gateway already does.

glc_v3 is not a simple proxy. It already contains routing, failover, rate control, metering, caching, and provider pooling.

1. Task-Complexity Classification

A small router model reads the request and classifies it as:

TINY
LARGE
HUGE
That classification maps to an ordered list of providers or models:

TINY  -> cheap models first
LARGE -> stronger models first
HUGE  -> frontier-capable models
TIER_TO_ORDER is simply the configuration mapping from complexity tier to candidate order.

The router model does not execute the task. It only classifies the task.

2. Provider Ring

A provider ring is the ordered list the router tries.

Example:

LARGE:
1. Gemini
2. Groq
3. GitHub Models
4. Ollama
The gateway walks the ring until it finds a provider that can serve the call.

It may skip a provider because:

The model lacks the required capability
The prompt exceeds its context limit
The provider is currently unavailable
Its rate quota is exhausted
3. Failover

Failover means automatically trying another provider when the preferred provider cannot serve the request.

Gemini unavailable
        |
        v
try Groq
        |
        v
try GitHub
This prevents one provider failure from stopping the whole agent.

4. RateState

RateState tracks provider usage limits such as:

Requests per minute
Requests per day
Tokens per minute
Minimum time between calls
Example:

Groq limit = 30 requests/minute
current usage = 30
The router temporarily skips Groq instead of sending a request that is likely to fail.

5. Circuit Breaker

A circuit breaker temporarily removes a failing provider from consideration.

provider times out
    |
    v
mark unavailable for 60 seconds
    |
    v
do not keep retrying it
Without a circuit breaker, every new request would repeatedly hit the same broken provider.

The cooldown may depend on the error:

rate limit       -> short cooldown
timeout          -> longer cooldown
authentication   -> very long cooldown
6. Metering

The gateway already records every provider call in SQLite:

provider
model
input tokens
output tokens
cache usage
latency
status
retry count
agent
session
This answers questions such as:

How much did agent X spend today?
Which provider generated the most tokens?
How many calls failed?
It does not yet explain the full hierarchy of one agent run. That requires tracing, introduced later.

7. Prompt Caching

The gateway already tries to reduce repeated input cost.

For Gemini, it explicitly creates a cached resource identified by a SHA hash.

For OpenAI-compatible providers, it keeps the static prompt prefix byte-identical so provider-side caching can activate.

same system prompt bytes
same tool definitions
same document prefix
        |
        v
provider can reuse cached tokens
8. Provider Pooling

One logical provider may represent several API keys.

gemini
  -> gemini_1
  -> gemini_2
  -> gemini_3
  -> gemini_4
  -> gemini_5
Each instance has separate:

Quotas
Rate state
Metering
Availability
The gateway can rotate between them when one key reaches its limit.

What glc_v4 Actually Adds

Only four major capabilities were missing:

ADDITION	MEANING
Spend budget	Stop or downgrade calls based on money
Tracing	Explain one complete run through spans
Per-model pricing and user identity	Attribute exact costs by model, user, tenant, or project
Role-aware routing	Let roles such as planner or summariser affect model choice
Everything else already existed.

Bug 1: Gemini Was Never Auto-Routed

The configuration referred to:

gemini
But the registered providers were:

gemini_1
gemini_2
...
gemini_5
The code checked literal membership:

"gemini" in providers
That returned false.

So Gemini appeared first in the routing configuration but was silently skipped.

The fix was to expand a base name:

gemini -> all live gemini_N instances
Bug 2: The Circuit Breaker Did Not Cool Down

The code tried to identify errors using:

str(error)
But:

str(httpx.ReadTimeout())
can be an empty string.

The gateway therefore failed to recognise the timeout and applied a zero-second cooldown.

provider times out for 180 seconds
        |
        v
immediately becomes eligible again
The fix was to inspect both:

exception class name + exception message
For example:

ReadTimeout:
The class name remains useful even when the message is empty. These two bugs and their causes are described in the session directly.

Core Takeaway

A successful API envelope does not prove that routing behaved correctly. Inspect the provider selected, ledger record, retries, and availability state.
Section 5: A Rung Is a Model

Core Idea

A ladder is an ordered set of models with different prices and capabilities.

economy
standard
frontier
Each position is called a rung.

The important rule is:

Each rung should represent a different model, not merely a different token limit.
Why Route by Role?

Different agent nodes perform different jobs.

summariser
planner
coder
reviewer
final-answer writer
They do not all require the same model.

A configuration may say:

summariser -> economy
planner    -> standard
reviewer   -> frontier
So the system chooses a model for the role, rather than choosing one model for the whole agent.

The Ladder Used Here

RUNG	MODEL	MEANING
Economy	openai/gpt-oss-120b	Lowest-cost option
Standard	gemini-3.1-flash-lite	Middle option
Frontier	openai/gpt-4.1	Most expensive option
The rungs also use different providers:

economy  -> Groq
standard -> Gemini
frontier -> GitHub Models
This matters because a downgrade genuinely changes:

The model
The provider
The price
The latency
Possibly the capability
What Does “Requested Frontier” Mean?

An agent node may declare:

required tier = frontier
This means:

“This work would ideally use the frontier model.”
It does not mean the gateway must always provide it.

The budget controller checks what can actually be afforded.

frontier requested
       |
       v
frontier affordable? -> use frontier
       |
       no
       v
standard affordable? -> use standard
       |
       no
       v
economy affordable?  -> use economy
       |
       no
       v
refuse
Why Not Just Reduce max_tokens?

Suppose the frontier model is too expensive.

One possible downgrade is:

same expensive model
max_tokens: 2000 -> 200
This may produce:

A truncated answer
An incomplete answer
The same expensive input charge
No real change in reasoning capability
A proper downgrade is:

frontier model -> standard model
That gives the cheaper model enough room to produce a complete answer.

So:

Budget pressure should usually change the model, not merely shorten the answer.
Important Warning: The Ladder Is Not a Truth Ranking

The names imply:

frontier > standard > economy
But this is only the configured capability assumption.

It does not guarantee:

frontier is better on every task
Later sections show that the cheapest model sometimes answered correctly while the more expensive models failed.

The ladder orders models primarily by:

Intended capability
Price
Operational role
It must later be validated against real tasks.

The Price-List Problem

The listed token prices differed by 84.3× between the bottom and top rungs.

But the actual measured charges differed by only 4.55×.

Why?

Because models generated different amounts of output.

cheap model     -> 299 output tokens
frontier model  -> 87 output tokens
The cheap model had a lower price per token, but produced many more tokens.

Cost of a Call

A simplified calculation is:

call cost
=
input tokens × input price
+
output tokens × output price
So two models with very different list prices may produce bills that are much closer if the cheaper one is more verbose.

Example:

Model A:
cheap per token × 300 output tokens

Model B:
expensive per token × 80 output tokens
The final difference may be much smaller than the pricing page suggests.

List Price vs Measured Charge

List price tells you:

cost per million input/output tokens
Measured charge tells you:

what this model actually cost
for this prompt and this answer
The second includes model behaviour:

How much it reasoned
How verbose it was
Whether it stopped early
Whether it used the full token ceiling
Token price is a rate. The bill depends on how many tokens the model actually consumes.
Core Takeaway

A useful ladder requires three things:

Each rung maps to a genuinely different model.
Budget downgrades move to a cheaper rung.
The ladder must be evaluated using measured task cost and quality, not pricing pages alone.

The ladder with its measured prices and latencies, then the downgrade under budget pressure showing the served model changing. Switch to the second view for the result that complicates the whole picture.
Section 6: Two Caches That Solve Different Problems

Core Difference

Both reduce cost, but at different points.

Prompt cache   -> model call still happens
Semantic cache -> model call is skipped
1. Prompt Caching

Prompt caching reuses the unchanged beginning of a prompt.

Suppose every request contains:

system prompt
tool definitions
large reference document
current user question
Usually, only the final user question changes.

The provider can avoid fully reprocessing the repeated prefix and charge a reduced input-token price for that cached part.

The call still happens

request
  -> provider receives it
  -> cached prefix reused
  -> model generates a new answer
You save part of the input cost, but still pay for:

New input tokens
Output tokens
Model execution
Latency
What Does Byte-Exact Prefix Mean?

The beginning of the request must match exactly.

These are different:

Today is 31 July 2026.
You are a coding assistant.
Today is 1 August 2026.
You are a coding assistant.
Because the timestamp changed near the top, everything after it may lose the cache match.

Even small differences can matter:

Spaces
Tool order
JSON formatting
Timestamps
Changing IDs
Different system-prompt wording
So place stable content first:

system prompt
-> tools
-> reference documents
-> changing conversation content
What Is the SHA-Keyed Cache?

A SHA hash is a fingerprint of some content.

Conceptually:

hash(system prompt + tools + documents)
        |
        v
cache key
If the same content produces the same hash, the gateway can locate the corresponding cached Gemini resource.

The hash is used for identification. It is not the cached content itself.

2. Semantic Caching

A semantic cache stores an earlier answer and reuses it when a new request has the same meaning.

Example:

"What is the deepest ocean trench?"
Later:

"Which ocean trench is the deepest?"
The wording differs, but the meaning is nearly identical.

The semantic cache may return the previous answer immediately:

new request
  -> search cached requests
  -> sufficiently similar request found
  -> return stored answer
  -> no model call
This saves the entire call.

What Is an Embedding?

An embedding converts text into a list of numbers representing its approximate meaning.

"What is the deepest ocean trench?"
        |
        v
[0.12, -0.43, 0.81, ...]
A paraphrase should produce a nearby numerical representation.

What Is Cosine Similarity?

Cosine similarity measures how closely two embedding vectors point in the same direction.

Typical interpretation:

1.00 -> almost identical meaning
0.95 -> very similar
0.70 -> somewhat related
0.20 -> mostly unrelated
In the example, the two questions matched at:

0.978869
That was above the cache threshold, so the cached answer was returned.

Why Is the Namespace Necessary?

Similarity of the user question alone is insufficient.

The previous answer may have been generated with:

A different model
A different system prompt
Different tools
A different response format
A different temperature
Therefore, the cache first requires exact agreement on those settings.

same model
same system prompt
same tools
same response format
same temperature
        |
        v
then compare semantic similarity
Without this separation, a concise answer produced by one model could be returned where another caller expected structured JSON or tool usage.

The Dangerous Threshold

A lower similarity threshold creates more cache hits.

It also creates more incorrect matches.

high threshold -> fewer hits, safer
low threshold  -> more savings, more collision risk
For example, these prompts may be semantically close but require opposite answers:

"Can this medication be taken during pregnancy?"
"Can this medication be avoided during pregnancy?"
A false semantic-cache hit produces a stored answer with:

No provider error
No new reasoning
No indication that the wrong question was matched
That is why the configured threshold is 0.95, and why the semantic cache is opt-in.

Prompt Cache vs Semantic Cache

PROPERTY	PROMPT CACHE	SEMANTIC CACHE
What is reused?	Input prefix	Previous answer
Does the model run?	Yes	No
Is the answer newly generated?	Yes	No
Main saving	Discounted input	Entire call
Match type	Byte-exact prefix	Meaning similarity
Main risk	Cache miss	Wrong cached answer
Core Takeaway

Prompt caching makes repeated calls cheaper. Semantic caching avoids repeated calls entirely.
Semantic caching saves more, but it carries the greater correctness risk.

Why Are We Discussing Semantic Caching?

Because this session is about reducing cost per task. Routing selects a cheaper call; prompt caching discounts a call; semantic caching can eliminate the call entirely.

But it is not a model-provider feature in the same sense as prompt caching.

Prompt caching   -> usually implemented by Anthropic/OpenAI/Gemini
Semantic caching -> usually implemented in your gateway or application
In this session, glc_v4 implements its own semantic cache: it embeds the request, searches previous requests by cosine similarity, checks the namespace, and returns the stored answer without contacting a model.

Does Anyone Provide It?

Yes. Examples include:

Azure API Management, which provides semantic-cache lookup and storage policies for LLM APIs. (Microsoft Learn)
Portkey AI Gateway, which provides exact and semantic response caching. (Portkey)
Redis, which provides semantic-cache components using embeddings, thresholds, metadata filters, and TTLs. (Redis)
The underlying LLM provider generally does not decide this. The cache sits before the provider:

application
    |
    v
gateway semantic-cache lookup
    |
    +-- hit  -> return stored answer
    |
    +-- miss -> call Gemini/Groq/OpenAI/etc.
Who Decides to Use It?

Three separate decisions exist:

DECISION	WHO DECIDES?
Whether semantic caching exists	System architect
Similarity threshold and namespace rules	System architect
Whether a particular request may use it	Caller or application policy
Whether the current request is a hit	Gateway code
In this implementation:

default_on: false
So the caller must explicitly enable it per request. The LLM does not choose.

Conceptually:

{
  "semantic_cache": true
}
The gateway then checks:

same model?
same system prompt?
same tools?
same response format?
same temperature?
similarity >= threshold?
Only then does it return the cached answer.

Why Keep It Opt-In?

Because a false match means the system returns an old answer to a different question, with no model call and no model opportunity to correct it.

Use semantic caching for narrow, repetitive, stable workloads such as:

FAQ answers
Product documentation questions
Standard support queries
Repeated classification tasks
Avoid it by default for:

Current information
Personalised answers
Coding against changing repositories
Financial or medical decisions
Agent tasks whose state changes between calls
So the teaching point is not that every agent should use semantic caching. It is:

Semantic caching is the highest-saving cache and the highest-risk cache. The gateway must control it explicitly.

The same request through both mechanisms, so the difference in what is saved is visible. Drag the similarity threshold and watch the two curves refuse to separate: the true-positive rate collapses long before the false-positive rate on hard negatives does, and it never reaches zero.
Section 7: Every Call Becomes a Span

Core Problem

The SQLite ledger can answer:

How much did we spend today?
Which provider charged us?
How many tokens were used?
It cannot easily answer:

Why did this one agent run cost $0.004?
Which node made the expensive call?
Which call caused the delay?
For that, we need a trace.

What Is a Trace?

A trace is the complete execution path of one request.

Example:

agent run
  -> agent loop
      -> answer node
          -> Gemini model call
It shows the hierarchy of what happened.

A trace normally has one unique trace ID.

trace_id = abc123
That ID lets us retrieve the complete run later.

What Is a Span?

A span is one timed operation inside a trace.

In this example:

run
  agent_loop
    node
      provider_call
Each line is a span.

A span normally records:

Start time
End time
Duration
Operation name
Parent span
Status
Attributes
Errors
Example:

provider_call
model = gemini-3.1-flash-lite
input_tokens = 269
output_tokens = 77
cost = $0.00018275
duration = 1012 ms
So:

Trace = complete request. Span = one operation inside it.
Why Use Parent and Child Spans?

They show where the work belongs.

run
  -> planner node
      -> model call
  -> tool node
      -> database call
  -> answer node
      -> model call
Without this hierarchy, we only have a flat list of calls.

With the hierarchy, we can answer:

Which node called the model?
Did the planner or final answer cost more?
Which tool delayed the run?
Which retry caused the increase?
What Is OpenTelemetry?

OpenTelemetry, usually called OTel, is a standard way to generate and export:

Traces
Metrics
Logs
It is not a dashboard itself.

It defines how the application describes telemetry and sends it to a backend.

application
   |
   v
OpenTelemetry SDK
   |
   v
telemetry backend
This session uses standard GenAI attributes such as:

gen_ai.provider.name
gen_ai.request.model
gen_ai.usage.input_tokens
gen_ai.usage.output_tokens
It also uses operation names such as:

chat
invoke_agent
execute_tool
These conventions make traces from different systems easier to compare.

What Is Jaeger?

Jaeger is the system that receives, stores, searches, and displays traces.

Think of it as a browser for distributed execution.

S15Code + glc_v4
        |
        v
OpenTelemetry exporter
        |
        v
Jaeger
In Jaeger, you can search by:

Trace ID
Service name
Operation name
Time range
Error status
Then open a trace and inspect its waterfall.

Jaeger does not decide routing, cost, or budget. It only shows what happened.

What Is a Trace Waterfall?

A waterfall shows when each span started and how long it lasted.

run             |-----------------------|
agent_loop      |-----------------------|
node answer     |-----------------------|
provider_call   |----------------------|
This helps reveal:

Slow provider calls
Retries
Sequential work that could be parallel
Nodes waiting on other nodes
Unexpected extra calls
Why Do We Need Both a Ledger and a Trace?

They serve different purposes.

LEDGER	TRACE
Durable financial record	Execution explanation
Usually tabular	Hierarchical
Good for aggregation	Good for one-run debugging
“What did we spend?”	“Why did this run cost that?”
Cost by day, model, user	Cost by node and call path
The strongest proof is that both agree.

sum of provider-call span costs
=
sum of ledger costs
In this session, the difference was exactly zero.

That matters because:

The trace says where the money was spent.
The ledger says how much was billed.
Agreement means both records are trustworthy.
Why Fetch the Trace Back from Jaeger?

Creating spans inside the process is not enough.

A program could create spans and fail to export them.

Therefore, the proof does this:

create trace
-> export trace
-> retrieve trace from Jaeger using trace ID
-> verify spans and costs
This proves the telemetry reached the actual backend.

Why Keep Prompt Content Out?

A trace may be accessible to:

Developers
Operations teams
Monitoring systems
External telemetry vendors
Prompts may contain:

Names
Passwords
API keys
Medical details
Internal documents
Customer information
Therefore, the trace should record:

model
provider
token counts
latency
cost
status
But normally not:

full prompt
full response
The session verified that gen_ai.input.messages and gen_ai.output.messages were absent from exported spans.

What Is a Metric Label?

A metric might look like:

llm_requests_total{
  provider="gemini",
  model="flash-lite",
  status="success"
}
The values inside braces are labels or dimensions.

They let us group metrics:

requests by provider
cost by model
errors by status
Why Not Put User IDs or Prompts in Metric Labels?

Metrics create one time series for every unique label combination.

Suppose we use:

user_id="user_1"
user_id="user_2"
user_id="user_3"
...
With millions of users, the monitoring system creates millions of series.

This is called high cardinality.

Prompts are even worse because nearly every prompt is unique.

So never use these as metric labels:

Prompt
Response
Conversation ID
Unbounded user ID
This can overload the metrics backend.

What Is an Exemplar?

An exemplar links an aggregated metric point to one specific trace.

Example:

latency p99 suddenly increased
        |
        v
open example trace abc123
Metrics tell us that a problem exists.

The exemplar takes us to a trace that shows why.

Complete Flow

Agent starts run
    |
    v
create run span
    |
    v
create node span
    |
    v
gateway makes model call
    |
    v
create provider-call span
    |
    +--> record tokens, cost, latency
    |
    v
export spans using OpenTelemetry
    |
    v
Jaeger stores and displays trace
Core Takeaway

The ledger proves the amount spent. The trace explains where and why it was spent. Jaeger is where the trace is inspected.

The real waterfall, with every span's attributes on click and cost attached to each provider call. Toggle content capture to see what would be exposed if you enabled it, and why the default is off.
Section 8: A Ceiling Is Real Only If It Refuses

Core Idea

A budget is meaningful only when the system can stop a call before money is spent.

The gateway adds a hard budget controller that runs before the provider is contacted.

What Happens Before Every Call

The gateway calculates a worst-case estimate:

projected cost
=
estimated input cost
+
maximum possible output cost
It uses:

Estimated prompt tokens
Model input price
The rung’s max_tokens
Model output price
Remaining budget
Then it makes a deterministic decision:

projected cost <= remaining budget
        -> allow

projected cost > remaining budget
        -> downgrade or refuse
No LLM makes this financial decision.

Why Use max_tokens in the Projection?

The actual output length is unknown before the call.

Suppose:

max_tokens = 2048
The model may produce 100 tokens or all 2,048.

To guarantee the ceiling, the controller assumes the expensive case:

possible output = 2048 tokens
This is conservative, but safe.

An average-cost estimate could allow a call that later exceeds the remaining budget.

Example

budget ceiling = $0.00003
small call cost = $0.00000125
The small call is admitted.

For the next call:

projected cost = $0.0030725
remaining      = $0.00002875
The gateway returns:

HTTP 402
budget_exceeded
It also reports the shortfall:

shortfall =
projected cost - remaining budget
The provider is never contacted.

What Is HTTP 402?

HTTP 402 means:

Payment Required
It is rarely used on the public web, but here it is a useful status for:

The requested work cannot be admitted under the available budget.
Why the Budget Cannot Live in the Prompt

You could tell the model:

Do not spend more than $0.01.
But the model does not directly control:

Provider pricing
Actual token billing
Retries
Tool calls
Hidden reasoning
Other agent nodes
Remaining shared budget
It may also ignore, misunderstand, or lose the instruction during context compaction.

Therefore:

prompt budget = guidance
gateway budget = enforcement
The session’s rule is:

The model requests capability. Deterministic code decides what the budget permits.
What Happens Under Budget Pressure?

There are three possible outcomes.

1. Admit the Requested Rung

requested = frontier
frontier affordable
-> serve frontier
2. Downgrade

requested = frontier
frontier unaffordable
standard affordable
-> serve standard
The call still happens, but on a cheaper model.

3. Refuse

economy also unaffordable
-> no provider call
This is a genuine hard ceiling.

Who Is the Principal?

The principal is the identity whose budget is being enforced.

It may represent:

A session
A user
A tenant
A project
An agent
A combination of these
Example:

principal = session:rohan-verify
The budget controller asks:

How much has this principal spent?
How much is still available?
Important Limitation

The controller proves:

This call fits inside the financial ceiling.
It does not prove:

This model will solve the task.
A cheap admitted call may still fail. A refused expensive call may have succeeded.

Budget enforcement controls risk of overspend, not answer quality.

Core Takeaway

A budget is not a warning shown after spending. It is an admission check performed before the call exists.
Where does "Estimated prompt tokens" come from?

The section only says the controller uses a pessimistic estimate of the prompt actually being sent. It does not specify the exact counting algorithm.

Where It Comes From

Before calling the provider, the gateway already has the complete request:

system prompt
+ conversation messages
+ tool definitions
+ retrieved documents
+ response-format instructions
It serializes this request into the provider-specific format, then estimates how many input tokens that payload will consume.

Common Methods

1. Exact tokenizer

If the model's tokenizer is available:

estimated_input_tokens = len(tokenizer.encode(serialized_prompt))
This is the best option.

2. Provider token-count API

Some providers expose an endpoint that counts tokens before generation.

This is accurate, but it may add:

Another network call
Latency
Rate-limit usage
3. Conservative character estimate

When the tokenizer is unavailable:

estimated_tokens ≈ characters / 3
or another deliberately pessimistic ratio.

For English, people often use roughly four characters per token, but a budget controller should estimate more conservatively because code, JSON, Indic text, and tool schemas tokenize differently.

Important Detail

Count the actual provider payload, not only the user's message.

This is wrong:

count(user_prompt)
This is correct:

count(
  system_prompt
  + tools
  + history
  + retrieved_context
  + user_prompt
  + provider wrappers
)
Then the gateway computes:

projected_cost =
estimated_input_tokens × input_price
+
max_tokens × output_price
The input side is estimated. The output side uses the configured maximum, because the actual output length is not known before execution.


Watch admission happen: projection, comparison, decision, all before a provider is contacted. The burn-down view shows five real principals, one of them past 100% and exhausted.
9. Denial of Wallet

Session 12's eighth invariant required every run to operate under enforceable limits on time, tokens, tool calls, and money. Until now, that was a promise. This is the test.

An adversarial loop requests work 200 times against a $0.02 ceiling.

200 loop rounds  ->  60 calls admitted, 123 refused
spent $0.00759225 against a $0.02 ceiling
call ceiling of 60 reached
17 gateway errors reported no tokens, so nothing was charged for them

[PASS] the controller, not the loop, stopped the spend
The loop never stopped requesting work. The agent never decided to become careful. Spending stopped because a limit outside the agent enforced the boundary.

Two details matter more than the totals.

Every refusal became a visible graph failure carrying BudgetRefused, rather than a silently truncated answer. The run remains honest about work it did not perform.

Provider errors that returned no token counts were recorded separately rather than included in spend. A failed call with no reported usage provides nothing reliable to price.

This is a security problem, not only a financial one.

An attacker who drives an agent into a reasoning or tool-use loop can turn the inference budget into a denial-of-service mechanism. Incident reports from 2026 include multi-agent pipelines generating more than $47,000 in spend over one weekend.

The defence is the same hard controller, combined with:

Per-session token limits
Per-run call limits
Spend ceilings
Human approval above a defined threshold
The Safest Outcome Was the Least Visible

Building the dashboard revealed an unexpected failure in observability.

A refused call left no evidence anywhere.

It created no ledger row because nothing was billed. It created no span because tracing began only after admission succeeded. The system's most protective behaviour was therefore also its least observable.

An operator watching the dashboard would see an untouched budget and no record of the calls that had been prevented.

A refusal recorder now stores the envelope of every HTTP 402 response.

A control that prevents work leaves no trace of the work it prevented. If the prevention is not recorded, telemetry describes a system that never needed protection.

Step the loop and watch spend flatten while requests keep arriving. Toggle the controller off to see the extrapolated counterfactual, clearly marked as extrapolation rather than measurement.
10. What the Measurement Refused to Confirm

This session began with a specific claim:

A cheaper model may reduce cost per call while increasing cost per resolved task, because failures trigger retries and escalation.
The commonly quoted example is a 25% reduction in cost per call combined with a 40% increase in cost per resolved task.

We built an experiment to demonstrate it.

The test used 12 tasks:

3 trivial
3 moderate
6 hard
Three strategies answered the same task set, and a generic rubric judge determined whether each response resolved the task.

STRATEGY	SPEND	CALLS	COST/CALL	RESOLVED	COST/RESOLVED TASK
A: Always frontier, openai/gpt-4.1	$0.019676	12	$0.00163967	12/12	$0.00163967
B: Always cheapest, openai/gpt-oss-120b, with two retries	$0.00213675	12	$0.00017806	12/12	$0.00017806
C: Budget-aware cascade	$0.00597325	14	$0.00042666	11/12	$0.00054302
The expected effect did not appear.

Strategy B was 89.14% cheaper per call and 89.14% cheaper per resolved task. The numbers are identical because the retry loop never ran. The cheapest rung resolved every task on the first attempt, including all six hard tasks, and matched the frontier model exactly.

The explanation is more useful than the claim we intended to prove.

Our cheapest rung is openai/gpt-oss-120b, priced at $0.15/$0.75 per million tokens. It is a 120-billion-parameter reasoning-class open-weight model.

Cheap and weak are no longer the same thing.
When the Trap Does Appear

Instead of forcing the expected conclusion, we derived the condition under which the cheap rung becomes more expensive.

If each successful task uses one call and every failed task consumes k calls, the cheap model loses when its resolution rate falls below:

r* = k / (C/c - 1 + k)
Here, C/c is the measured price ratio between the expensive and cheap models.

On our ladder:

C/c = 9.2
k   = 2
r*  = 26.8%
The cheap model would need to fail more than 73% of tasks before its cost per resolved task exceeded the frontier model. It failed none.

The industry example implies a much narrower price ratio of roughly 1.3×. At that ratio, r* rises above 90%, so even a small failure rate can make the cheaper model more expensive per resolved task.

The trap is a race between price spread and failure rate. A wide ladder can absorb substantial failure. A narrow ladder cannot.
This rule can be applied to any model ladder using two measured values:

Price ratio
Resolution rate
It is more useful than the anecdote it replaces.

Strategy C also produced an important result. The budget-aware cascade was three times more expensive than Strategy B per resolved task.

A cascade pays for every rung it passes through. It escalates when its confidence signal decides that the cheaper answer is insufficient. When that signal is wrong, the system pays twice for essentially the same answer.

11. Capability Is Not Monotonic

One task explains the previous section better than the aggregate results.

t04_dates asks for the date 45 days after 3 March 2026, counted inclusively, together with the weekday.

The correct answer is:

Thursday, 16 April 2026
RUNG	MODEL	ANSWER	VERDICT
Economy	openai/gpt-oss-120b	“Thursday, 16 April 2026”	Resolved
Standard	gemini-3.1-flash-lite	“Friday, 16 April 2026”	Unresolved
Frontier	openai/gpt-4.1	“16 April 2026 is a Friday”	Unresolved
Every model calculated the date correctly. Only the cheapest model identified the correct weekday.

The cascade escalated through all three rungs, spent $0.00415, which was twelve times the cost of the economy strategy on the same task, and still ended with the wrong answer.

A price ladder orders models by cost. It does not order them by competence on a specific task.
This is the strongest argument in the session for evaluating models against your own traffic.

A ladder built from benchmark averages may route difficult requests to a more expensive model that performs worse on those requests. The cost ledger will show that the routing worked exactly as designed, while revealing nothing about the loss in answer quality.

A second finding appears in the same task.

The cascade's economy attempt stopped at exactly 512 output tokens, the ceiling for that rung. The generic rubric detected the truncation through its consistent and complete criteria without containing any date-specific knowledge.

The token cap that makes a rung cheaper can also make it fail.
A truncated answer is still fully billed. It becomes another form of the same failure that opened this session: the system pays for generation but does not receive a usable result.

12. Judging Costs Money Too

Deciding whether an answer resolved a task requires judgement, and in 2026 that judgement is often provided by another model. Doing this honestly is difficult, and doing it at all has a cost.

Our rubric is deliberately task-agnostic, because a judge that already knows the correct answer is effectively an answer key.

Five criteria are scored from 0 to 4:

Does the answer address the requested task?
Is it specific rather than evasive?
Is it internally consistent?
Is it complete enough to act on?
Does it satisfy the success criterion supplied by the task?
The first four criteria have weight 1. The success criterion has weight 2.

An answer is resolved only when its weighted score reaches 0.75 and no individual criterion falls below 0.5.

That minimum exists for a specific reason. A fluent, complete, and self-consistent answer to the wrong question scores 4 out of 6 on the generic criteria, or 0.667. A simple threshold could allow it to pass. The per-criterion floor prevents that.

Four safeguards make the verdicts usable.

The judging panel is separate from the answering ladder, so no model grades its own answer. Every verdict records the judge model and a self_judged flag that the proof verifies.

An unparseable verdict is recorded as a judge failure with resolved = None. It is never silently counted as resolved or unresolved, because either default biases the result.

An empty or errored answer is marked unresolved without spending another model call.

The panel's agreement is also reported. In this experiment, all 35 judged answers received unanimous verdicts.

Then comes the number usually omitted:

judging: 26 calls, $0.01486990
strategy B, the entire experiment being judged: $0.00213675
Evaluation cost 7.0× more than the work it evaluated.
This is the meta-cost problem in its clearest form. A router that calls one model to decide which model should answer must justify the cost of that decision.

What Is Wrong With Our Judge

An evaluation method must also state its limitations.

Every resolved answer received full marks on every criterion. The judge therefore behaves almost like a binary classifier, with most of its discrimination coming from the task-specific success criterion.

The 0.75 threshold is close to the 0.667 score of a confidently wrong answer. A careless change in weighting can break the decision boundary.

The verdicts are also not fully reproducible. The same model on the same task changed verdicts across runs because temperature 0 does not guarantee deterministic output. Single-run resolution counts should therefore be read with roughly one task of uncertainty.

The judging panel is composed of mid-tier models and may be weaker than the frontier model it evaluates.

Finally, the judge reads untrusted task and answer text. Wrapping both as data reduces prompt-injection risk, but does not remove it.


Score a sample answer and watch the verdict flip, including the case the floor exists to catch. The meta-cost panel puts the judging bill beside the bill it was grading.
13. Honest Failures

Four failures taught us more than another green check.

A refusal was invisible. As covered in §9, the safest behaviour in the system left no trace until a separate refusal recorder was added.

A confidence signal made the result worse. The cascade originally treated a response below a minimum length as a reason to escalate. This caused a correct one-word answer to be replaced by a more expensive model.

Emptiness can indicate failure. Brevity cannot.

The rule now treats only an empty response as a failure signal, and the reasoning is documented beside the configuration value.

The projected and measured price spreads differed by a factor of eighteen. The price list suggested an 84.3× difference between the lowest and highest rungs. Real prompts produced only a 4.55× difference.

A price-page ratio describes token rates. It does not predict the ratio that will appear on the bill.
A pinned model can look exactly like a dead provider. NVIDIA initially appeared unavailable. Every request waited for the full 180-second timeout and returned an empty error string.

The endpoint and API key were working. A different model using the same provider and key responded in 1.2 seconds. The failure came from one incorrect model pin.

From the caller's side, a provider that never responds and a model that never responds look identical. The distinction appears only when the same provider is tested with another model.

What This Session Does Not Solve

Cost variance makes fixed budgets imperfect. The same task can cost different amounts across runs. A ceiling tight enough to matter may therefore reject work that could have completed within budget.

A cheap rung without failover inherits one provider's limits. Pinning one model to one provider makes the architecture easier to understand, but creates production fragility. The denial-of-wallet experiment produced 17 gateway errors, mostly from rate limits.

Errors without usage remain unpriced. A provider may consume prompt tokens before failing and still charge for them. When no usage data is returned, the gateway cannot attribute that cost. Rate limiting remains the primary defence.

Prices change frequently. Every figure in §3 and §5 was verified on 30 July 2026. They must be checked again before being used for planning. Through 2026, frontier models and their pricing changed on a quarterly cadence.

14. Run it

Three terminals plus Jaeger.

git clone https://github.com/theschoolofai/glc_v4.git
git clone https://github.com/theschoolofai/S15Code.git
Start Jaeger first, so the traces have somewhere to land. Docker is the normal path.

docker compose -f glc_v4/docker-compose.observability.yml up -d
# UI on http://localhost:16686, OTLP on 4317 (gRPC) and 4318 (HTTP)
Terminal one, the gateway:

cd glc_v4
uv sync
export GLC_OTEL_EXPORTER_ENDPOINT=http://localhost:4318
uv run glc serve
Terminal two, the runtime:

cd S15Code
uv sync
export GLC_BASE_URL=http://127.0.0.1:8111
export S15_OTEL_EXPORTER_ENDPOINT=http://localhost:4318
uv run s15code serve
Check the gateway, then open the dashboard at http://127.0.0.1:8111/dashboard:

curl http://127.0.0.1:8111/healthz
curl http://127.0.0.1:8111/v1/status
curl http://127.0.0.1:8111/v1/cache/stats
Set a budget and watch it refuse:

curl -s -X POST http://127.0.0.1:8111/v1/budget \
  -H 'Content-Type: application/json' \
  -d '{"principal":"session:demo","limit_usd":0.00003,"window":"lifetime"}'

curl -s -X POST http://127.0.0.1:8111/v1/chat \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"say ok"}],"max_tokens":2048,
       "reasoning":"off","provider":"gemini","session":"demo"}'
# -> HTTP 402 with projected_usd, remaining_usd and shortfall_usd
Run an agent task with a ceiling, then find its trace in Jaeger by the returned trace_id:

curl -s -X POST http://127.0.0.1:8113/v1/agent/runs \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Compare two approaches to bounding agent spend.",
       "budget_usd":0.02, "tenant_id":"course","project_id":"s15",
       "user_id":"student-01","agent_id":"assistant"}'
Configuration lives in YAML. pricing.yaml carries per-model prices, routing.yaml the tiers and roles and cooldowns, budgets.yaml the allowances, cache.yaml the threshold. Adding a model, a role, a tier, or a budget never requires a Python edit — and a malformed config raises at boot rather than degrading quietly into "no budget".

15. The proof suite

cd glc_v4    && uv run pytest -q     # 445 passed
cd ../S15Code && uv run pytest -q    # 244 passed
Then the proofs, each taking the task, budget, and principal as arguments so they run on work they have never seen:

PROOF	WHAT IT ESTABLISHES
p1_cost_per_task.py	Three strategies over one task set; cost per call against cost per resolved task; the break-even rate
p2_budget_holds.py	A ceiling holds across four allowances; downgrade under pressure; refusal at exhaustion
p3_denial_of_wallet.py	An unbounded loop is stopped by the controller, with every refusal visible
p4_trace_export.py	A real trace is fetched back from Jaeger by ID; span costs sum to the ledger; no content leaves
p7_cross_model_ladder.py	Each rung is served by the model its config names, and a downgrade changes the model
cd S15Code
uv run python proofs/p2_budget_holds.py --task "<your task>" --budget 0.02 --principal "demo/you"
uv run python proofs/p1_cost_per_task.py --tasks proofs/tasks/mixed.jsonl --principal "demo/you"
Every proof exits non-zero on failure and writes machine-readable JSON to proofs/out/. Swap in your own task file and the harness works unchanged; that is the property that makes it a proof rather than a demonstration.

16. The assignment

Build a routing and budget policy for a workload of your choosing, and prove what it costs.

Part 1: reproduce the floor

Run both suites and the five proofs. Capture, for four runs: the prompt, the tier and model chosen, the ordered event trace, the Jaeger trace ID, the ledger rows, and the final answer. Then state one honest limitation the traces exposed.

Part 2: build a policy and measure it

Choose a task class with at least fifteen tasks — your own domain, not the shipped file. Build a ladder and a budget policy for it. Then measure, against an always-frontier baseline:

cost per call and cost per resolved task, with a judge whose rubric you can defend,
the break-even resolution rate for your ladder from its measured spread,
at least one task where your policy chose wrongly, and what it cost.
A submission that reports only savings has not finished. Every routing policy trades quality for money somewhere, and finding where is the work.

Part 3: attack your own budget

Write an adversarial test against your policy. Drive a runaway loop, request an unaffordable tier, force a cascade to climb its whole ladder, or arrange for a provider to fail after consuming tokens. Show the spend before your control and the refusal after it, and show that the refusal is visible in your telemetry.

What you submit

A pull request to S15Code adding your policy, your task file, and one evidence section in the README containing:

the workload and the ladder you built for it,
the measured cost per call and cost per resolved task against the baseline,
your ladder's break-even resolution rate, and where you sit relative to it,
a Jaeger trace showing one run's span hierarchy with costs,
the adversarial test, failing before your control and refused after,
one case your policy got wrong,
the commands to reproduce all of it from a fresh checkout.
Secrets, .env, and real user data never enter the pull request.

Scoring

AREA	POINTS
Measured cost per resolved task, honestly obtained	25
Proof quality and reproducibility	25
Budget enforcement that holds under attack	20
Observability: traces, attribution, refusals visible	15
A case your policy got wrong, and its analysis	10
Explanation simple enough to operate	5
A policy that saves 80% and cannot say what it broke scores badly. A policy that saves 20% and can name precisely which tasks it degraded, by how much, and when it would stop being worth it, scores well.

17. What this session commits us to

Four commitments carry forward.

The first is that cost per task is the unit. Cost per call is the number that improves while the bill grows, and a strategy that lowers it while raising the cost of a finished piece of work has made things worse in a way its dashboard will not show.

The second is that a budget is a hard controller. Models overshoot budgets stated in their instructions, so enforcement lives in code the model cannot reach, before the provider is contacted, and a refusal is a visible outcome rather than a silent truncation.

The third is that every call becomes a span, and the spans agree with the ledger. Two independent records of the same spend that reconcile exactly are what make a cost claim trustworthy. Content stays out of them by default, because a trace is not a place to keep the user's words.

The fourth is the one we did not plan to teach. Price does not order models by competence at your task. The cheapest rung on our ladder was the only one that answered a date question correctly, and the cascade that escalated past it paid twelve times as much to be wrong. Route on measurements taken from your own traffic, and re-take them when the frontier turns over, which is now roughly every quarter.

The shortest statement of the whole session:

Spend only what the work justifies. Record every unit you spend. Refuse before you exceed the ceiling rather than explain afterwards. And measure which model is actually good at your problem, because the price list will not tell you.