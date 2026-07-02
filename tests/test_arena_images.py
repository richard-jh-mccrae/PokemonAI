"""Arena card images: pool id -> official scan URL; the one-time local fetch.

Offline — the URL builder is pure (EN_Card_Data set/number), and fetch_all is
tested with an injected fetcher. The real download is a manual ops step.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from arena import images  # noqa: E402
from deck_convert import _indexes  # noqa: E402

req = pytest.mark.req("REQ-ARENA-0009")

BY_NORM = _indexes()[0]


@req
def test_image_url_uses_the_pool_printing():
    ultra = BY_NORM["ultra ball"][0]                     # pool print: SVI 196
    url = images.image_url(ultra)
    assert url.endswith("/SVI/SVI_196_R_EN_SM.png")


@req
def test_promo_cards_remap_to_svp():
    url = images.image_url(21)                           # Scrafty PROMO 188
    assert "/SVP/SVP_188_" in url


@req
def test_blank_set_cards_have_no_image():
    assert images.image_url(916) is None                 # Scyther, set unknown


@req
def test_fetch_all_skips_existing_and_reports_missing(tmp_path):
    calls = []

    def fake_fetcher(url):
        calls.append(url)
        return b"png-bytes"

    first = images.fetch_all(tmp_path, ids=[21, 916, BY_NORM["ultra ball"][0]],
                             fetcher=fake_fetcher)
    assert first["fetched"] == 2                         # 916 has no URL
    assert first["missing"] == [916]
    assert (tmp_path / "21.png").read_bytes() == b"png-bytes"

    again = images.fetch_all(tmp_path, ids=[21], fetcher=fake_fetcher)
    assert again["fetched"] == 0 and again["skipped"] == 1
    assert len(calls) == 2                               # never re-downloaded
