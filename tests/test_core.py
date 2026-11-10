import numpy as np
import pandas as pd
import pytest

from core import analytics as an
from core.forecast import forecast


def make_sales(days=60, pad=3):
    idx = pd.date_range("2026-01-01", periods=days)
    total = np.array([800 + 300 * (d.dayofweek in (4, 5)) for d in idx], dtype=float)
    df = pd.DataFrame({"date": idx, "cash": total / 2, "card": total / 2})
    df["total"] = df["cash"] + df["card"]
    pad_rows = pd.DataFrame({"date": pd.date_range(idx[-1] + pd.Timedelta(days=1), periods=pad),
                             "cash": 0.0, "card": 0.0, "total": 0.0})
    return pd.concat([df, pad_rows], ignore_index=True)


def test_daily_series_trims_trailing_empty_days():
    s = an.daily_series(make_sales(days=60, pad=3))
    assert len(s) == 60 and s.iloc[-1] > 0


def test_forecast_length_and_nonnegative():
    s = an.daily_series(make_sales())
    r = forecast(s, 14)
    assert len(r["forecast"]) == 14 and (r["forecast"] >= 0).all()
    assert r["forecast"].index[0] == s.index[-1] + pd.Timedelta(days=1)


def test_forecast_refuses_short_history():
    with pytest.raises(ValueError):
        forecast(an.daily_series(make_sales(days=10, pad=0)), 7)


def test_supplier_balance_math_and_unmatched_flag():
    purchases = pd.DataFrame({"supplier": ["ACME", "acme ", "Beta"], "spend": [100.0, 50.0, 80.0],
                              "paid": [20.0, 0.0, 80.0]})
    payments = pd.DataFrame({"company": ["Acme", "Gamma"], "amount": [30.0, 10.0]})
    out = an.supplier_balances(purchases, payments).set_index("supplier")
    assert out.loc["ACME", "balance"] == 100 + 50 - 20 - 30
    assert out.loc["Beta", "balance"] == 0
    assert "no matching" in out.loc["Gamma", "check"]
