"""Streamlit UI. Presentation only: all logic lives in core/."""
import os
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from core import analytics as an
from core import insights
from core import mapping as mp
from core import workbook as wb
from core.config import HEADER_ROW, PRESET_CURRENCY, SHEETS
from core.forecast import forecast
from core.profiles import PROFILES, Profile

st.set_page_config(page_title="Shop Tracker", layout="wide")

# Reading a server-side path is for running on your own machine only. Never enable it on a public host.
ALLOW_LOCAL_PATH = os.getenv("SHOP_TRACKER_LOCAL") == "1"
NONE = "(none)"
ORDER_LABELS = {"day_first": "3 April (day first)", "month_first": "March 4 (month first)"}


@st.cache_data(show_spinner="Reading file...")
def read_tables(file_bytes: bytes, filename: str) -> dict:
    return mp.read_tables(file_bytes, filename)


@st.cache_data(show_spinner="Reading workbook...")
def load_preset(file_bytes: bytes) -> dict:
    return wb.load_all(file_bytes)


@st.cache_data
def is_preset(file_bytes: bytes) -> bool:
    return wb.matches_preset(file_bytes)


def pick_profile() -> Profile | None:
    """Step 0: what kind of business is this? It decides which extra views the owner gets."""
    st.subheader("What kind of business is this?")
    key = st.radio("Business type", list(PROFILES), format_func=lambda k: PROFILES[k].label, index=None,
                   horizontal=True, key="business_type", label_visibility="collapsed")
    if key is None:
        st.info("Choose one to continue. It decides the extra views you get, for example peak hours for a "
                "restaurant or slow-moving items for a pharmacy. The sales forecast works the same way for all types.")
        return None
    st.caption(PROFILES[key].blurb)
    return PROFILES[key]


def pick_source() -> tuple[bytes, str] | None:
    with st.sidebar:
        st.header("Data")
        mode = st.radio("Source", ["Upload file", "Local file path"]) if ALLOW_LOCAL_PATH else "Upload file"
        if mode == "Upload file":
            up = st.file_uploader("Sales file (.xlsx or .csv)", type=["xlsx", "csv"])
            return (up.getvalue(), up.name) if up else None
        path = st.text_input("Full path to the file")
        if not path:
            return None
        if not Path(path).is_file():
            st.error("File not found.")
            return None
        st.caption("Re-reads the file on every refresh, so edits in Excel show up after you save.")
        return Path(path).read_bytes(), Path(path).name


def show_help():
    with st.expander("What file does this accept?", expanded=True):
        st.write("Any **.xlsx or .csv** with a **date** column and a **sales amount** column, one row per day or one "
                 "row per sale (a POS or shop export works). You confirm which column is which, so headers can be "
                 "named anything. An item/product column is optional and unlocks a best-sellers view.")
        st.write("Dates are needed for at least 4 weeks to get a forecast.")
        with st.expander("Full template layout (sales + expenses + supplier credit)"):
            st.write(f"Sheets with column titles on row {HEADER_ROW + 1}, data below:")
            for spec in SHEETS.values():
                st.markdown(f"- **{spec.sheet}**, columns {spec.cols}: {', '.join(spec.names)}")
        st.caption("Your file is read in memory to build the charts and is not stored.")


def _pick(label, options, default, key):
    return st.selectbox(label, options, index=options.index(default) if default in options else 0, key=key)


