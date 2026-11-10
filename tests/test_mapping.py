import io

import numpy as np
import pandas as pd
import pytest

from core import analytics as an
from core import mapping as mp
from core.forecast import forecast
from tests import fixtures as fx


def _first_table(blob, name):
    tables = mp.read_tables(blob, name)
    return next(iter(tables.values()))


def test_restaurant_pos_export_quantity_times_price():
    df = _first_table(fx.restaurant_csv(), "orders.csv")
    g = mp.guess_columns(df)
    assert (g.date, g.item, g.quantity, g.unit_price, g.amount) == ("Order Time", "Item", "Qty", "Unit Price", [])
    out, rep = mp.apply_mapping(df, g)
    assert rep["rows_dropped"] == 0 and rep["first"] == pd.Timestamp("2026-01-01")
    assert out["total"].iloc[0] == out["quantity"].iloc[0] * pd.to_numeric(df["Unit Price"]).iloc[0]
    s = an.daily_series(out)
    assert len(s) == 60 and forecast(s, 14)["forecast"].shape[0] == 14


def test_grocery_sheet_title_row_cash_plus_card_and_totals_row_ignored():
    df = _first_table(fx.grocery_xlsx(), "daily.xlsx")
    g = mp.guess_columns(df)
    assert g.date == "Date" and sorted(g.amount) == ["Card Sales", "Cash Sales"]
    out, rep = mp.apply_mapping(df, g)
    assert rep["rows_dropped"] == 1  # the TOTAL row has no date, so it is not double counted
    assert len(out) == 45
    assert out["total"].sum() == pd.to_numeric(df["Cash Sales"][:45]).sum() + pd.to_numeric(df["Card Sales"][:45]).sum()


def test_online_shop_export_ignores_tax_and_shipping_and_timezones():
    df = _first_table(fx.shopify_csv(), "orders_export.csv")
    g = mp.guess_columns(df)
    assert g.date == "Created at" and g.amount == []
    assert (g.item, g.quantity, g.unit_price) == ("Lineitem name", "Lineitem quantity", "Lineitem price")
    out, _ = mp.apply_mapping(df, g)
    assert out["date"].min() == pd.Timestamp("2026-03-01") and out["date"].dt.tz is None


def test_text_numbers_refunds_and_currency_symbols():
    df = pd.DataFrame({"Date": ["2026-01-01", "2026-01-02", "2026-01-03"], "Sales": ["QAR 1,234.50", "(120.00)", "$1,000"]})
    g = mp.guess_columns(df)
    assert g.date == "Date" and g.amount == ["Sales"]
    out, _ = mp.apply_mapping(df, g)
    assert out["total"].tolist() == [1234.5, -120.0, 1000.0]


@pytest.mark.parametrize("text,expected", [("1.234,50", 1234.5), ("1,234", 1234.0), ("12,5", 12.5), ("(120.00)", -120.0),
                                           ("$1,000", 1000.0), ("1,234,567", 1234567.0), ("abc", None), ("", None)])
def test_to_number(text, expected):
    v = mp.to_number(pd.Series([text])).iloc[0]
    assert (np.isnan(v) if expected is None else v == expected)


def test_date_order_detection():
    s = pd.Series
    assert mp.date_order(s(["03/04/2026", "05/06/2026"])) == "ambiguous"
    assert mp.date_order(s(["13/04/2026"])) == "day_first"
    assert mp.date_order(s(["04/13/2026"])) == "month_first"
    assert mp.date_order(s(["2026-04-13", "2026-04-14"])) == "not_applicable"


def test_ambiguous_dates_follow_the_users_choice():
    ser = pd.Series(["03/04/2026"])
    assert mp.parse_dates(ser, "day_first").iloc[0] == pd.Timestamp("2026-04-03")
    assert mp.parse_dates(ser, "month_first").iloc[0] == pd.Timestamp("2026-03-04")


def test_excel_serial_dates_need_a_date_header():
    df = pd.DataFrame({"Date": [45000 + i for i in range(40)], "Sales": [35000 + i for i in range(40)]})
    g = mp.guess_columns(df)
    assert g.date == "Date" and g.amount == ["Sales"]  # 35000-range sales must not be mistaken for dates
    out, _ = mp.apply_mapping(df, g)
    assert out["date"].iloc[0] == pd.Timestamp("1899-12-30") + pd.Timedelta(days=45000)


