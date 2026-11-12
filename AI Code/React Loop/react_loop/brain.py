"""Component 1 — the brain interface (Phase 0).

One method: ``think(messages) -> str``. The brain is the *reasoning* seam and
nothing else. It receives the running message list and returns the model's raw
text reply. It does NOT parse, does NOT call tools, does NOT loop — that is the
loop controller's job. Swapping brains = writing a new class with this method.

Messages are OpenAI chat-completions dicts: ``{"role": ..., "content": ...}``.
"""

from __future__ import annotations

import logging
from time import perf_counter
# Protocol lets us describe a "shape" (a required method) without forcing classes
# to inherit from it. Sequence is a read-only list-like type used for the messages.
from typing import Protocol, Sequence

# A module-level logger, named after this module ("react_loop.brain"), so log
# lines can be traced back to where they came from.
logger = logging.getLogger(__name__)

# A type alias: a "Message" is just a dict with string keys and string values,
# e.g. {"role": "user", "content": "hello"}. Writing `Message` instead of
# `dict[str, str]` everywhere makes the intent clearer.
Message = dict[str, str]


class Brain(Protocol):
    """The reasoning seam. The only thing the loop depends on.

    This is a Protocol, NOT a normal base class. It defines a contract: "anything
    that has a `think(messages) -> str` method is a Brain." Classes do NOT need to
    inherit from it — OpenAIBrain and FakeBrain below both count as a Brain simply
    because they have a matching `think` method (this is called "duck typing":
    if it walks and quacks like a Brain, it IS a Brain).

    Why bother? So the loop can be written against `Brain` and accept EITHER the
    real OpenAI-backed brain OR the fake scripted brain, with no code change. The
    Protocol is only used by type-checkers and as documentation; at runtime it
    does nothing at all.
    """

    def think(self, messages: Sequence[Message]) -> str:
        """Given the conversation so far, return the model's raw text reply.

        This is the whole contract — one method. Take the list of messages, return
        a string. The `...` below is a literal ellipsis meaning "no body": a
        Protocol only declares the method's shape; the actual work is done by the
        concrete classes (OpenAIBrain / FakeBrain) that implement it.
        """
        ...  # placeholder body — Protocols never contain real logic


class OpenAIBrain:
    """Calls OpenAI chat-completions and returns the raw assistant text.

    Deliberately thin: no ``tools`` param, no function-calling, no streaming.
    The model reads tools as text (rendered into the system prompt) and replies
    with text. Temperature defaults to 0 so decisions are as reproducible as the
    API allows — this is a control loop, not creative writing.
    """

    def __init__(
        self,
        model: str,               # which OpenAI model to call, e.g. "gpt-4o-mini"
        api_key: str | None = None,  # optional key; None means "read from env"
        temperature: float = 0.0,    # 0 = most deterministic/repeatable output
    ) -> None:
        # Imported lazily (inside __init__, not at the top of the file) so the
        # rest of the package (and the tests, which use FakeBrain) can import this
        # module even if the `openai` SDK isn't installed.
        from openai import OpenAI

        # Stash the settings on the instance (`self.`) so `think` can read them later.
        self.model = model
        self.temperature = temperature
        # Build the API client. If an api_key was passed, use it; otherwise call
        # OpenAI() with no args and let the SDK find the key in the environment.
        # (The `A if cond else B` form is Python's one-line "ternary" if/else.)
        self._client = OpenAI(api_key=api_key) if api_key else OpenAI()

    def think(self, messages: Sequence[Message]) -> str:
        logger.debug("brain think: model=%s messages=%d", self.model, len(messages))
        started = perf_counter()  # wall-clock timer for the debug latency line
        try:
            # A single, plain chat-completion. `list(messages)` copies the seq
            # into the mutable list the SDK expects (callers may pass any Sequence).
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=list(messages),
                temperature=self.temperature,
            )
        except Exception:
            # Log with traceback, then re-raise: the brain doesn't decide policy
            # on API failure — that's the loop's call — it just surfaces it.
            logger.exception("brain think failed: model=%s", self.model)
            raise
        # Defensive `or ""`: the API can return None content (e.g. on a refusal),
        # and the parser downstream expects a string, never None.
        content = resp.choices[0].message.content or ""
        logger.debug(
            "brain reply: model=%s in %.0fms (%d chars)",
            self.model, (perf_counter() - started) * 1000, len(content),
        )
        return content


class FakeBrain:
    """A scripted brain for tests and offline demos (no API key needed).

    Hand it a list of canned replies; each ``think`` call returns the next one.
    This is how Phase 2 tests the parser "with fake tool results" and how the
    whole loop's mechanics are verified end-to-end without touching OpenAI.
    """

    def __init__(self, replies: Sequence[str]) -> None:
        # The canned answers to hand back, in order. `list(...)` copies them so
        # the caller can't mutate our internal state after construction.
        self._replies = list(replies)
        # A cursor: index of the NEXT reply to return. Starts at the first one (0).
        self._i = 0
        # A log of every `messages` list the loop passed to us. Tests read this to
        # assert "the loop sent the brain what we expected." Starts empty.
        self.calls: list[list[Message]] = []

    def think(self, messages: Sequence[Message]) -> str:
        # Record what the loop actually sent us — useful for assertions.
        self.calls.append(list(messages))
        # If the cursor has run past the end, the test scripted too few replies.
        # Fail loudly (AssertionError) rather than returning garbage.
        if self._i >= len(self._replies):
            raise AssertionError(
                "FakeBrain ran out of scripted replies "
                f"(asked {self._i + 1} times, only {len(self._replies)} scripted)"
            )
        # Grab the reply the cursor points at...
        reply = self._replies[self._i]
        # ...advance the cursor so the NEXT call returns the NEXT reply...
        self._i += 1
        # ...and hand this one back. Same signature as OpenAIBrain.think, which is
        # exactly why the loop accepts either class (that's the Protocol at work).
        return reply
