

# Understanding GPT-5’s New Parameters (Setting a Foundation)

Before we dive into prompt construction, you need to understand GPT-5’s new levers of control. Each one affects the final output in important ways.

Press enter or click to view image in full size

# Reasoning Effort

GPT-5 introduces a reasoning_effort parameter (minimal, low, medium, high) that controls how hard the model thinks before responding. The default is medium, but I've found this needs adjusting based on task complexity.

Press enter or click to view image in full size

# Verbosity Control

There’s now a verbosity parameter separate from reasoning effort. Low verbosity gives you concise outputs, while high verbosity provides detailed explanations. You can override this globally with natural language instructions in your prompt.

I often set global verbosity to low, then specify in my prompt: “For code sections only, provide detailed explanations and comments.”

# If you’re new to prompting GPT-5, here’s my basic framework that prevents most common mistakes.

# 1. The Three-Part Structure of a Prompt

Every effective prompt should have:

Here’s a simple template.

# 2. Be Embarrassingly Specific

GPT-5’s precision means vague instructions lead to unpredictable results. Instead of “make this better,” try:

# 3. Use the Escape Hatch

Always give the model a way out when it encounters uncertainty. Add phrases like:

# Advanced Techniques for the Prompt Veterans

Once you’ve mastered the basics, here are the advanced strategies I’ve discovered through trial and error:

# 1. Agentic Eagerness Control

GPT-5 is naturally thorough. Sometimes too thorough. You can calibrate its “agentic eagerness” (how proactive vs. cautious it should be) with specific instructions.

Join Medium for free to get updates from this writer.

Subscribe

For less eagerness (faster results).

For more eagerness (thorough results).

# 2. Tool Preambles for Complex Tasks

When GPT-5 is working on multi-step tasks, use tool preambles to keep users informed:

# 3. The Meta-Prompting Technique

Here’s something I discovered recently: GPT-5 is excellent at improving its own prompts. I use this template when a prompt isn’t working:

This has saved me hours of prompt iteration.

# Templates for Common Use Cases

Based on OpenAI’s guide and my own experiments, here are templates that consistently work well:

# For Coding Tasks

# For Analysis Tasks

# For Creative Tasks

# Common Mistakes (That I’ve Definitely Never Made)

# 1. Contradictory Instructions

GPT-5 will try to satisfy conflicting requirements, wasting reasoning tokens. I once asked for “brief but comprehensive” analysis and got a response that was somehow both rushed and exhaustive.

Fix: Review your prompt for contradictions before running it.

# 2. Overloading with Context

More context isn’t always better. I’ve learned that GPT-5 can get lost in too much background information.

Fix: Include only context that directly affects the output.

# 3. Forgetting the Reasoning Budget

Complex prompts on minimal reasoning effort often fail. It’s like asking someone to write a thesis while half-asleep.

Fix: Match reasoning effort to task complexity.





ALSO Important for the structure of the prompt