def mapping_ui(tables: dict, p: Profile):
    """Step 1: the user confirms which column is which. Returns the clean sales table, or None."""
    guesses = {s: mp.guess_columns(t, p.item_hints) for s, t in tables.items()}
    names = list(tables)
    st.subheader("Step 1: confirm your columns")
    start = mp.best_sheet(tables, guesses)
    sheet = st.selectbox("Sheet", names, index=names.index(start)) if len(names) > 1 else names[0]
    df, guess = tables[sheet], guesses[sheet]
    cols = [NONE] + list(df.columns)
    key = lambda n: f"{sheet}:{n}"  # noqa: E731  (fresh defaults when the sheet changes)

    left, right = st.columns(2)
    with left:
        date_col = _pick("Date column", cols, guess.date, key("date"))
    with right:
        amount_cols = st.multiselect("Sales amount column(s). Several are added together, e.g. Cash + Card.",
                                     list(df.columns), default=guess.amount, key=key("amount"))
    with st.expander("Optional columns (items, quantity, order number)"):
        item = _pick(f"{p.item_label} column (for best sellers)", cols, guess.item, key("item"))
        qty = _pick("Quantity column", cols, guess.quantity, key("qty"))
        price = _pick("Unit price column (used only if there is no sales amount column)", cols, guess.unit_price, key("price"))
        order_id = _pick(f"Order / bill / invoice number column (for {p.basket_label.lower()})", cols, guess.order_id, key("order_id"))

    order = None
    if date_col != NONE and mp.date_order(df[date_col]) == "ambiguous":
        order = st.radio("Dates like 03/04/2026 mean", list(ORDER_LABELS), format_func=ORDER_LABELS.get,
                         horizontal=True, key=key("order"))

    chosen = mp.Mapping(date=None if date_col == NONE else date_col, amount=amount_cols,
                        item=None if item == NONE else item, quantity=None if qty == NONE else qty,
                        unit_price=None if price == NONE else price, order_id=None if order_id == NONE else order_id)
    if not chosen.complete:
        st.info("Pick the date column and the sales amount column (or quantity and unit price) to continue.")
        return None
    try:
        sales, report = mp.apply_mapping(df, chosen, order)
    except mp.MappingError as exc:
        st.error(str(exc))
        return None
    st.success(f"Using {report['rows_used']:,} of {report['rows_read']:,} rows, "
               f"{report['first']:%d %b %Y} to {report['last']:%d %b %Y}.")
    if report["rows_dropped"]:
        st.caption(f"{report['rows_dropped']:,} rows skipped because the date or amount was missing or unreadable "
                   "(for example a totals row).")
    if "hour" in sales.columns:
        st.caption("Times of day found in the date column, so hourly views are available.")
    st.dataframe(sales.head(8), hide_index=True)
    return sales


def tab_overview(d, cur, p):
    k = an.sales_kpis(d["sales"])
    if not k:
        st.warning("No sales found.")
        return
    s = an.daily_series(d["sales"])
    g = an.growth(s)
    c = st.columns(5 if g else 4)
    c[0].metric("Total sales", insights.money(k["total_sales"], cur))
    c[1].metric("Avg per selling day", insights.money(k["avg_per_selling_day"], cur))
    if k["card_share"] is not None:
        c[2].metric("Card share", f"{k['card_share']:.0%}")
    else:
        c[2].metric("Selling days", f"{k['selling_days']}")
    c[3].metric("Best day", insights.money(k["best_day_total"], cur), f"{k['best_day']:%d %b %Y}")
    if g:
        delta = f"{g['change']:+.0%} vs the {g['days']} days before" if g["change"] is not None else None
        c[4].metric(f"Last {g['days']} days", insights.money(g["current"], cur), delta)
    st.caption(f"{k['start']:%d %b %Y} to {k['end']:%d %b %Y} | {k['selling_days']} selling days")
    hints = missing_hints(d, p)
    if hints:
        st.info(f"More {p.label.lower()} views unlock if your file has: " + "; ".join(hints) + ". Map them in Step 1.")

    fig = go.Figure()
    fig.add_scatter(x=s.index, y=s.values, name="Daily", opacity=0.5)
    fig.add_scatter(x=s.index, y=s.rolling(7, min_periods=1).mean(), name="7-day average")
    fig.update_layout(title="Daily sales", yaxis_title=cur, margin=dict(t=40, b=10))
    st.plotly_chart(fig)

    prof = an.weekday_profile(s)
    bar = go.Figure(go.Bar(x=prof.index, y=prof.values))
    bar.update_layout(title="Average sales by weekday (days with sales)", yaxis_title=cur, margin=dict(t=40, b=10))
    st.plotly_chart(bar)


