"""Pure functions: DataFrames in, numbers/tables out. No Excel, no UI."""
import pandas as pd

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_EMPTY_MONTHLY = pd.Series(dtype=float, index=pd.DatetimeIndex([]))


def daily_series(sales: pd.DataFrame) -> pd.Series:
    """One value per calendar day. Pre-filled empty days before the first and
    after the last real sale are trimmed; zero days in between are kept."""
    s = sales.groupby("date")["total"].sum().asfreq("D").fillna(0)
    active = s[s > 0]
    return s.loc[active.index.min():active.index.max()] if not active.empty else s.iloc[0:0]


def series_kpis(s: pd.Series) -> dict:
    """Headline numbers for any daily sales series."""
    if s.empty:
        return {}
    selling = s[s > 0]
    return {
        "start": s.index.min(), "end": s.index.max(), "days": len(s), "selling_days": len(selling),
        "total_sales": float(s.sum()), "avg_per_selling_day": float(selling.mean()),
        "best_day": selling.idxmax(), "best_day_total": float(selling.max()),
    }


def sales_kpis(sales: pd.DataFrame) -> dict:
    """series_kpis plus the cash/card split (needs cash and card columns)."""
    s = daily_series(sales)
    k = series_kpis(s)
    if not k:
        return {}
    k.update(cash=None, card=None, card_share=None)
    if {"cash", "card"} <= set(sales.columns):  # only the built-in template has a cash/card split
        window = sales[sales["date"].between(s.index.min(), s.index.max())]
        card = float(window["card"].sum())
        k.update(cash=float(window["cash"].sum()), card=card,
                 card_share=card / k["total_sales"] if k["total_sales"] else 0.0)
    return k


def weekday_profile(s: pd.Series) -> pd.Series:
    """Average sales per weekday, over days that had sales."""
    selling = s[s > 0]
    return selling.groupby(selling.index.day_name()).mean().reindex(WEEKDAYS).dropna()


def top_items(sales: pd.DataFrame, n: int = 10, by: str = "revenue") -> pd.DataFrame:
    """Best sellers by revenue (or units). Needs an item column; returns an empty table otherwise."""
    if "item" not in sales.columns:
        return pd.DataFrame()
    s = sales.dropna(subset=["item"])
    out = s.groupby("item").agg(revenue=("total", "sum"), sales_rows=("total", "size"))
    if "quantity" in s.columns:
        out["units"] = s.groupby("item")["quantity"].sum()
    return out.sort_values(by if by in out.columns else "revenue", ascending=False).head(n)


def hourly_profile(sales: pd.DataFrame) -> pd.Series:
    """Average sales per day in each hour of the day. Empty if the data has no times."""
    if "hour" not in sales.columns:
        return pd.Series(dtype=float)
    s = sales.dropna(subset=["hour"])
    return (s.groupby("hour")["total"].sum() / max(s["date"].nunique(), 1)).sort_index()


def abc_analysis(sales: pd.DataFrame) -> pd.DataFrame:
    """Items by revenue with class A (the items making the first 80%), B (next 15%) and C (last 5%)."""
    if "item" not in sales.columns:
        return pd.DataFrame()
    rev = sales.dropna(subset=["item"]).groupby("item")["total"].sum().sort_values(ascending=False)
    rev = rev[rev > 0]
    if rev.empty:
        return pd.DataFrame()
    share = rev / rev.sum()
    before = share.cumsum() - share  # share of revenue earned by the items ranked above
    cls = pd.Series("C", index=rev.index).mask(before < 0.95, "B").mask(before < 0.80, "A")
    return pd.DataFrame({"revenue": rev, "share": share, "cum_share": share.cumsum(), "class": cls})


def slow_movers(sales: pd.DataFrame, days: int = 30) -> pd.DataFrame:
    """Items that sold before but not in the last `days` days of the data."""
    s = daily_series(sales)
    if "item" not in sales.columns or s.empty:
        return pd.DataFrame()
    g = sales.dropna(subset=["item"]).groupby("item").agg(last_sold=("date", "max"), revenue=("total", "sum"))
    g["days_since_sale"] = (s.index.max() - g["last_sold"]).dt.days
    return g[g["days_since_sale"] >= days].sort_values("days_since_sale", ascending=False)


