"""Turn an arbitrary sales spreadsheet or CSV into a clean sales table.

Pipeline: read_tables -> guess_columns -> (user confirms) -> apply_mapping.
Pure functions, no UI.
"""
import io
import re
import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

MAX_ROWS = 500_000
HEADER_SCAN_ROWS = 15
SAMPLE_ROWS = 2000
EXCEL_SERIAL_RANGE = (30000, 80000)  # Excel day numbers, roughly years 1982-2118

# Header names, best match first. Matching is on lowercase words.
DATE_NAMES = ["date", "order date", "sale date", "sales date", "transaction date", "invoice date",
              "created at", "created", "paid at", "day", "timestamp", "datetime", "time"]
AMOUNT_NAMES = ["net sales", "total sales", "sales amount", "sales", "revenue", "grand total",
                "total amount", "line total", "total price", "total", "amount", "sale amount",
                "income", "turnover", "value"]
ITEM_NAMES = ["item", "item name", "product", "product name", "menu item", "dish", "lineitem name",
              "description", "sku", "category", "name"]
QTY_NAMES = ["quantity", "qty", "units", "lineitem quantity", "count", "pieces"]
PRICE_NAMES = ["unit price", "price", "rate", "lineitem price", "selling price"]
NOT_AN_AMOUNT = {"id", "no", "number", "qty", "quantity", "tax", "discount", "shipping", "cost",
                 "tip", "fee", "balance", "paid"}
ORDER_NAMES = ["order id", "order number", "order no", "invoice no", "invoice number", "invoice", "bill no",
               "bill number", "receipt no", "receipt number", "receipt", "transaction id", "txn id", "order"]
SALES_SHEET_WORDS = {"sales", "sale", "revenue", "orders", "order", "transactions", "daily", "pos", "income"}
PAYMENT_WORDS = {"cash", "card", "online", "upi", "wallet", "mobile", "visa", "credit", "debit", "cod"}


class MappingError(ValueError):
    """The file could not be read or the chosen columns do not work."""


@dataclass
class Mapping:
    date: str | None = None
    amount: list[str] = field(default_factory=list)  # several columns are added (e.g. Cash + Card)
    item: str | None = None
    quantity: str | None = None
    unit_price: str | None = None
    order_id: str | None = None  # one value per bill/order/invoice: enables "average bill"

    @property
    def complete(self) -> bool:
        return bool(self.date) and (bool(self.amount) or bool(self.quantity and self.unit_price))


# ---------- numbers and dates ----------

def _clean_number(x):
    if not isinstance(x, str):
        if isinstance(x, (bool, np.bool_)) or pd.isna(x):
            return np.nan
        return float(x) if isinstance(x, (int, float, np.integer, np.floating)) else np.nan
    t = x.strip()
    negative = t.startswith("(") and t.endswith(")")
    t = re.sub(r"[^\d,.\-]", "", t)
    if not re.search(r"\d", t):
        return np.nan
    if "," in t and "." in t:  # 1,234.50 or 1.234,50: the last separator is the decimal one
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        head, _, tail = t.rpartition(",")
        t = t.replace(",", "") if (t.count(",") > 1 or len(tail) == 3) else f"{head}.{tail}"
    try:
        value = float(t)
    except ValueError:
        return np.nan
    return -abs(value) if negative else value


def to_number(series: pd.Series) -> pd.Series:
    """Numbers stored as text ('QAR 1,234.50', '(120.00)', '1.234,50') become floats; junk becomes NaN."""
    return series.map(_clean_number).astype(float)


def _looks_numeric(v: str) -> bool:
    return bool(re.fullmatch(r"[\s\d,.\-+%$€£()]+", v))


_SLASH_DATE = re.compile(r"^\s*(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})")


