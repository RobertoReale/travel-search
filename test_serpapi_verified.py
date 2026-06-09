"""Unit tests for the pure helpers in serpapi_verified.py.

Run:  python -m pytest test_serpapi_verified.py -q
These cover the parsing/ranking/tax/link logic the article's numbers depend on.
No network calls — `call()` and `link_ok()` are intentionally not exercised here.
"""
import serpapi_verified as sv


def test_rate_fields_extracts_shown_and_before_tax():
    block = {
        "total_rate": {
            "lowest": "$643",
            "extracted_lowest": 643,
            "before_taxes_fees": "$590",
            "extracted_before_taxes_fees": 590,
        }
    }
    f = sv.rate_fields(block, "total_rate")
    assert f["shown_num"] == 643
    assert f["before_tax_num"] == 590
    assert f["shown"] == "$643"


def test_rate_fields_missing_key_is_safe():
    f = sv.rate_fields({}, "total_rate")
    assert f == {"shown": None, "shown_num": None, "before_tax": None, "before_tax_num": None}


def test_is_bookable_link_drops_vacation_rental_redirect():
    assert sv.is_bookable_link("https://www.google.com/aclk?sa=l&ai=xyz") is True
    assert sv.is_bookable_link("https://www.google.com/travel/clk?pc=abc") is False
    assert sv.is_bookable_link(None) is False
    assert sv.is_bookable_link("") is False


def test_tax_status_inclusive_when_total_exceeds_before_tax():
    status, note = sv.tax_status(643, 590)
    assert status == "ok"
    assert "incl" in note


def test_tax_status_warns_when_total_equals_before_tax():
    status, _ = sv.tax_status(600, 600)
    assert status == "warn"


def test_tax_status_na_when_breakdown_missing():
    assert sv.tax_status(None, None)[0] == "na"
    assert sv.tax_status(600, None)[0] == "na"


def test_nights_between_counts_calendar_nights():
    assert sv.nights_between("2026-07-30", "2026-08-04") == 5
    assert sv.nights_between("2026-07-30", "2026-07-31") == 1


def test_nights_between_never_below_one():
    # same day, or unparseable input, both clamp to 1 night
    assert sv.nights_between("2026-07-30", "2026-07-30") == 1
    assert sv.nights_between("garbage", "2026-08-04") == 1


def test_booking_search_link_is_a_stable_booking_url():
    link = sv.booking_search_link("Hotel Da Maria", "2026-07-30", "2026-08-04", "2")
    assert link.startswith("https://www.booking.com/searchresults.html?")
    assert "checkin=2026-07-30" in link
    assert "checkout=2026-08-04" in link
    assert "travel/clk" not in link  # never an ephemeral redirect


def test_cache_path_ignores_api_key_but_varies_on_query():
    a = sv._cache_path({"q": "Ischia", "api_key": "SECRET1"})
    b = sv._cache_path({"q": "Ischia", "api_key": "SECRET2"})
    c = sv._cache_path({"q": "Barcelona", "api_key": "SECRET1"})
    assert a == b          # secret key must not change the cache key
    assert a != c          # different query -> different cache entry
    assert "SECRET1" not in a
