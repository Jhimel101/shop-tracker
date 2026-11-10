"""Excel workbook -> clean pandas DataFrames. Knows the sheet layout, nothing else."""
import io

import pandas as pd

from .config import HEADER_ROW, SHEETS


class WorkbookError(ValueError):
    """Raised when the workbook does not look like the expected shop sheet."""


def open_workbook(source) -> pd.ExcelFile:
    """Accept a path, a file-like object, or raw bytes."""
    if isinstance(source, (bytes, bytearray)):
        source = io.BytesIO(source)
    try:
        return pd.ExcelFile(source)
    except Exception as exc:  # corrupt file, wrong format, ...
        raise WorkbookError(f"Could not open the workbook: {exc}") from exc


def _read(xl: pd.ExcelFile, key: str) -> pd.DataFrame:
    spec = SHEETS[key]
    if spec.sheet not in xl.sheet_names:
        raise WorkbookError(f"Sheet '{spec.sheet}' not found. Sheets present: {', '.join(xl.sheet_names)}")
    df = xl.parse(spec.sheet, header=HEADER_ROW, usecols=spec.cols)
    if len(df.columns) != len(spec.names):
        raise WorkbookError(f"'{spec.sheet}' {spec.cols}: expected {len(spec.names)} columns, got {len(df.columns)}")
    df.columns = list(spec.names)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.dropna(subset=["date"]).reset_index(drop=True)  # drops notes/total rows with no date


def _numeric(df: pd.DataFrame, cols) -> pd.DataFrame:
    df[list(cols)] = df[list(cols)].apply(pd.to_numeric, errors="coerce")
    return df


def load_daily_sales(xl) -> pd.DataFrame:
    df = _numeric(_read(xl, "daily_sales"), ["cash", "card"])
    df[["cash", "card"]] = df[["cash", "card"]].fillna(0)
    df["total"] = df["cash"] + df["card"]  # the sheet's own total is a formula with no stored value
    return df


def load_expenses(xl) -> pd.DataFrame:
    df = _numeric(_read(xl, "expenses"), ["amount"]).dropna(subset=["amount"])
    df["category"] = df["category"].fillna("Uncategorised")
    return df


def load_purchases(xl) -> pd.DataFrame:
    df = _numeric(_read(xl, "purchases"), ["qty", "unit_price", "total", "paid", "balance"])
    df["supplier"] = df["supplier"].fillna("(no supplier name)").astype(str).str.strip()
    df["spend"] = df["total"].fillna(df["paid"])  # total is sometimes blank while paid is filled
    return df


def load_supplier_payments(xl) -> pd.DataFrame:
    df = _numeric(_read(xl, "supplier_payments"), ["amount"]).dropna(subset=["amount"])
    df["company"] = df["company"].fillna("(no name)").astype(str).str.strip()
    return df


def load_nearby_stores(xl) -> pd.DataFrame:
    return _numeric(_read(xl, "nearby_stores"), ["amount"]).dropna(subset=["amount"])


def matches_preset(source) -> bool:
    """True if the file has every sheet of the built-in template layout (see config.SHEETS)."""
    try:
        xl = open_workbook(source)
    except WorkbookError:
        return False
    return {spec.sheet for spec in SHEETS.values()} <= set(xl.sheet_names)


def load_all(source) -> dict:
    xl = open_workbook(source)
    return {
        "sales": load_daily_sales(xl),
        "expenses": load_expenses(xl),
        "purchases": load_purchases(xl),
        "payments": load_supplier_payments(xl),
        "nearby": load_nearby_stores(xl),
    }