def date_order(series: pd.Series) -> str:
    """'day_first', 'month_first', 'ambiguous' (e.g. 03/04/2026 only) or 'not_applicable' (ISO, real dates)."""
    firsts, seconds = [], []
    for v in series.dropna().astype(str).head(20000):
        m = _SLASH_DATE.match(v)
        if m:
            firsts.append(int(m[1]))
            seconds.append(int(m[2]))
    if not firsts:
        return "not_applicable"
    if max(firsts) > 12:
        return "day_first"
    if max(seconds) > 12:
        return "month_first"
    return "ambiguous"


_ISO_DATE = r"^\s*\d{4}[-/]\d{1,2}[-/]\d{1,2}"  # year first: never ambiguous, never day-first


_UTC_OFFSET = r"(\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?)\s*(?:Z|UTC|[+-]\d{2}:?\d{2})\s*$"  # only after a time of day


def _parse_strings(series: pd.Series, order: str) -> pd.Series:
    """Year-first dates are read as year-month-day whatever the order setting (pandas would swap them
    when dayfirst is on); every other format follows the day/month order. A UTC offset after a time is
    dropped, keeping the clock time shown in the file, so a 23:30 sale stays on its own day."""
    series = series.astype(str).str.replace(_UTC_OFFSET, r"\1", regex=True)
    iso = series.str.match(_ISO_DATE)

    def convert(part: pd.Series, dayfirst: bool) -> pd.Series:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return pd.to_datetime(part, errors="coerce", dayfirst=dayfirst, format="mixed")

    parts = [convert(series[mask], dayfirst) for mask, dayfirst in ((iso, False), (~iso, order == "day_first")) if mask.any()]
    if not parts:  # empty input
        return convert(series, False)
    return pd.concat(parts).reindex(series.index)


def parse_timestamps(series: pd.Series, order: str = "day_first") -> pd.Series:
    """Dates of any common format -> timestamps. The time of day is kept when the file has one."""
    if pd.api.types.is_datetime64_any_dtype(series):
        out = series
    else:
        num = pd.to_numeric(series, errors="coerce")
        if num.notna().mean() > 0.9:  # Excel stores dates as day numbers when the cell is not formatted
            out = pd.to_datetime(num.where(num.between(*EXCEL_SERIAL_RANGE)), unit="D",
                                 origin="1899-12-30", errors="coerce")
        else:
            out = _parse_strings(series, order)
    if getattr(out.dt, "tz", None) is not None:
        out = out.dt.tz_localize(None)
    return out


def parse_dates(series: pd.Series, order: str = "day_first") -> pd.Series:
    """Same, as midnight timestamps (one value per calendar day)."""
    return parse_timestamps(series, order).dt.normalize()


# ---------- reading files ----------

def _read_csv(source: bytes) -> pd.DataFrame:
    for encoding in ("utf-8-sig", "latin-1"):
        for sep in (None, ","):
            try:
                return pd.read_csv(io.BytesIO(source), header=None, sep=sep, engine="python", dtype=object,
                                   encoding=encoding, on_bad_lines="skip")
            except pd.errors.EmptyDataError as exc:
                raise MappingError("The file is empty.") from exc
            except (UnicodeDecodeError, pd.errors.ParserError, csv_error()):
                continue
    raise MappingError("Could not read this CSV file.")


def csv_error():
    import csv
    return csv.Error


def _with_header(raw: pd.DataFrame) -> pd.DataFrame | None:
    """Find the title row (it is not always the first one) and return the table beneath it."""
    raw = raw.dropna(how="all").dropna(axis=1, how="all").reset_index(drop=True)
    if raw.empty:
        return None
    top = raw.head(HEADER_SCAN_ROWS)
    scores = [sum(isinstance(v, str) and v.strip() != "" and not _looks_numeric(v) for v in row)
              for row in top.itertuples(index=False)]
    header_at = int(np.argmax(scores)) if max(scores) >= 2 else 0  # earliest row wins ties
    names, seen = [], {}
    for i, v in enumerate(raw.iloc[header_at]):
        name = str(v).strip() if pd.notna(v) and str(v).strip() else f"column_{i + 1}"
        seen[name] = seen.get(name, 0) + 1
        names.append(name if seen[name] == 1 else f"{name}_{seen[name]}")
    table = raw.iloc[header_at + 1:].copy()
    table.columns = names
    table = table.dropna(how="all").reset_index(drop=True)
    return table if len(table) else None


