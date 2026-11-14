# AI OS: an honest review, version 2

14 Nov 2026. Written by Claude at your request. Version 2 answers your comments on version 1. A copy you can comment on, with version 1 and your comments in its second tab, is at https://claude.ai/artifact/PUhDjcE4UxEqxDq1dJ9qDV.

## The verdict now

Build it, in a different shape and a different order. Version 1 said "do not build an AI OS, build three small tools". After your comments I would put it this way: **build one personal record that you own, and one agent that works for you from it.**

The idea is good for a reason version 1 missed. The assistants answer when asked. Nothing follows up with you, remembers what you meant to do, or watches your sources while you are busy. That gap is real, and it is where a personal system earns its place.

What I still hold: the plan was built platform-first, the gateway is not worth building, and the knowledge graph is right in direction and wrong in timing.

## What I got wrong in version 1

**Who you are.** You are an AI engineer, not an equity analyst. I took the persona on your pitch slide as you. That removes the "analyst's desk" tool and changes how the rest should be judged.

**Building as a hobby.** Ingestion, retrieval, evals and agent orchestration are your job. Building them has value even when the tool is replaceable, because the skill carries to work. Version 1 counted that as zero.

**The source watcher.** I filed your podcast, channel and website tracker under "freeze". It passes my own test: it runs without being asked, and it saves hours you do not have. It may be the most useful tool on the list.

**Owning your data.** You said you cannot keep handing personal data to the assistants, and that there must be a separation somewhere. I under-weighted this. It is a real reason to build the record yourself.

**Claude Code and Codex as tools.** Having your agent start a Claude Code or Codex session for research, and take back the result, is the most forward-looking idea in your comments. You get a strong research worker without building one.

**The grader risk.** I overstated it. For "is this understanding correct against this source", a strong model is rarely wrong. The risk that remains is leniency: it agrees too easily.

## Where I still disagree with you

### The knowledge graph

You said it is not about this year, it is about the rest of your life, and asked me to argue. Here is the argument.

**What lasts for life is the raw record, not the graph.** Sources, passages, your answers, your mistakes and your intentions, each with a date and where it came from. A graph is an index built from that record. It can be rebuilt at any time.

**A graph built now is the part most likely to be thrown away.** Pulling entities and relations out of text improves every year. A graph built today bakes in today's errors and a schema (the fixed shape of the data) you will regret. Your own comment says you would replace it when something better comes. The raw record is what survives that replacement.

**You are right about where it wins.** Search by meaning finds passages. It does not answer "what contradicts what", "how did my view on this change over two years" or "which sources all rest on the same claim". Those need structure, and they are exactly the questions a lifelong record should answer.

**So keep the raw record now and add the graph after the capstone.** Store every source and passage with its date and origin. Point the graph at that record when it holds a few hundred passages, or when you hit a question that search by meaning cannot answer, whichever comes first.

**Graphiti, not a hand-built graph.** You confirmed the graph will use Graphiti, a library that builds a graph of dated facts from text, so nothing is built by hand. That removes my cost objection. The timing point stays: the graph is built from the raw record, so the record comes first and the graph can be rebuilt from it whenever the tooling improves.

### Ingestion

You are passionate about this part, and storing what you read is the right direction. My disagreement is about where the value is.

**Capturing feels like learning and is not.** You named the real problem yourself: you read something, want to apply it, and life gets in the way. Nothing in ingestion fixes that. The return path does: what comes back to you, when, and whether it asks something of you.

**Keep intake thin and borrowed.** Libraries and existing tools already turn PDFs, pages, video and audio into text. Your part is the narrow step that files the text into your record with its source and date. A rule I would follow: for every hour spent on intake, an hour on what comes back.

### Privacy and the gateway

We agree the gateway goes. One correction to the reasoning: a gateway never gave you separation. Any call to a hosted model sends that text out, whatever sits in front of it. Separation comes from two things: your store stays on your machine or server in open formats, and sensitive material goes to a local model.

### "The assistants are for enterprise"

