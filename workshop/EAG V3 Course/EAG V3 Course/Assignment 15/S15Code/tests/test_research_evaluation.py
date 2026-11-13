from s15code.research.evaluation import compare


def row(strategy, cost, resolved, calls=1):
    return {"strategy": strategy, "task_id": "t1", "spent": cost, "calls": calls,
            "resolved": resolved, "quality": .9 if resolved else .3,
            "judge_cost": .001, "self_judged": False}


def test_break_even_uses_task_cost_not_call_cost():
    report = compare([row("routed", .02, False, calls=2), row("frontier", .03, True)])
    assert report["strategies"]["routed"]["cost_per_call"] == .01
    assert report["strategies"]["routed"]["cost_per_resolved_task"] is None
    assert abs(report["break_even_resolution_rate"] - 2/3) < 1e-9
    assert report["bad_routing_decisions"][0]["routed_cost"] == .02


def test_unknown_or_self_judged_quality_cannot_become_a_success_metric():
    report = compare([row("routed", .02, None), row("frontier", .03, True)])
    assert report["break_even_resolution_rate"] is None
    assert report["strategies"]["routed"]["resolution_rate"] is None
    sample = row("routed", .02, True)
    sample["self_judged"] = True
    assert compare([sample, row("frontier", .03, True)])["break_even_resolution_rate"] is None
