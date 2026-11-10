"""Constants and the sheet layout of the shop workbook.

If the Excel layout changes (a column moves, a sheet is renamed), this is the
only file that needs editing.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SheetSpec:
    sheet: str    # worksheet name
    cols: str     # Excel column range holding the table, e.g. "A:E"
    names: tuple  # standard names for those columns, in order


HEADER_ROW = 3  # zero-based index of the row with the column titles (Excel row 4)

SHEETS = {
    "daily_sales": SheetSpec("Daily Sales", "A:C", ("date", "cash", "card")),
    "expenses": SheetSpec("Expenses", "A:E", ("date", "category", "description", "paid_by", "amount")),
    "purchases": SheetSpec(
        "Purchases", "A:J",
        ("date", "supplier", "invoice_no", "item", "qty", "unit_price", "total", "paid", "balance", "status"),
    ),
    "supplier_payments": SheetSpec("Purchases", "T:W", ("date", "company", "amount", "notes")),
    "nearby_stores": SheetSpec("Purchases", "Y:AC", ("date", "store", "item", "amount", "paid_by")),
}

SEASON_DAYS = 7        # weekly cycle
BACKTEST_DAYS = 14     # length of each hidden test window
BACKTEST_FOLDS = 3     # how many test windows are averaged
MIN_HISTORY_DAYS = 28  # below this the forecast refuses to run
PRESET_CURRENCY = "QAR"  # default label for the built-in template layout only
