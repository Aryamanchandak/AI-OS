Last updated: 2026-05-10

---

# Prompt and Plan Optimizer — Comprehensive Overview

---

## 1. What This Project Is

This project is a personal, single-user web tool that helps someone interrogate and improve two things: AI prompts (the instructions you give an AI model) and technical plans (markdown documents describing how a software project should be built). The core idea is that when an AI generates a prompt or a plan, the output is opaque — you can read it but you can't easily tell *why* each part exists or what would happen if you changed something. This tool breaks that output into labelled pieces, lets you chat with the AI about any individual piece, shows you exactly what changed when you make an edit, and warns you when an edit in one place creates a problem somewhere else.

The project is built as a web application that runs on your own computer and calls the Anthropic (Claude) AI API to do its thinking. It is squarely in early development: the underlying logic is largely written, but the actual visual interface is still a placeholder.

---

## 2. The Big Picture — How It All Fits Together

Think of this tool as a document editor crossed with a conversation interface, crossed with a code-review diff view.

You start by pasting in either a prompt or a plan. The AI reads the whole thing and automatically slices it into labelled sections — each with a name, a type ("this is the system role section" or "this is the phase-two module"), and a sentence explaining why that section exists. You never have to split it yourself.

Once it's split, you see three panels side by side. On the left is the list of sections. In the middle is whichever section you've clicked on, plus a chat thread scoped just to that section. On the right is a diff view showing exactly what changed between the previous and current version of a section, and — depending on the mode — either a list of test results or a list of logical conflicts.

The two modes differ in how they verify that an edit was good:

In "prompt mode," the tool treats a prompt like a function that takes inputs and produces outputs. You write test cases — example inputs with expectations about what the output should look like — and after each chat-driven edit the tool reruns those tests and shows you which ones now pass or fail. A test that used to pass and now fails is flagged loudly as a regression.

In "plan mode," there are no tests, because a markdown plan doesn't "run" the way a prompt does. Instead, after each edit the AI checks the entire document for logical contradictions: did the edit in section three now conflict with something section five still says? That conflict is surfaced as a notice that you can click to jump to the affected section.

Underlying all of this is a project context layer. Before you paste your prompt or plan, you can dump a freeform description of what you're building — your tech stack, constraints, open questions, decisions already made. The AI structures that dump and feeds it as context into every subsequent call. This means that when you ask "why is this section here," the AI's answer is grounded in your specific project, not a generic guess.

Every time you make an edit that actually changes the content of a section, the tool takes a snapshot of the full document state and adds it to a version history. You can roll back to any previous version at any time.

---

## 3. Every Component — What It Does and Why It Exists

### The Web Application Shell

The project runs as a Next.js application — a framework that handles serving web pages and routing requests. It was generated from a standard template and has the minimal configuration needed to run locally. The shell's only contribution at this stage is providing the infrastructure for the rest of the code to sit inside.

### The API Relay (the server-side gateway)

There is a small server-side endpoint that acts as a secure middleman between the browser and the Anthropic AI API. When the browser needs to ask Claude something, it sends the request to this local relay. The relay picks up the API key from a protected environment variable and forwards the request to Anthropic's servers, then hands the response back to the browser.

This relay exists because API keys must never be exposed in a browser — a browser-visible key is a publicly accessible key. The relay keeps the key on the server side only. Without it, the app would either have to embed the key in the browser (a security hole) or ask the user to supply it on every request.

### The Types Definition

There is a file that defines the shape of every major piece of data the application works with. Think of it as the project's vocabulary list — it says what a "section" is (an identifier, a title, a type, the actual content, a rationale sentence, and a history of edits), what a "test case" is, what a "version snapshot" is, what a "conflict" is, and so on.

This file does nothing by itself, but it is the contract that keeps every other part of the system speaking the same language. If a section is supposed to have a rationale, this file is where that expectation is recorded. Every other module that creates or reads a section knows what to expect because of this definition.

### The Claude Communication Module

This is a thin layer that knows how to talk to the relay. It provides two modes of asking Claude a question: one that returns a plain text response, and one that insists on getting back a structured data object (like a JSON record) with automatic retry if Claude's first response is malformed. The retry logic strips markdown formatting fences and tries again with a more forceful instruction to return pure data.

