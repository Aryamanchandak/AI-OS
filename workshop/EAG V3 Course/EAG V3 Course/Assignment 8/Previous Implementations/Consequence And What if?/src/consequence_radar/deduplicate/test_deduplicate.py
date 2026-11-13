from consequence_radar.deduplicate import deduplicate
from consequence_radar.models import DiscoveryExtract


def test_dedup_only_groups_same_development():
    values = [
        DiscoveryExtract(item_id="1", canonical_url="https://a.com", headline="India cuts solar import tariff", text="India announced a solar import tariff cut"),
        DiscoveryExtract(item_id="2", canonical_url="https://b.com", headline="Solar import tariff cut announced by India", text="India announced a solar import tariff cut"),
        DiscoveryExtract(item_id="3", canonical_url="https://c.com", headline="Monsoon rainfall rises", text="Rainfall is above normal"),
    ]
    groups = deduplicate(values, threshold=.35)
    assert sorted(len(g.member_item_ids) for g in groups) == [1, 2]