Half right. They are reactive, they know you shallowly and they never hold you to anything, so individuals get far less from them than they could. But they are shipping memory, scheduled tasks and connectors for individuals. Anything general you build will be matched. Bet on what stays yours: the record and the follow-up rules. Make both plug into whichever assistant is best that year.

### Jarvis

A person in your pocket who understands what you read and pushes you where you want to go is a good direction and a bad specification. As a specification it has no edge, so everything belongs in it, which is how 38 projects happened. As a direction it breaks into four small things, listed in the next sections.

### An option for hand-written or LangGraph

I would not build both. Two loops means two things to test and keep working. Hand-written for the capstone, because the course requires it. After that, pick one and delete the other.

## Two tests for every piece

Version 1 used one test. Because building is also your work, there are now two, and a piece must say which one it is passing.

**The life test.** Would a saved prompt in an assistant, plus a file, do this? If yes, building it adds nothing to your life. A piece passes only if it needs a record that builds up over time, acts without being asked, or keeps your data in your hands. You agreed with this test.

**The work test.** Does building it teach you something you will use as an AI engineer? Retrieval quality, evals, agents that run reliably and systems that stay up all pass. Plumbing that a library already does well does not.

**The rule between them.** A piece that passes only the work test is practice. That is allowed, but it gets a time limit and it never blocks a piece that passes the life test.

## Piece by piece, revised

**Gateway: drop entirely.** Agreed on both sides.

**The record: build, and own it.** One store on your machine or server in open formats: sources, passages, claims, your answers, mistakes and intentions. This is the lifelong asset, and it passes both tests.

**Ingestion: keep thin, borrow the heavy parts.** File text into the record with source and date. Use libraries for PDFs, pages, transcripts and audio.

**Knowledge graph: after the capstone, with Graphiti.** The raw record is stored so the graph can be built from it at any time. Nothing is hand-built.

**The examiner: build.** Cards, questions and grading against the source. This is the capstone.

**The watcher: build next.** It tracks the websites, channels and podcasts you choose, turns each new item into text, and sends you only what matters, with the reason. It needs a hard limit, such as five items a week, or it becomes one more feed you ignore.

**The follow-up agent: build third.** When you read something you want to apply, you log it as an intention. The agent comes back to you on it, asks what happened and adjusts. This is the one piece that is a true agent, because it decides for itself what to raise and when.

**Research and claim checking: delegate.** Your agent calls Claude Code or Codex as a tool and takes back the result. You build the call and the safety rules around it, not the research.

**Orchestrator: keep small.** One loop that picks a tool. Hand-written for the capstone. You were right that all of this together needs an agent in the middle; that agent is the follow-up agent, not a separate platform.

**Steelman and the other prompt agents: keep as prompts.** You said yourself they are prompts in YAML. Leave them as files the agent can load. Do not give each a service.

**Tasks, calendar, reminders: connect, do not build.** Talk to the apps you use, such as Instinct or Hark, through their connectors.

**Telegram, WhatsApp, screens: later.** Reach the system through the assistant you already use, with your record exposed as one connector. Build a screen only when a tool needs one that no assistant can show.

**The decision ledger: optional.** Version 1 pushed this for an analyst. For you it is worth adding only if you want to track your own predictions.

**Everything else: freeze.** The UPI agent, interview coach and experiments stay out until one of the pieces above is in daily use.

## What I would make it into

**One record.** A single store that only you hold. It keeps four things.

1. **What you read:** sources, passages and the claims in them.
2. **What you got wrong:** your answers, how they were graded, and the mistakes.
3. **What you meant to do:** intentions you logged from what you read, and what happened to each.
4. **What you follow:** the sources you want watched, and what they published.

**Four tools that read and write it.**

1. **Intake** puts a source into the record.
2. **The examiner** tests you on it.
3. **The watcher** brings in new material from your sources and filters it.
4. **Research** hands a question to Claude Code or Codex and files the answer.

**One agent in the middle.** The follow-up agent looks at the record on a schedule and decides what to bring to you: a card that is due, a mistake to revisit, an intention gone quiet, an item the watcher found. This is the Jarvis part, kept to one job.

