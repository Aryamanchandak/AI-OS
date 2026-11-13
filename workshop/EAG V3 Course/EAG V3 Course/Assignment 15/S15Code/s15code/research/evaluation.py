"""Compare resolved-task economics without treating missing verdicts as successes."""
from statistics import mean


def compare(rows: list[dict]) -> dict:
    summaries = {}
    for strategy in ("routed", "frontier"):
        group = [row for row in rows if row["strategy"] == strategy]
        spent = sum(row["spent"] for row in group)
        calls = sum(row["calls"] for row in group)
        valid = bool(group) and all(isinstance(row["resolved"], bool) and not row["self_judged"]
                                    and row.get("baseline_valid", True) for row in group)
        resolved = sum(row["resolved"] is True for row in group) if valid else None
        summaries[strategy] = {
            "tasks": len(group), "calls": calls, "spent": spent,
            "cost_per_call": spent / calls if calls else None,
            "cost_per_task": spent / len(group) if group else None,
            "resolved": resolved, "resolution_rate": resolved / len(group) if valid else None,
            "cost_per_resolved_task": spent / resolved if resolved else None,
            "mean_quality": mean(r["quality"] for r in group if r["quality"] is not None) if valid else None,
            "judge_cost": sum(row["judge_cost"] for row in group), "valid_quality": valid,
        }
    routed, frontier = summaries["routed"], summaries["frontier"]
    paired = {r["task_id"] for r in rows if r["strategy"] == "routed"} == {
        r["task_id"] for r in rows if r["strategy"] == "frontier"}
    valid = paired and routed["valid_quality"] and frontier["valid_quality"]
    break_even = (frontier["resolution_rate"] * routed["cost_per_task"] / frontier["cost_per_task"]
                  if valid and frontier["cost_per_task"] else None)
    baseline = {r["task_id"]: r for r in rows if r["strategy"] == "frontier"}
    wrong = [{"task_id": r["task_id"], "routed_cost": r["spent"],
              "frontier_cost": baseline[r["task_id"]]["spent"]}
             for r in rows if r["strategy"] == "routed" and r["resolved"] is False
             and baseline.get(r["task_id"], {}).get("resolved") is True]
    return {"strategies": summaries, "break_even_resolution_rate": break_even,
            "break_even_formula": "frontier_resolution_rate * routed_cost_per_task / frontier_cost_per_task",
            "bad_routing_decisions": wrong,
            "finding": ("No routed failure against a resolved frontier answer was observed."
                        if valid and not wrong else "Quality evidence incomplete." if not valid else
                        "Inspect the recorded routed failures and their costs."),
            "judge_cost_excluded_from_workload_metrics": True}