Without this module, every part of the app that needed to ask Claude something would have to re-implement the same error handling, formatting cleanup, and retry logic. It centralises that plumbing in one place.

### The Prompts Library

This file contains every instruction given to the AI, stored as reusable templates. There are five distinct prompts:

The section splitter prompt instructs the AI to read a prompt or plan and divide it into labelled sections, preserving the text verbatim, generating a rationale sentence for each, and returning the result as structured data.

The context extractor prompt instructs the AI to read the user's freeform project description and structure it into specific fields: the project goal, the technology choices, constraints, decisions already made, architectural notes, and open questions.

The iteration prompt is the most complex. It is constructed on-the-fly for each chat message. It gives the AI the project context, the full document, the specific section being worked on, the history of prior chat messages in this section's thread, and the user's current message. It tells the AI to either explain the section as-is, rewrite it based on the request, ask a clarifying question if the request is ambiguous, or suggest a context update if the chat reveals something new and worth remembering. All four outcomes are returned in structured form.

The conflict detection prompt is used in plan mode after every edit. It shows the AI the full document with the just-edited section clearly marked, and asks it to identify contradictions (one section says X, another says not-X), redundancies (significant overlap between sections), or orphan references (one section references something the edited section used to define but no longer does).

The judge prompt is used in test assertions. When a test case uses a semantic assertion — a plain-language description of what the output should achieve — the judge prompt sends that criterion and the actual output to the AI and asks for a pass/fail verdict with a brief explanation.

These prompts are the core intellectual work of the product. They are the rules that determine the quality of every section split, every rewrite, every conflict notice. They live in one place so they can be tuned without hunting through code.

### The Operations Module

This is where the prompts and the communication layer are assembled into useful actions. It exposes five major capabilities:

Section detection takes a raw blob of text and a mode flag, calls the section splitter prompt via the communication layer, and returns a properly structured list of sections with stable identifiers assigned.

Context extraction takes freeform text, calls the context extractor prompt, and returns a structured project context object.

Section iteration takes a section, the full document, the project context, the chat history for that section, and the user's latest message. It calls the iteration prompt and returns the rewritten content, the reasoning, and any clarifying question or context suggestion.

Conflict detection takes the full set of sections and the identifier of the section just edited, calls the conflict detection prompt, and returns a list of conflict objects.

Test running assembles the full prompt from all sections, substitutes any template variables (placeholder slots like double-bracketed words) with the test case's input values, sends the result to Claude as a system prompt with the test context as the user message, collects the output, and evaluates it against each assertion in the test case. For substring assertions, it checks locally whether the output includes or excludes a specific phrase. For structural assertions, it checks whether the output is valid structured data with the expected fields. For semantic assertions, it calls the judge prompt. For reference similarity assertions, it calculates a word-overlap score between the output and a reference example.

### The Diff Module

This module implements a standard algorithm for comparing two texts line by line and identifying which lines were added, which were removed, and which stayed the same. It is a self-contained piece of math — it takes two strings and returns a list of annotated lines. The rendering layer uses this output to draw the green/red highlighted diff view.

It exists because displaying "here is exactly what changed" is a core promise of the tool. Without it, after an edit you would have to compare old and new text by eye.

### The Versioning Module

This module provides two functions. The first creates a deep frozen snapshot of the current document state — it deep-copies the document, the test results, and the conflict list, and packages them with a timestamp. The second compares two snapshots of test results and classifies each test case as a regression (it used to pass, now it fails), a new pass (it used to fail, now it passes), or unchanged.

This module exists because the version history is one of the tool's key promises: you can always go back, and you can see not just what the document looked like at any past point but also what the test suite looked like at that moment.

### The Storage Module

This module knows how to save and load three things to and from the browser's local storage — which is essentially a small private key-value database that the browser keeps on your machine, tied to this particular web address. The three things stored are the current document, the project context, and the version history. The version history is capped at fifty snapshots to prevent it from growing without bound.

It checks whether it is running in a browser context before attempting any reads or writes, because the application framework can also run on the server side during initial page load where browser storage doesn't exist.

Without this module, every time you refreshed the page, you would lose your work. It is the persistence layer.

### The Onboarding and Main Page

The current actual web page is a minimal placeholder. It shows a dark-background screen with the title "Prompt/Plan Optimizer — Backend," a note that "Phase A: backend layer only, UI coming in Phase B," and a single amber button labelled "Test backend." Clicking the button sends a simple hardcoded message to Claude via the relay and displays the response. Beneath the button, there is a static list of the library file names to confirm they exist.