def read_tables(source: bytes, filename: str) -> dict[str, pd.DataFrame]:
    """One clean table per sheet (a CSV has one). Title rows above the headers are skipped."""
    name = filename.lower()
    if name.endswith(".csv"):
        raw = {"CSV": _read_csv(source)}
    elif name.endswith(".xlsx"):
        try:
            xl = pd.ExcelFile(io.BytesIO(source))
            raw = {s: xl.parse(s, header=None) for s in xl.sheet_names}
        except Exception as exc:
            raise MappingError(f"Could not open the Excel file: {exc}") from exc
    elif name.endswith(".xls"):
        raise MappingError("Old .xls files are not supported. In Excel use Save As > .xlsx and upload that.")
    else:
        raise MappingError("Please upload an .xlsx or .csv file.")
    tables = {}
    for sheet, df in raw.items():
        table = _with_header(df)
        if table is not None:
            tables[sheet] = table
    if not tables:
        raise MappingError("No table with data was found in this file.")
    if sum(len(t) for t in tables.values()) > MAX_ROWS:
        raise MappingError(f"This file has more than {MAX_ROWS:,} rows, which is more than this tool handles.")
    return tables


# ---------- guessing columns ----------

def _norm(name) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(name).lower()).split())


def _name_score(col, names) -> int:
    n = _norm(col)
    tokens = set(n.split())
    for i, cand in enumerate(names):
        if n == cand:
            return 100 - i
    for i, cand in enumerate(names):
        if set(cand.split()) <= tokens:
            return 50 - i
    return 0


def _sample(series: pd.Series) -> pd.Series:
    return series.dropna().head(SAMPLE_ROWS)


def _numeric_ratio(series: pd.Series) -> float:
    s = _sample(series)
    return float(to_number(s).notna().mean()) if len(s) else 0.0


def _text_ratio(series: pd.Series) -> float:
    s = _sample(series)
    if s.empty:
        return 0.0
    return float(s.map(lambda v: isinstance(v, str) and v.strip() != "" and not _looks_numeric(v)).mean())


def _guess_date(df: pd.DataFrame) -> str | None:
    best = None
    for col in df.columns:
        s = _sample(df[col])
        if s.empty:
            continue
        score = _name_score(col, DATE_NAMES)
        numeric = pd.to_numeric(s, errors="coerce")
        if numeric.notna().mean() > 0.9:  # numbers are dates only if the header says so and they look like Excel days
            if not score:
                continue
            ratio = float(numeric.between(*EXCEL_SERIAL_RANGE).mean())
        else:
            try:
                ratio = float(parse_dates(s, "day_first").notna().mean())
            except (ValueError, OverflowError):  # e.g. text such as "1398" read as a year outside pandas' range
                continue
        if ratio < (0.8 if score else 0.9):
            continue
        if best is None or (score, ratio) > best[0]:
            best = ((score, ratio), col)
    return best[1] if best else None


def _best_by_name(df, names, valid, exclude=()):
    scored = [(_name_score(c, names), c) for c in df.columns if c not in exclude]
    scored = [(s, c) for s, c in scored if s > 0 and valid(df[c])]
    return max(scored, key=lambda t: t[0])[1] if scored else None


