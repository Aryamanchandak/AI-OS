Assignment
Build a DAG-based agent for a problem of your choice and prove the architecture is intact.

Pass the five base queries (hello, A, I, J, K) from this session. Verbatim, within the iteration and wall-clock bounds named alongside each.

Design one query that requires parallel fan-out. The query must have at least three independent sub-tasks that the Planner correctly emits as concurrent nodes. Verify that the parallel layer's wall-clock is the maximum of the branches, not the sum.

Design one query that requires a Critic verdict. Choose a property the Critic can actually verify with the tools available to it. The Critic must produce both a pass and a fail across two runs of the query, and the fail must successfully splice in a Planner recovery that produces a corrected answer.

Fill in the Coder skill. The current prompts/coder.md is a stub; replace it with a prompt that emits Python suitable for the SandboxExecutor. Demonstrate the Coder on one query where the answer requires computation the Formatter cannot reliably produce from text alone.

Add one new skill to agent_config.yaml. Choose a skill that the existing catalogue does not cover. Write its prompt file. Write one query that exercises it. The orchestrator should not need modification; if it does, the modification is reportable.

Submit YouTube Demo clearly showing 1, 2, 3, 4, and 5 parts of the assignment.

Submit README.md link clearly showing results for 1, 2, 3, 4 and 5 parts of the assignment via logs.

Architectural rules carry over. Skills are yaml entries plus prompts. The Planner emits the graph; the Executor runs it; the Critic sits between a flagged producer and its successor. The recovery classifier must continue to pass its unit tests after any change. Adding a new skill is a yaml edit and a prompt file; touching the Executor for anything but a new generic mechanism is a bug.

