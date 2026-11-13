"""The agent loop: ask the model for one action, run it, show it the result.

Every model call becomes one event, whether or not the reply was usable.
"""
import json


def run_agent(model, workspace, system_prompt, task_prompt, max_model_calls):
    """Return (events, finish, stop_reason).

    finish is {"status", "message"} if the agent ended the run itself, else None.
    stop_reason is "finish", "step_budget" or "model_error".
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "TASK: " + task_prompt},
    ]
    events = []
    for step in range(1, max_model_calls + 1):
        reply = model.chat(messages)
        event = {"step": step, "model": reply, "action": None, "result": None}
        events.append(event)
        if not reply["ok"]:
            return events, None, "model_error"

        action = _parse(reply["text"])
        event["action"] = action
        messages.append({"role": "assistant", "content": reply["text"]})
        if action is None:
            messages.append({"role": "user", "content": "RESULT: could not read that. Reply with exactly one JSON object with a \"tool\" field."})
            continue
        if action["tool"] == "finish":
            finish = {"status": str(action.get("status")), "message": str(action.get("message", ""))}
            return events, finish, "finish"

        event["result"] = workspace.call(action)
        left = max_model_calls - step
        messages.append({"role": "user", "content": f"RESULT ({left} turns left):\n{event['result']['output']}"})
    return events, None, "step_budget"


def _parse(text):
    try:
        action = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(action, dict) and isinstance(action.get("tool"), str):
        return action
    return None
