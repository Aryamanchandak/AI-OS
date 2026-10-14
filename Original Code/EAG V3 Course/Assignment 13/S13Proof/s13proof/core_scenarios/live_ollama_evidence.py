"""One live, local proof that retrieved evidence becomes a grounded answer.

Not a unit test: it calls the Ollama model already running on the developer's
machine.  The deterministic acceptance replay proves the architecture; this
prints the actual model response a human can inspect.
"""
from __future__ import annotations

import json
from urllib.request import Request, urlopen

from S13Core.proofs.scenarios import semantic_document_prompt


def main() -> None:
    proof = semantic_document_prompt()
    question = proof["prompt"]
    evidence = proof["semantic_answer_evidence"]
    prompt = f"""Answer the user's question using only the evidence below.
If the evidence is insufficient, say so. Give one concise sentence and cite
the source as [gateway-capacity.md].

User question: {question}

Evidence from gateway-capacity.md:
{evidence}
"""
    body = json.dumps({
        "model": "phi4:latest", "stream": False,
        "messages": [{"role": "user", "content": prompt}],
        "options": {"temperature": 0},
    }).encode()
    request = Request("http://127.0.0.1:11434/api/chat", data=body,
                      headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=180) as response:  # local Ollama only
        answer = json.loads(response.read())["message"]["content"].strip()
    print("USER PROMPT:", question)
    print("RETRIEVED EVIDENCE:", evidence)
    print("MODEL ANSWER:", answer)


if __name__ == "__main__":
    main()