This page is purely a confidence check — it exists to verify that the relay is working and the API key is configured correctly. It is not the real user interface.

### The Reference Scaffold (not wired in)

There is a second file at the root of the project, separate from the web application, that contains a complete working implementation of the entire tool's logic and a minimal rough interface. It is described in its own header comments as "scaffolding UI just to exercise the backend" and explicitly instructs the reader to "lift the top half into your real codebase when you build the production UI."

This file contains duplicates of the prompts, the Claude communication helpers, the operations, the diff algorithm, and the versioning logic — plus a fully wired React user interface with all three panels, the chat thread, the diff view, the conflict display, the test result display, and the version history.

Crucially, this file is not part of the web application. Next.js does not import it. It also calls the Anthropic API directly from the browser rather than through the secure relay — which would expose the API key and fail due to browser security restrictions in a deployed setting. It was written as a design prototype and a reference implementation in a single self-contained file, intended to be broken up and properly integrated as Phase B work begins.

The header of this file also contains a very detailed plain-English specification for what the production interface should look like: every screen, every button, every edge case, every interaction pattern. This specification and the scaffold implementation together form the design blueprint for the UI that has not yet been built.

---

## 4. How a Typical Interaction Works

### Using Plan Mode

A user who has just written a markdown technical plan for a new software project opens the app in a browser. They are greeted by the onboarding screen.

They type a description of their project into the project context area — something like "building a spaced repetition flashcard app, using Postgres, React on the frontend, decided not to use a third-party FSRS library" — and click the extract button. The app sends this text to Claude via the relay. Claude returns a structured summary: the goal is a flashcard app, the tech stack is Postgres and React, a key decision is to implement FSRS directly, and so on. This structured summary is displayed on screen and remembered for the rest of the session.

The user then pastes their plan into the document input area and clicks "Analyze and split into sections." The app sends the text to Claude with the section splitter prompt. Claude returns a list of sections — perhaps "Phase 1: Data Model," "Phase 2: Review Algorithm," "Phase 3: Frontend Components," "Open Questions" — each with a kind label and a rationale sentence. The app displays these sections in the left panel.

The user clicks "Phase 2: Review Algorithm." The middle panel shows the content of that section and its rationale. The right panel is empty of conflicts for now.

The user types into the chat box: "Why is the algorithm described this way — wouldn't a simpler scoring model be better?" They press Command-Enter. The app sends the full document, the section, the chat history (currently empty), the project context, and the user's message to Claude via the iteration prompt. Claude returns a JSON object explaining its reasoning (which appears in the chat thread) but does not rewrite the section because the user was asking a question, not requesting a change.

The user reads Claude's explanation and then types: "OK, simplify the algorithm section — make it match the constraint that we're not using a third-party library." Claude rewrites the section content. Because the content actually changed, the app saves a snapshot to version history, updates the section in the document, and immediately calls the conflict detection prompt on the full document. Claude comes back saying that the edited section now contradicts something in the "Open Questions" section, which still mentions evaluating third-party library options. A conflict notice appears in the right panel. The user clicks it, the left panel jumps to the "Open Questions" section, and they update that section's wording via another chat message.

At the end of the session, the user can click Export to copy the full document to their clipboard and save it elsewhere.

### Using Prompt Mode

A developer who has written a system prompt for a customer support chatbot pastes it into the document input area with the mode set to "Prompt." Claude splits it into sections: "Role Definition," "Tone Constraints," "Output Format," "Escalation Rules."

The developer adds a test case by clicking the test button, which adds a sample test to the document. They edit the test in the interface to specify a simulated user message asking about a refund, with a semantic assertion that the output "should be polite and offer a concrete next step." They click "Run tests" and see the results.

Then they click "Tone Constraints" and ask via chat to make the tone "warmer and less corporate." Claude rewrites the section. The app saves a snapshot, updates the section, and reruns all test cases. The test results in the right panel now show the refund test as newly passing after having previously failed — flagged as a "new pass." If any previously passing test had broken, it would be flagged loudly as a regression. The diff view shows exactly which lines were added and removed in the tone section.

The developer can browse back through the version history in the left panel to see what the prompt and test results looked like at any prior version.

