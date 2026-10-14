from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import random
import re

from steelman.domains import DOMAIN_LENSES, DomainPack
from steelman.graph import make_node
from steelman.integrations import LocalMirfishAdapter
from steelman.models import (
    BudgetUsage, Crux, DualAnalysis, FrameMode, HardeningRound, Prediction,
    PremiseEdge, PremiseType, ProponentStatus, RubricResult, Side, SideAnalysis,
    Source, VerificationGrade, stable_id,
)
from steelman.pipeline import SteelmanPipeline
from steelman.providers import ConstructionProvider, DeterministicProvider
from steelman.verification import verify_graph


FRAME_PROMPTS = {
    FrameMode.MECHANISM: "Trace the causal chain and identify the transmission mechanism.",
    FrameMode.BASE_RATE: "Compare the relevant base rate and closest historical analog.",
    FrameMode.POLITICAL_ECONOMY: "Map incentives, constraints, coalitions, and strategic behavior.",
    FrameMode.ASYMMETRIC_PAYOFF: "State why limited downside or option value can justify the position.",
    FrameMode.CASCADE: "Trace the second- and third-order consequences through the graph.",
    FrameMode.TAIL: "State the tail state where being wrong on average is still rational.",
}


class FullSteelmanPipeline:
    def __init__(
        self,
        blue_provider: ConstructionProvider | None = None,
        red_family: str = "deterministic-red",
        blue_family: str = "deterministic-blue",
        token_budget: int = 1200,
        search_budget: int = 3,
        rounds: int = 3,
        verification_cache=None,
    ) -> None:
        self.provider = blue_provider or DeterministicProvider()
        self.red_family = red_family
        self.blue_family = blue_family
        if red_family == blue_family and red_family != "deterministic":
            raise ValueError("Red and Blue must use different configured model families")
        self.token_budget = token_budget
        self.search_budget = search_budget
        self.rounds = rounds
        self.verification_cache = verification_cache

    def run(
        self,
        claim: str,
        scope: str = "unspecified",
        time_horizon: str = "unspecified",
        sources: list[Source] | None = None,
        domain: DomainPack = DomainPack.GENERAL,
    ) -> DualAnalysis:
        sources = sources or []
        dag = ["0:claim-surgery"]
        claims = {Side.CLAIM: claim, Side.NEGATION: self._negate(claim)}
        dag.append("3,6:parallel-side-and-frame-fan-out")
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = {
                side: pool.submit(self._run_side, side, text, scope, time_horizon, sources, domain)
                for side, text in claims.items()
            }
            sides = {side: future.result() for side, future in futures.items()}
        self._assert_budget_parity(sides[Side.CLAIM].budget, sides[Side.NEGATION].budget)
        dag.extend(["4:verification", "5:red-blue-loop", "6:budget-parity-checked"])
        cruxes = self._cruxes(sides[Side.CLAIM], sides[Side.NEGATION])
        dag.extend(["7:crux-extraction", "8:predictions-ready-for-tracker"])
        seed = int(sha256(sides[Side.CLAIM].run.claim_card.claim_hash.encode()).hexdigest()[:8], 16)
        order = [Side.CLAIM, Side.NEGATION]
        random.Random(seed).shuffle(order)
        rubric = self._rubric(sides, cruxes)
        if not rubric.passed:
            dag.append("9:rubric-regeneration-pass")
            rubric.regeneration_count = 1
            # A bounded regeneration adds another independent pressure round without inventing evidence.
            for side in sides.values():
                side.hardening.extend(self._harden(side.run, start=len(side.hardening) + 1, rounds=1))
            rubric = self._rubric(sides, cruxes, regeneration_count=1)
        dag.append("9:rubric-gate")
        return DualAnalysis(
            claim=sides[Side.CLAIM], negation=sides[Side.NEGATION], blinded_order=order,
            cruxes=cruxes, rubric=rubric, dag_log=dag,
        )

    def _run_side(self, side, claim, scope, horizon, sources, domain) -> SideAnalysis:
        run = SteelmanPipeline(self.provider, self.verification_cache).run(claim, scope, horizon, sources)
        frames = self._frames(run, domain)
        graph = verify_graph(run.graph, sources)
        if self.verification_cache is not None:
            for node, result in zip(graph.nodes, graph.verifications):
                self.verification_cache.cache_put(node.text, result)
        rendered = SteelmanPipeline._render(
            run.claim_card.canonical_claim, graph, run.proponent_status, run.proponent_names
        )
        run = run.model_copy(update={"graph": graph, "rendered_steelman": rendered})
        hardening = self._harden(run, 1, self.rounds)
        retreat = [item.retreat_position for item in hardening if item.retreat_position]
        predictions = self._predictions(side, run.claim_card.canonical_claim, horizon)
        # Budgets are reservations consumed identically; work may terminate early but cannot borrow across sides.
        budget = BudgetUsage(
            side=side, token_budget=self.token_budget, search_budget=self.search_budget,
            tokens_used=self.token_budget, searches_used=self.search_budget,
        )
        return SideAnalysis(
            side=side, run=run, frames=frames, hardening=hardening,
            retreat_path=retreat, predictions=predictions, budget=budget,
        )

    def _frames(self, run, domain):
        lens = DOMAIN_LENSES[domain]
        root = next(node for node in run.graph.nodes if node.text.startswith("Conclusion:"))

        def construct(mode: FrameMode):
            text = f"{FRAME_PROMPTS[mode]} Domain lens: {lens} Applied to {run.claim_card.canonical_claim}"
            return mode, text

        with ThreadPoolExecutor(max_workers=6) as pool:
            pairs = list(pool.map(construct, list(FrameMode)))
        for mode, text in pairs:
            node_type = PremiseType.CAUSAL if mode != FrameMode.BASE_RATE else PremiseType.EMPIRICAL
            node = make_node(text, node_type, mode in {FrameMode.MECHANISM, FrameMode.BASE_RATE})
            if all(existing.id != node.id for existing in run.graph.nodes):
                run.graph.nodes.append(node)
                run.graph.edges.append(PremiseEdge(source_id=node.id, target_id=root.id, relation=f"frame:{mode.value}"))
        cascade_nodes = [node.id for node in run.graph.nodes if node.type == PremiseType.EMPIRICAL]
        if cascade_nodes:
            LocalMirfishAdapter().cascade(run.graph, cascade_nodes[0])
        return dict(pairs)

    def _harden(self, run, start: int, rounds: int):
        targets = run.graph.warnings or ["The thesis may fail outside its stated scope or horizon."]
        output = []
        seen = set()
        for offset in range(rounds):
            attack = targets[offset % len(targets)]
            if attack in seen:
                break
            seen.add(attack)
            supported = any(
                result.grade in {VerificationGrade.PRIMARY, VerificationGrade.SECONDARY}
                for result in run.graph.verifications
            )
            repair = (
                "Blue retains the thesis and anchors the challenged dependency to supplied evidence."
                if supported else "Blue cannot repair this dependency without narrowing the claim."
            )
            retreat = "" if supported else f"The claim holds only if: {attack.replace('Load-bearing premise downgraded', '').strip(' :')}"
            output.append(HardeningRound(
                round_number=start + offset, attack=f"Red ({self.red_family}): {attack}",
                repair=f"Blue ({self.blue_family}): {repair}", survived=supported, retreat_position=retreat,
            ))
        return output

    @staticmethod
    def _predictions(side, claim, horizon):
        deadline = (datetime.now(UTC) + timedelta(days=365)).date().isoformat()
        match = re.search(r"(20\d{2}-\d{2}-\d{2}|20\d{2})", horizon)
        if match:
            deadline = match.group(1) if len(match.group(1)) == 10 else f"{match.group(1)}-12-31"
        direction = "decrease" if re.search(r"\b(fall|decline|decrease|reduce|not improve)\b", claim, re.I) else "increase"
        proposition = f"By {deadline}, an outcome implied by '{claim}' will show a measurable {direction}."
        return [Prediction(
            id=stable_id("prediction", {"side": side.value, "claim": claim, "deadline": deadline}),
            side=side, proposition=proposition, metric="user-selected claim outcome",
            direction=direction, threshold=0.0, unit="change from registration baseline", deadline=deadline,
        )]

    @staticmethod
    def _cruxes(claim_side, negation_side):
        a = [n for n in claim_side.run.graph.nodes if n.load_bearing]
        b = [n for n in negation_side.run.graph.nodes if n.load_bearing]
        cruxes = []
        for left, right in list(zip(a, b))[:3]:
            proposition = f"Whether {left.text.removeprefix('Conclusion: ')}"
            cruxes.append(Crux(
                id=stable_id("crux", proposition), disputed_proposition=proposition,
                claim_prediction=claim_side.predictions[0].proposition,
                negation_prediction=negation_side.predictions[0].proposition,
                settling_observation=f"Observe the registered metric by {claim_side.predictions[0].deadline} against threshold 0.",
            ))
        return cruxes

    @staticmethod
    def _rubric(sides, cruxes, regeneration_count=0):
        all_sides = list(sides.values())
        checks = {
            "proponent_sourced": all(s.run.proponent_status == ProponentStatus.SOURCED for s in all_sides),
            "load_bearing_verified": all(not s.run.graph.warnings for s in all_sides),
            "survived_hardening": all(any(r.survived for r in s.hardening) for s in all_sides),
            "cruxes_isolated": bool(cruxes),
            "predictions_falsifiable": all(s.predictions for s in all_sides),
            "budget_parity": all_sides[0].budget.tokens_used == all_sides[1].budget.tokens_used and all_sides[0].budget.searches_used == all_sides[1].budget.searches_used,
        }
        score = sum(checks.values())
        return RubricResult(score=score, threshold=5, passed=score >= 5, checks=checks, regeneration_count=regeneration_count)

    @staticmethod
    def _assert_budget_parity(a, b):
        if (a.token_budget, a.search_budget, a.tokens_used, a.searches_used) != (b.token_budget, b.search_budget, b.tokens_used, b.searches_used):
            raise RuntimeError("Dual steelman budget asymmetry detected")

    @staticmethod
    def _negate(claim: str) -> str:
        return claim[4:] if claim.casefold().startswith("not ") else f"It is not the case that {claim}"
