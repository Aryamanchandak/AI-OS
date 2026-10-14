from consequence_radar.ingest import normalize_batch
from consequence_radar.models import NewsBatch, NewsItem


def test_normalise_assigns_stable_ids_and_removes_tracking_duplicates():
    batch = NewsBatch(items=[NewsItem(url="https://example.com/x?utm_source=a"), NewsItem(url="https://example.com/x")])
    result = normalize_batch(batch)
    assert len(result.items) == 1 and result.items[0].id.startswith("N")