---

## 5. How the System Makes Decisions

### Deciding Whether to Rewrite or Explain

When the user sends a chat message about a section, the iteration prompt instructs Claude to examine the intent of the message and choose one of four paths: explain the section without changing it (if the user asked a "why" question), rewrite the section (if the user asked for a change), ask a clarifying question back (if the request is ambiguous or there is not enough context), or do some combination of explaining while noting a possible context update.

The deciding factor is Claude's interpretation of the user's message combined with how much project context it has been given. If context is thin, the prompt explicitly instructs Claude to lean toward asking rather than guessing.

### Deciding Whether to Save a New Version

After each chat response, the application checks whether the section content that came back from Claude is different from what it was before. If the content is unchanged — because Claude explained or asked a question rather than rewrote — no version snapshot is taken. If the content changed, a snapshot is taken and added to version history. The decision is purely mechanical: changed content means a new version.

### Deciding Which Conflicts to Surface

After each edit in plan mode, Claude is given the full document and a marker identifying which section was just edited. Claude then independently judges whether the edited section now logically contradicts, duplicates, or orphans content in any other section. The prompt explicitly tells Claude to only flag real conflicts and not to invent stylistic issues. Resolved conflicts simply disappear from the list on the next detection run.

### Deciding How to Classify Test Changes

When test results come back after a prompt edit, the versioning module compares each test's current pass/fail status to its status in the most recent prior version. A test that moved from passing to failing is classified as a regression. A test that moved from failing to passing is classified as a new pass. Everything else is unchanged. The UI renders these three states with different visual treatments, with regressions being the loudest.

### Deciding Whether an Assertion Passes

For substring assertions, the decision is purely local — does the output contain (or not contain) the specified phrase. For structural assertions, it is also local — can the output be parsed as valid data with the required fields. For semantic assertions, the decision is delegated to Claude via the judge prompt, which returns a boolean verdict. For reference similarity assertions, the decision is a mathematical word-overlap calculation compared to a threshold the test case specifies.

---

## 6. What the System Remembers

### The Current Document

The document — the set of sections currently being worked on, including each section's content, kind, title, rationale, and full edit history — is held in memory while the app is open and written to browser local storage whenever it changes. If the user closes the browser and returns, the document is reloaded. If local storage is cleared, the document is gone.

### Project Context

The structured project context — extracted from the user's freeform dump — is saved to browser local storage separately from the document. It persists across page reloads. It grows when the user clicks a "save to context" suggestion from Claude during a chat. If lost, the user would need to re-enter their project description and extract again; the tool would still work but Claude's responses would be less grounded in project-specific knowledge.

### Version History

Each snapshot of the document state (plus test results or conflict list at the time of the snapshot) is saved to browser local storage. The system keeps at most fifty snapshots, automatically discarding the oldest when the cap is reached. Rolling back replaces the current document state with the snapshot's; it does not re-snapshot the pre-rollback state, so rolling back is a one-way operation in the current implementation.

### Per-Section Chat History

Each section has its own chat thread stored in memory. Chat history is used as context for the next chat message in that section — Claude can see what was discussed before and does not start from scratch. However, chat history is not currently written to local storage; it exists only for the duration of the browser session.

### Test Results

The most recent test run's results are held in memory and included in version snapshots. When the user rolls back to a prior version, the test results associated with that snapshot are restored.

---

## 7. What the System Talks To

### Anthropic's Claude API

This is the only external service the system calls. Every AI-powered feature — section splitting, context extraction, section iteration, conflict detection, test running (including the judge calls) — is a call to this API with a structured request and a structured response. The system uses the Claude Sonnet model specifically.

If this service is unavailable, the application degrades completely for any feature that requires AI. The local text-comparison and word-overlap similarity calculations would still work, but section detection, context extraction, chat iteration, conflict detection, and semantic assertions would all fail. The app handles API errors by catching the failure and surfacing an error message in the interface.

The API key is required for any AI call to succeed. The environment file in the project currently contains a placeholder value rather than a real key, meaning the application will not successfully make AI calls without the user replacing this placeholder with their actual key.

### Browser Local Storage

This is not an external service in the traditional sense — it is a small storage area that the browser provides for websites to save data on the user's own machine. The application uses it to persist the document, the project context, and the version history between sessions. Local storage is single-machine and single-browser; data does not synchronise across devices. If local storage is full or disabled, the save operations silently fail; the app continues to work for the current session but changes will be lost on reload.