**Everything else borrowed.** Models through a library, with a local model for sensitive material. Surfaces through the assistant you already use, with the record exposed as one connector (an MCP server, a standard plug that lets an assistant call your tool).

**How I would structure the code.** A trunk of four small files: the model door, the store, the tool list and the loop. One folder per tool. One folder of prompts as plain files. One file of your own test sentences per tool. One page of plan.

**Safety, because this version acts on outside content.** The watcher and research read the open web. Your own rule says an agent that reads untrusted content must never directly trigger one that acts. So Claude Code and Codex sessions run read-only, what they return is stored as content and never followed as an instruction, and anything that sends or changes something outside the record needs your yes.

**You can keep the name.** My objection was never to calling it an AI OS. It was to building the platform before the first useful tool. With one record and one agent, the name fits.

## What I would do in your place

**This week, to Sunday 22 Nov: the capstone.** It is the record plus the examiner, so the deadline and the long-term plan point the same way. One caution from your comments: if claim checking calls Claude Code or Codex from the Hetzner server, that server needs its own API key and a read-only session. For the capstone I would keep ask 1 as a direct model call and add delegation afterwards.

**The two weeks after: use it.** Put in what you actually read and answer the cards daily. Keep a note of each time the grader was too lenient. What you learn here decides the next step better than any plan.

**December: the watcher.** Start with five sources you already wish you kept up with. Success is one thing: you stop feeling behind on them.

**January to March: the follow-up agent.** Start with intentions only: you log what you want to apply, it comes back to you. Add delegation to Claude Code or Codex for research once the agent is steady.

**Through next year: the graph.** Point Graphiti at the record once it holds a few hundred passages, or sooner if a question you care about cannot be answered by search.

**The five-year view.** Models, assistants and tools will be replaced several times. Three things carry through: a record in open formats that is years deep, a set of test sentences that says what correct looks like for you, and the skill of building agents that run without supervision. Every choice above is made to grow those three.

**The one rule.** No new tool until the last one has been in real use for two weeks. You enjoy making things and thinking of new ones, which is a strength and the cause of the 38. This rule lets you keep the strength.

## How a person makes the best use of AI in their life

You agreed with most of version 1's list. Those points stay, shortened, with three added from your comments.

**Kept from version 1.** Start from a task, not a system. Save prompts before writing programs. Build only where value builds up over time. Use AI to test your thinking, not to replace it. Keep a human yes on anything that sends, pays, books or deletes. Measure by what you used this week.

**Changed: use the assistants, and connect more than most people do.** Your comment was that this is what you want to make, with more sources and surfaces than most people connect. I agree with the aim. The cheapest route is your own record as a connector inside the assistant, not a second assistant beside it.

**New: own the record, rent the intelligence.** Keep your data in your own store in open formats. Treat every model and assistant as replaceable. This is the separation you asked for, and it is what makes the system last longer than any one product.

**New: make it come to you.** The largest unused value for an individual is not a better answer. It is something that returns to you unasked: tests you on what you read, reminds you what you meant to do, and tells you what you missed. Most people never set this up, and no assistant does it well yet.

**New: let building pay twice.** If the skills are your job, choose the builds that also teach what your work needs, and finish them. One system with tests and months of real use is worth more, to you and to an employer, than many started ones.

## What I am still unsure about

**Whether you will use the examiner.** Being tested is effort. If you skip the cards for a week, the follow-up agent matters more than the examiner, and the order above should change.

**Whether the watcher's filter can be good enough.** Deciding what matters to you is a hard judgment. It may take months of your corrections before it is worth trusting.

**How proactive is welcome.** An agent that pushes you can become one you mute. How often it should speak is something only real use will show.

**The cost of delegation.** Starting a Claude Code or Codex session for each research question costs money and time per call. I have not measured either.

**The graph timing.** I may be wrong that search by meaning is enough for the first months. If you hit a question it cannot answer early, you were right and Graphiti moves up.

**I still have not run anything.** Parts of the existing ingestion and graph code may be reusable. That is unknown until they are tested this week.