def tab_forecast(d, cur, p):
    s = an.daily_series(d["sales"])
    horizon = st.slider("Days ahead", 7, 28, p.default_horizon, key=f"horizon:{p.key}")
    try:
        r = forecast(s, horizon)
    except ValueError as exc:
        st.warning(str(exc))
        return
    st.info(insights.forecast_summary(s, r, cur))
    hist = s.tail(60)
    fig = go.Figure()
    fig.add_scatter(x=hist.index, y=hist.values, name="Actual")
    fig.add_scatter(x=r["upper"].index, y=r["upper"], line=dict(width=0), showlegend=False, hoverinfo="skip")
    fig.add_scatter(x=r["lower"].index, y=r["lower"], fill="tonexty", line=dict(width=0), name="Likely range")
    fig.add_scatter(x=r["forecast"].index, y=r["forecast"], name="Forecast", line=dict(dash="dash"))
    fig.update_layout(yaxis_title=cur, margin=dict(t=20, b=10))
    st.plotly_chart(fig)
    st.subheader("How the models scored (lower is better)")
    st.dataframe({m: f"{v:.0%}" for m, v in sorted(r["scores"].items(), key=lambda kv: kv[1])}, width=400)
    st.caption(f"Winner: {r['best_model']}. Forecasts start the day after the last sale in the data.")


def tab_items(d, cur, p):
    by = "revenue"
    if "quantity" in d["sales"].columns:
        by = st.radio("Rank by", ["revenue", "units"], horizontal=True, key=f"rank:{p.key}")
    items = an.top_items(d["sales"], 10, by)
    if items.empty:
        st.info("No item names found.")
        return
    bar = go.Figure(go.Bar(x=items.index, y=items[by]))
    bar.update_layout(title=f"Top {p.item_label.lower()}s by {by}", yaxis_title=cur if by == "revenue" else "units",
                      margin=dict(t=40, b=10))
    st.plotly_chart(bar)
    st.dataframe(items.round(0))


def tab_cash(d, cur, p):
    st.subheader("Monthly cash picture (estimate)")
    m = an.monthly_cash(d["sales"], d["expenses"], d["purchases"], d["payments"], d["nearby"])
    st.dataframe(m.round(0))
    st.caption("net_cash = sales - expenses - money actually paid to suppliers. Unpaid supplier invoices are not "
               "included here (see Suppliers). First and last months may be partial.")
    cats = an.expense_by_category(d["expenses"])
    bar = go.Figure(go.Bar(x=cats.index, y=cats.values))
    bar.update_layout(title="Expenses by category", yaxis_title=cur, margin=dict(t=40, b=10))
    st.plotly_chart(bar)


def tab_suppliers(d, cur, p):
    p = an.payables(d["purchases"], d["payments"], d["nearby"])
    k = an.sales_kpis(d["sales"])
    avg = k["avg_per_selling_day"] if k else 0.0
    c = st.columns(4)
    c[0].metric("Invoiced", insights.money(p["invoiced"], cur))
    c[1].metric("Paid at purchase", insights.money(p["paid_at_purchase"], cur))
    c[2].metric("Later payments", insights.money(p["later_payments"], cur))
    c[3].metric("Still owed (est.)", insights.money(p["outstanding"], cur))
    st.info(insights.payables_summary(p, avg, cur))
    st.subheader("By supplier")
    st.dataframe(an.supplier_balances(d["purchases"], d["payments"]).round(0), hide_index=True)
    st.caption("Rows flagged in 'check' usually mean the same supplier is spelled differently in the Purchases "
               "table and the Payments Log. Fix the spelling in Excel and the balance corrects itself.")


def panel_hourly(d, cur, p):
    prof = an.hourly_profile(d["sales"])
    st.subheader("Peak hours")
    bar = go.Figure(go.Bar(x=[f"{int(h):02d}:00" for h in prof.index], y=prof.values))
    bar.update_layout(yaxis_title=f"average sales per day {cur}".strip(), margin=dict(t=10, b=10))
    st.plotly_chart(bar)
    busiest = sorted(int(h) for h in prof.nlargest(3).index)
    st.caption("Busiest hours: " + ", ".join(f"{h:02d}:00" for h in busiest) + ". Useful for staffing and prep.")