---

## 8. What Is Currently Built vs. What Is Not Yet Built

### Fully Working and Complete

The API relay that securely forwards requests to Anthropic is complete and functioning. The build itself has been compiled and exists in a cached production form.

All five prompt templates are written, tuned, and ready to use. They represent careful, deliberate design with specific schemas, retry logic, and clear behavioral rules.

The Claude communication layer is complete, including the JSON retry logic.

The type definitions covering every data shape in the system are complete.

The operations module — section detection, context extraction, section iteration, conflict detection, test running, and assertion evaluation — is fully written and covers all four assertion types including the semantic judge.

The line-by-line diff algorithm is complete and correct.

The versioning module, including snapshot creation and test-change classification, is complete.

The storage module for saving and loading all three persistence keys is complete.

The reference scaffold file, despite not being wired into the app, contains a fully functional implementation of the entire system end-to-end, including the three-pane UI, chat interaction, diff display, conflict display, test running, and version rollback. It works as a reference and could be run in isolation (with a direct API key) as a prototype.

### Exists But Incomplete or Not Connected

The actual page the user sees when they open the app is a temporary placeholder — it has the backend connection test and a list of library names, but nothing else. The library files it lists are all written and ready, but nothing in the app's user interface calls them.

The storage module is written but no part of the current application imports or uses it. The document, context, and versions that the operations module produces are never persisted.

The versioning module is written but similarly orphaned from the actual page.

### Planned But Not Yet Built

The three-panel production user interface described in exhaustive detail in the reference scaffold's comment block does not exist as a real Next.js page or set of components. It is a specification awaiting implementation.

The test case authoring interface — the form where a user would create named test cases, add assertions with different types, set input variables — does not exist. Even the scaffold only adds a hardcoded sample test case via a button; there is no form to create custom tests with custom assertions.

The section override affordances (merging two adjacent sections together, splitting one section into two) are specified in the plan but implemented nowhere.

The clarifying question flow — where Claude asks a question, the chat pauses, and the user answers before the iteration proceeds — is specified in the plan and the JSON response shape supports it, but the user interface handling for the paused state and the distinct card rendering is not built.

The export flow (copying just the current section, or the full document, in markdown or plain text) is specified but not built into the real app.

The "save to context" chip that appears when Claude suggests a context update during a chat message is specified but not built in the real app.

The version comparison mode — shift-clicking two versions to see a diff of test results between them — is specified but not built.

The planned second phase involving a locally-running AI model, a file system watcher, and automatic project context derivation from the codebase is explicitly deferred and not started.

---

## 9. The Current State of the Project

This project is solidly in the foundation stage. The intellectual and technical work of defining "what this tool does and how" is unusually thorough — the design document is detailed, the prompts are carefully crafted, and the backend logic modules are all written. That is a meaningful amount of work completed well.

But the gap between the backend and the user interface is large. Right now, opening the app in a browser gives you a single button that pings Claude. The entire document editor, the three-panel layout, the chat interaction, the diff view, the conflict surfacing, the test runner UI — all of that exists only as a thoroughly commented reference prototype in an unconnected file, and as a detailed specification in comment blocks and a planning document.

The strongest part of the project is the prompts library and the operations module. These encode the real design insight of the tool — the decisions about how Claude should split sections, what "rationale" means, how the iteration prompt handles ambiguity by asking rather than guessing, how conflict detection distinguishes contradictions from redundancies. These are polished and ready.

The most fragile part is the disconnection between the written logic and the actual running application. The storage module, the versioning module, and all the operations are ready but not wired to anything the user can touch. If someone tried to use this tool today, they would see a placeholder page.

Before touching anything, a new developer joining this project would need to understand three things. First, the reference scaffold file is a design prototype, not production code — it calls the API directly from the browser and is not imported by the app. The library files under the directory called "lib" are the production-ready versions of that same logic, and they route correctly through the relay. Second, the placeholder page needs to be replaced with a real implementation that calls those library functions, not with a copy of the scaffold. Third, the API key in the environment file is a literal placeholder string and must be replaced with a real key before any AI feature will work.

The project is well-conceived and the hard thinking has been done. The next significant work is building the user interface that connects the ready backend to the user.
