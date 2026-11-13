from __future__ import annotations

from decimal import Decimal, localcontext

from ..models import Estimate


class EstimateError(ValueError): pass


def multiply_range(*, estimate_id: str, metric: str, left: Estimate, right: Estimate, unit: str, period: str | None = None, currency: str | None = None, caveat: str, assumptions: list[str] | None = None) -> Estimate:
    if left.low is None or left.high is None or right.low is None or right.high is None:
        raise EstimateError("range multiplication requires low and high inputs")
    with localcontext() as ctx:
        ctx.prec = 28
        products = [left.low * right.low, left.low * right.high, left.high * right.low, left.high * right.high]
        low, high = min(products), max(products)
        central = (left.central * right.central) if left.central is not None and right.central is not None else (low + high) / Decimal(2)
        # An input whose central sits outside its own low/high pushes the
        # product outside the range just derived from that same pair, producing
        # a range whose central is not inside it. Keep the result coherent.
        central = min(max(central, low), high)
    return Estimate(id=estimate_id, metric=metric, estimate_type="derived_range", low=low, central=central, high=high, unit=unit, period=period, currency=currency, formula=f"{left.id} * {right.id}", input_estimate_ids=[left.id, right.id], assumptions=assumptions or [], caveat=caveat)


def convert_currency(source: Estimate, *, estimate_id: str, fx: Estimate, target_currency: str) -> Estimate:
    # multiply_range works off low/high, so guarding on fx.central let an FX rate
    # with only a central value through to a misleading "range multiplication"
    # error instead of naming the field that is actually missing.
    if source.currency is None or fx.low is None or fx.high is None:
        raise EstimateError("currency conversion requires a source currency and an FX low/high range")
    converted = multiply_range(estimate_id=estimate_id, metric=source.metric, left=source, right=fx, unit=source.unit or "", period=source.period, currency=target_currency, caveat=f"Converted from {source.currency} using {fx.id}; original preserved separately")
    return converted


def sensitivity(base: Estimate, coefficient: Estimate, change: Decimal = Decimal("0.10")) -> dict[str, Decimal]:
    if coefficient.central is None or base.central is None: raise EstimateError("sensitivity requires central values")
    return {"lower_input": base.central * coefficient.central * (Decimal(1) - change), "central": base.central * coefficient.central, "higher_input": base.central * coefficient.central * (Decimal(1) + change)}