def panel_basket(d, cur, p):
    b = an.basket_stats(d["sales"])
    st.subheader(p.basket_label)
    c = st.columns(3)
    c[0].metric("Orders", f"{b['orders']:,}")
    c[1].metric(p.basket_label, insights.money(b["avg_order_value"], cur))
    c[2].metric("Median", insights.money(b["median_order_value"], cur))
    line = go.Figure(go.Scatter(x=b["orders_per_day"].index, y=b["orders_per_day"].values))
    line.update_layout(title="Orders per day", margin=dict(t=40, b=10))
    st.plotly_chart(line)


def panel_abc(d, cur, p):
    abc = an.abc_analysis(d["sales"])
    st.subheader("Which items matter most")
    n_a = int((abc["class"] == "A").sum())
    st.write(f"**{n_a} of {len(abc)} items ({n_a / len(abc):.0%})** bring in the first 80% of revenue (class A). "
             "Keep these available and priced carefully. Class C items together bring in the last 5%.")
    show = abc.head(25).copy()
    for col in ("share", "cum_share"):
        show[col] = show[col].map("{:.1%}".format)
    show["revenue"] = show["revenue"].round(0)
    st.dataframe(show)


def panel_slow(d, cur, p):
    st.subheader("Items with no recent sales")
    days = st.slider("No sale for at least (days)", 7, 90, p.slow_days, key=f"slow:{p.key}")
    slow = an.slow_movers(d["sales"], days)
    if slow.empty:
        st.success(f"Every item sold within the last {days} days.")
    else:
        st.dataframe(slow.assign(revenue=slow["revenue"].round(0)))
    st.caption(p.slow_note)


PANELS = {"hourly": ("hour", panel_hourly), "basket": ("order_id", panel_basket),
          "abc": ("item", panel_abc), "slow": ("item", panel_slow)}
COLUMN_HINTS = {"hour": "the time of day in the date column (e.g. 19:45)", "order_id": "an order / bill / invoice number",
                "item": "an item or product name"}


def available_panels(d: dict, p: Profile) -> list[str]:
    return [k for k in p.panels if PANELS[k][0] in d["sales"].columns]


def missing_hints(d: dict, p: Profile) -> list[str]:
    """What the file lacks for this business type's views. Not shown for the full template layout."""
    if "expenses" in d:
        return []
    needed = {PANELS[k][0] for k in p.panels} | {"item"}
    return [COLUMN_HINTS[c] for c in COLUMN_HINTS if c in needed and c not in d["sales"].columns]


def tab_focus(d, cur, p):
    for key in available_panels(d, p):
        PANELS[key][1](d, cur, p)


def tabs_for(d: dict, p: Profile) -> list:
    """Show only the tabs the data can support."""
    tabs = [("Overview", tab_overview), ("Forecast", tab_forecast)]
    if "item" in d["sales"].columns:
        tabs.append((p.items_tab, tab_items))
    if p.focus_tab and available_panels(d, p):
        tabs.append((p.focus_tab, tab_focus))
    if "expenses" in d:
        tabs.append(("Cash & expenses", tab_cash))
    if "purchases" in d:
        tabs.append(("Suppliers", tab_suppliers))
    return tabs


def main():
    st.title("Shop Tracker")
    profile = pick_profile()
    if profile is None:
        return
    source = pick_source()
    if source is None:
        st.write("Upload your sales file in the sidebar.")
        show_help()
        return
    raw, filename = source
    try:
        preset = filename.lower().endswith(".xlsx") and is_preset(raw)
        if preset and not st.sidebar.checkbox("Use my own column mapping instead", key="custom"):
            data, default_cur = load_preset(raw), PRESET_CURRENCY
            st.sidebar.caption("Recognised the full template: sales, expenses and supplier credit.")
        else:
            sales = mapping_ui(read_tables(raw, filename), profile)
            if sales is None:
                return
            data, default_cur = {"sales": sales}, ""
    except (wb.WorkbookError, mp.MappingError) as exc:
        st.error(str(exc))
        show_help()
        return
    cur = st.sidebar.text_input("Currency label (optional)", value=default_cur, key=f"cur:{default_cur}")
    tabs = tabs_for(data, profile)
    for tab, (_, render) in zip(st.tabs([name for name, _ in tabs]), tabs):
        with tab:
            render(data, cur, profile)


main()