def test_semicolon_csv_and_latin1():
    blob = "Date;Total\n" + "\n".join(f"2026-01-{d:02d};{100 + d}" for d in range(1, 29))
    df = _first_table(blob.encode("latin-1"), "x.csv")
    g = mp.guess_columns(df)
    assert g.date == "Date" and g.amount == ["Total"]


def test_missing_amount_is_incomplete_and_apply_refuses():
    df = pd.DataFrame({"Date": ["2026-01-01", "2026-01-02"], "Item": ["a", "b"]})
    g = mp.guess_columns(df)
    assert not g.complete
    with pytest.raises(mp.MappingError):
        mp.apply_mapping(df, g)


def test_wrong_columns_give_a_clear_error_not_a_crash():
    df = pd.DataFrame({"Date": ["hello", "world"], "Sales": [1, 2]})
    with pytest.raises(mp.MappingError, match="valid date"):
        mp.apply_mapping(df, mp.Mapping(date="Date", amount=["Sales"]))


@pytest.mark.parametrize("name,blob,msg", [("old.xls", b"x", "xls"), ("notes.txt", b"x", ".xlsx or .csv"), ("e.csv", b"", "empty")])
def test_unsupported_or_empty_files(name, blob, msg):
    with pytest.raises(mp.MappingError, match=msg):
        mp.read_tables(blob, name)


def test_top_items_and_kpis_without_cash_card_split():
    df = _first_table(fx.restaurant_csv(), "orders.csv")
    out, _ = mp.apply_mapping(df, mp.guess_columns(df))
    top = an.top_items(out, 3)
    assert len(top) == 3 and top["revenue"].is_monotonic_decreasing and "units" in top
    k = an.sales_kpis(out)
    assert k["card_share"] is None and k["total_sales"] == pytest.approx(out["total"].sum())


@pytest.mark.parametrize("order", ["day_first", "month_first"])
def test_year_first_dates_are_never_swapped(order):
    ser = pd.Series(["2026-03-01 14:15:00 +0000", "2026-03-01", "2026/03/01", "05/03/2026"])
    out = mp.parse_dates(ser, order)
    assert (out.iloc[:3] == pd.Timestamp("2026-03-01")).all()  # 1 March, not 3 January
    assert out.iloc[3] == (pd.Timestamp("2026-03-05") if order == "day_first" else pd.Timestamp("2026-05-03"))


def test_multi_sheet_workbook_opens_the_sales_sheet_not_the_longest_one():
    from openpyxl import Workbook
    wb = Workbook()
    exp = wb.active
    exp.title = "Expenses"
    exp.append(["Date", "Amount"])
    for i in range(200):
        exp.append([pd.Timestamp("2026-01-01") + pd.Timedelta(days=i % 90), 10 + i])
    sales = wb.create_sheet("Daily Sales")
    sales.append(["Date", "Total Sales"])
    for i in range(60):
        sales.append([pd.Timestamp("2026-01-01") + pd.Timedelta(days=i), 500 + i])
    buf = io.BytesIO()
    wb.save(buf)
    tables = mp.read_tables(buf.getvalue(), "shop.xlsx")
    guesses = {k: mp.guess_columns(v) for k, v in tables.items()}
    assert mp.best_sheet(tables, guesses) == "Daily Sales"


def test_a_notes_column_of_numbers_and_text_never_breaks_guessing():
    df = pd.DataFrame({"Date": pd.date_range("2026-01-01", periods=8).astype(str), "Sales": range(100, 108),
                       "Notes": ["1398", "617", "ok", "50", "n/a", "1398", "see invoice", "1200"]})
    g = mp.guess_columns(df)
    assert g.date == "Date" and g.amount == ["Sales"]
    out, _ = mp.apply_mapping(df, g)
    assert len(out) == 8


def test_parse_dates_handles_empty_and_all_nonsense_input():
    assert mp.parse_dates(pd.Series([], dtype=object)).empty
    assert mp.parse_dates(pd.Series(["hello", "world"])).isna().all()