def basket_stats(sales: pd.DataFrame) -> dict:
    """Orders, average and median value of one bill/order. Needs an order id column."""
    if "order_id" not in sales.columns:
        return {}
    s = sales.dropna(subset=["order_id"])
    if s.empty:
        return {}
    per_order = s.groupby("order_id")["total"].sum()
    return {"orders": int(len(per_order)), "avg_order_value": float(per_order.mean()),
            "median_order_value": float(per_order.median()),
            "orders_per_day": s.groupby("date")["order_id"].nunique().asfreq("D").fillna(0)}


def growth(s: pd.Series) -> dict:
    """Last 28 days vs the 28 before (or 14 vs 14 when there is less history). Empty under 28 days."""
    for n in (28, 14):
        if len(s) >= 2 * n:
            cur, prev = float(s.tail(n).sum()), float(s.iloc[-2 * n:-n].sum())
            return {"days": n, "current": cur, "previous": prev, "change": (cur - prev) / prev if prev else None}
    return {}


def expense_by_category(expenses: pd.DataFrame) -> pd.Series:
    return expenses.groupby("category")["amount"].sum().sort_values(ascending=False)


def _monthly(df: pd.DataFrame, col: str) -> pd.Series:
    return _EMPTY_MONTHLY if df.empty else df.set_index("date")[col].resample("MS").sum()


def monthly_cash(sales, expenses, purchases, payments, nearby) -> pd.DataFrame:
    """Estimated monthly cash picture. supplier_cash = money actually paid to
    suppliers (at purchase + later payments + nearby-store cash purchases)."""
    supplier_cash = (_monthly(purchases, "paid")
                     .add(_monthly(payments, "amount"), fill_value=0)
                     .add(_monthly(nearby, "amount"), fill_value=0))
    out = pd.concat({
        "sales": daily_series(sales).resample("MS").sum(),
        "expenses": _monthly(expenses, "amount"),
        "supplier_cash": supplier_cash,
    }, axis=1).fillna(0)
    out["net_cash"] = out["sales"] - out["expenses"] - out["supplier_cash"]
    out.index = out.index.strftime("%Y-%m")
    return out


def payables(purchases, payments, nearby) -> dict:
    invoiced = float(purchases["spend"].sum())
    paid_at_purchase = float(purchases["paid"].sum())
    later = float(payments["amount"].sum())
    return {
        "invoiced": invoiced, "paid_at_purchase": paid_at_purchase, "later_payments": later,
        "outstanding": invoiced - paid_at_purchase - later,
        "nearby_cash": float(nearby["amount"].sum()),
    }


def supplier_balances(purchases: pd.DataFrame, payments: pd.DataFrame) -> pd.DataFrame:
    """Per-supplier balance. Names are matched ignoring case/spacing; payments
    whose company never appears in Purchases are flagged, not silently dropped."""
    key = lambda col: col.astype(str).str.strip().str.casefold()  # noqa: E731
    inv = (purchases.assign(key=key(purchases["supplier"]))
           .groupby("key").agg(supplier=("supplier", "first"), invoiced=("spend", "sum"),
                               paid_at_purchase=("paid", "sum")))
    pay = (payments.assign(key=key(payments["company"]))
           .groupby("key").agg(pay_name=("company", "first"), later_payments=("amount", "sum")))
    out = inv.join(pay, how="outer")
    out["supplier"] = out["supplier"].fillna(out["pay_name"])
    out = out.drop(columns="pay_name").fillna({"invoiced": 0, "paid_at_purchase": 0, "later_payments": 0})
    out["balance"] = out["invoiced"] - out["paid_at_purchase"] - out["later_payments"]
    out["check"] = ""
    out.loc[out["balance"] < 0, "check"] = "paid more than invoiced"
    out.loc[out["invoiced"] == 0, "check"] = "payment with no matching invoice supplier"
    return out.reset_index(drop=True).sort_values("balance", ascending=False)
