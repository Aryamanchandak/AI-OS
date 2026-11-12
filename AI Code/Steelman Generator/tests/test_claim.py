from steelman.claim import create_claim_card
from steelman.models import ComponentType


def test_claim_card_is_stable_and_splits_components():
    one = create_claim_card(
        "Revenue will rise and management should increase investment",
        "Acme Corp",
        "by 2027",
    )
    two = create_claim_card(
        "Revenue will rise and management should increase investment",
        "Acme Corp",
        "by 2027",
    )
    assert one.claim_hash == two.claim_hash
    assert [component.type for component in one.components] == [
        ComponentType.EMPIRICAL,
        ComponentType.NORMATIVE,
    ]
    assert one.falsifiable is True


def test_unbounded_normative_claim_is_not_falsifiable():
    card = create_claim_card("The company should behave better")
    assert card.falsifiable is False
    assert "measurable" in card.falsifiability_note

