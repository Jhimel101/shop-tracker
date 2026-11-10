import pandas as pd
import pytest

from core import analytics as an
from core import mapping as mp
from core.profiles import PROFILES
from tests import fixtures as fx


def mapped(blob, name, profile="other"):
    df = next(iter(mp.read_tables(blob, name).values()))
    g = mp.guess_columns(df, PROFILES[profile].item_hints)
    out, _ = mp.apply_mapping(df, g)
    return df, g, out


def test_every_profile_is_complete():
    assert set(PROFILES) == {"restaurant", "grocery", "pharmacy", "retail", "online", "other"}
    for p in PROFILES.values():
        assert p.label and p.blurb and p.item_label and p.items_tab and p.basket_label
        assert 7 <= p.default_horizon <= 28 and p.slow_days > 0
        assert all(k in {"hourly", "basket", "abc", "slow"} for k in p.panels)
        assert bool(p.focus_tab) == bool(p.panels)


def test_business_type_changes_which_column_is_the_item():
    df = next(iter(mp.read_tables(fx.pharmacy_csv(), "p.csv").values()))
    assert mp.guess_columns(df).item == "Customer Name"  # without a type, "name" wins
    assert mp.guess_columns(df, PROFILES["pharmacy"].item_hints).item == "Medicine Name"


def test_restaurant_gets_hours_and_bills():
    _, g, out = mapped(fx.restaurant_csv(), "r.csv", "restaurant")
    assert g.order_id == "Bill No" and "hour" in out.columns
    hours = an.hourly_profile(out)
    assert set(hours.index) <= set(range(24)) and hours.idxmax() in (12, 13, 19, 20, 21)
    b = an.basket_stats(out)
    assert b["orders"] == out["order_id"].nunique()
    assert b["avg_order_value"] == pytest.approx(out["total"].sum() / b["orders"])


def test_no_hour_column_when_dates_have_no_times():
    _, _, out = mapped(fx.pharmacy_csv(), "p.csv", "pharmacy")
    assert "hour" not in out.columns and an.hourly_profile(out).empty


def test_pharmacy_abc_and_slow_movers():
    _, _, out = mapped(fx.pharmacy_csv(), "p.csv", "pharmacy")
    abc = an.abc_analysis(out)
    assert abc["share"].sum() == pytest.approx(1.0) and abc["cum_share"].iloc[-1] == pytest.approx(1.0)
    assert abc["class"].iloc[0] == "A" and abc["class"].is_monotonic_increasing
    a_share = abc.loc[abc["class"] == "A", "share"].sum()
    assert a_share >= 0.8 and abc.loc[abc["class"] == "A", "share"].iloc[:-1].sum() < 0.8  # smallest set reaching 80%
    slow = an.slow_movers(out, 30)
    assert {"Medicine R", "Medicine S", "Medicine T"} <= set(slow.index)  # stopped selling after day 30
    assert not {"Medicine A", "Medicine B", "Medicine C"} & set(slow.index)  # best sellers are never flagged
    assert (slow["days_since_sale"] >= 30).all()
    assert an.slow_movers(out, 400).empty


def test_growth_windows():
    s = pd.Series(range(100), index=pd.date_range("2026-01-01", periods=100), dtype=float)
    g = an.growth(s)
    assert g["days"] == 28 and g["current"] > g["previous"] and g["change"] > 0
    assert an.growth(s.head(40))["days"] == 14 and an.growth(s.head(20)) == {}


def test_basket_stats_and_abc_need_their_columns():
    plain = pd.DataFrame({"date": pd.date_range("2026-01-01", periods=3), "total": [1.0, 2.0, 3.0]})
    assert an.basket_stats(plain) == {} and an.abc_analysis(plain).empty and an.slow_movers(plain).empty


def test_timezone_offset_does_not_move_a_late_sale_to_another_day():
    ser = pd.Series(["2026-03-01 23:30:00 +0300", "2026-03-01T23:45:00Z", "01-03-2026"])
    out = mp.parse_dates(ser, "day_first")
    assert (out == pd.Timestamp("2026-03-01")).all()  # and the year in 01-03-2026 is not mistaken for an offset
    assert mp.parse_timestamps(ser.iloc[:1]).iloc[0].hour == 23
