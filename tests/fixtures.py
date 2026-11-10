"""Synthetic sales files shaped like what real businesses export."""
import io

import numpy as np
import pandas as pd
from openpyxl import Workbook


def restaurant_csv(days=60) -> bytes:
    """POS export: one row per order line, dd/mm/yyyy with time, a bill number, no total (quantity x unit price)."""
    rng = np.random.default_rng(1)
    rows, bill = [], 5000
    for d in pd.date_range("2026-01-01", periods=days):
        for _ in range(rng.integers(5, 12)):
            bill += 1
            hour = int(rng.choice([12, 13, 14, 19, 20, 21], p=[.15, .2, .1, .15, .25, .15]))
            for _ in range(int(rng.integers(1, 4))):
                rows.append((f"{d:%d/%m/%Y} {hour}:{rng.integers(0, 59):02d}", f"B{bill}",
                             rng.choice(["Burger", "Fries", "Cola", "Pizza"]), int(rng.integers(1, 4)),
                             float(rng.choice([2.5, 4, 6.5, 9])), rng.choice(["Cash", "Card"])))
    cols = ["Order Time", "Bill No", "Item", "Qty", "Unit Price", "Payment Method"]
    return pd.DataFrame(rows, columns=cols).to_csv(index=False).encode()


def pharmacy_csv(days=90) -> bytes:
    """Invoice lines with a customer name column (a trap for 'name') and a medicine column. The last
    three medicines stop selling after day 30, so they are the slow movers."""
    rng = np.random.default_rng(4)
    meds = [f"Medicine {chr(65 + i)}" for i in range(20)]
    rows, invoice = [], 1000
    for i, d in enumerate(pd.date_range("2026-04-01", periods=days)):
        pool = meds if i < 30 else meds[:-3]
        w = 0.85 ** np.arange(len(pool))  # skewed, but every medicine sells regularly while it is stocked
        for _ in range(int(rng.integers(8, 16))):
            invoice += 1
            for _ in range(int(rng.integers(1, 3))):
                rows.append((f"{d:%Y-%m-%d}", invoice, f"Customer {rng.integers(1, 200)}", rng.choice(pool, p=w / w.sum()),
                             int(rng.integers(1, 4)), float(rng.choice([1.5, 3.0, 7.5, 12.0]))))
    cols = ["Date", "Invoice No", "Customer Name", "Medicine Name", "Qty", "Unit Price"]
    return pd.DataFrame(rows, columns=cols).to_csv(index=False).encode()


def grocery_xlsx(days=45) -> bytes:
    """Daily sheet: title row, blank row, Cash/Card columns (no total), remarks, and a TOTAL row at the bottom."""
    wb = Workbook()
    ws = wb.active
    ws.append(["Fresh Mart - Daily Sales"])
    ws.append([])
    ws.append(["Date", "Cash Sales", "Card Sales", "Remarks"])
    rng = np.random.default_rng(2)
    cash_total = card_total = 0
    for d in pd.date_range("2026-02-01", periods=days):
        cash, card = int(rng.integers(300, 900)), int(rng.integers(200, 700))
        cash_total, card_total = cash_total + cash, card_total + card
        ws.append([d.to_pydatetime(), cash, card, "ok" if rng.random() > 0.8 else None])
    ws.append(["TOTAL", cash_total, card_total, None])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def shopify_csv(days=40) -> bytes:
    """Online shop export: tz-aware timestamps, line items, tax/shipping columns that are not sales."""
    rng = np.random.default_rng(3)
    rows = []
    for i, d in enumerate(pd.date_range("2026-03-01", periods=days)):
        for j in range(int(rng.integers(2, 7))):
            rows.append((f"#{1000 + i * 10 + j}", f"{d:%Y-%m-%d} {rng.integers(8, 22)}:15:00 +0000",
                         int(rng.integers(1, 3)), rng.choice(["T-Shirt", "Mug", "Cap"]),
                         float(rng.choice([12.0, 8.5, 15.0])), 3.0, 1.2, "USD"))
    cols = ["Name", "Created at", "Lineitem quantity", "Lineitem name", "Lineitem price", "Shipping", "Total Tax", "Currency"]
    return pd.DataFrame(rows, columns=cols).to_csv(index=False).encode()
