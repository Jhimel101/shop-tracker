"""Template-based plain-English summaries (no LLM, no network)."""


def money(x: float, cur: str = "") -> str:
    return f"{x:,.0f} {cur}".strip()


def forecast_summary(history, result, cur: str = "") -> str:
    pred = result["forecast"]
    prev = history.tail(len(pred)).sum()
    change = (pred.sum() - prev) / prev * 100 if prev else 0.0
    err = result["scores"][result["best_model"]]
    return (f"Next {len(pred)} days: about {money(pred.sum(), cur)}, {change:+.0f}% vs the previous {len(pred)} days. "
            f"Best day {pred.idxmax():%a %d %b}, weakest {pred.idxmin():%a %d %b}. "
            f"On past data this method missed by about {err:.0%} per day, so treat single days loosely.")


def payables_summary(p: dict, avg_daily_sales: float, cur: str = "") -> str:
    days = p["outstanding"] / avg_daily_sales if avg_daily_sales else 0
    return (f"Estimated owed to suppliers: {money(p['outstanding'], cur)}, roughly {days:.0f} days of average sales. "
            f"Invoiced {money(p['invoiced'], cur)}, paid so far {money(p['paid_at_purchase'] + p['later_payments'], cur)}.")