def _guess_amount(df: pd.DataFrame, exclude: set) -> list[str]:
    cands = []
    for c in df.columns:
        if c in exclude or set(_norm(c).split()) & NOT_AN_AMOUNT:
            continue
        score = _name_score(c, AMOUNT_NAMES)
        if score and _numeric_ratio(df[c]) >= 0.6:
            cands.append((score, c))
    if not cands:
        return []
    cands.sort(key=lambda t: -t[0])
    top_score, top = cands[0]
    if set(_norm(top).split()) & PAYMENT_WORDS:  # Cash + Card columns: add them together
        return [c for s, c in cands if s == top_score and set(_norm(c).split()) & PAYMENT_WORDS]
    return [top]


def guess_columns(df: pd.DataFrame, item_hints: tuple = ()) -> Mapping:
    """item_hints: header names to prefer for the item column (from the business type)."""
    m = Mapping(date=_guess_date(df))
    used = {m.date}
    m.amount = _guess_amount(df, used)
    used |= set(m.amount)
    m.item = _best_by_name(df, [*item_hints, *ITEM_NAMES], lambda s: _text_ratio(s) >= 0.7, used)
    used.add(m.item)
    m.quantity = _best_by_name(df, QTY_NAMES, lambda s: _numeric_ratio(s) >= 0.8, used)
    used.add(m.quantity)
    m.unit_price = _best_by_name(df, PRICE_NAMES, lambda s: _numeric_ratio(s) >= 0.8, used)
    if not m.amount and m.unit_price and not m.quantity:  # just "Date, Item, Price": the price is the sale
        m.amount, m.unit_price = [m.unit_price], None
    m.order_id = _best_by_name(df, ORDER_NAMES, lambda s: len(_sample(s)) > 0, used | set(m.amount) | {m.unit_price})
    return m


def best_sheet(tables: dict, guesses: dict) -> str:
    """Which sheet to open first: one we could map, preferring names like 'Daily Sales', then the longest."""
    pool = [s for s, g in guesses.items() if g.complete] or list(tables)
    named = [s for s in pool if set(_norm(s).split()) & SALES_SHEET_WORDS]
    return max(named or pool, key=lambda s: len(tables[s]))


# ---------- applying the user's choice ----------

def apply_mapping(df: pd.DataFrame, m: Mapping, order: str | None = None) -> tuple[pd.DataFrame, dict]:
    """Return a table with date, total (+ item, quantity if mapped) and a report of what was used."""
    if not m.complete:
        raise MappingError("Choose a date column and a sales amount column.")
    chosen = [c for c in [m.date, *m.amount, m.item, m.quantity, m.unit_price, m.order_id] if c]
    missing = [c for c in chosen if c not in df.columns]
    if missing:
        raise MappingError(f"Column not found: {', '.join(missing)}")
    if order is None:
        order = "month_first" if date_order(df[m.date]) == "month_first" else "day_first"

    if m.amount:
        total = pd.concat([to_number(df[c]) for c in m.amount], axis=1).sum(axis=1, min_count=1)
    else:
        total = to_number(df[m.unit_price]) * to_number(df[m.quantity])
    stamps = parse_timestamps(df[m.date], order)
    out = pd.DataFrame({"date": stamps.dt.normalize(), "total": total})
    has_time = stamps.notna() & (stamps != stamps.dt.normalize())
    if has_time.any() and has_time.sum() >= 0.3 * stamps.notna().sum():  # most rows carry a time of day
        out["hour"] = stamps.dt.hour.astype(float)
    if m.item:
        out["item"] = df[m.item].map(lambda v: str(v).strip() if pd.notna(v) else np.nan)
    if m.quantity:
        out["quantity"] = to_number(df[m.quantity])
    if m.order_id:
        out["order_id"] = df[m.order_id].map(lambda v: str(v).strip() if pd.notna(v) else np.nan)

    used = out.dropna(subset=["date", "total"]).reset_index(drop=True)
    if used.empty:
        raise MappingError("No rows have both a valid date and a valid amount. "
                           "Check the column choices (and the day/month order of the dates).")
    return used, {"rows_read": len(df), "rows_used": len(used), "rows_dropped": len(df) - len(used),
                  "first": used["date"].min(), "last": used["date"].max()}
