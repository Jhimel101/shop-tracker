# Shop Tracker

Free, offline sales analytics and forecasting for any shop, restaurant or online store. Upload an Excel or CSV
sales file, confirm which column is which, and get charts, a forecast and best sellers. No LLM, no cloud service,
nothing stored.

## Setup (once)
    python -m venv .venv
    source .venv/bin/activate        # Windows: .venv\Scripts\activate
    pip install -r requirements.txt

## Run
    streamlit run app.py
Upload an .xlsx or .csv in the sidebar. To read a file straight from disk instead (re-reads on every refresh), run with
`SHOP_TRACKER_LOCAL=1 streamlit run app.py` (Windows: `set SHOP_TRACKER_LOCAL=1` first). Never set this on a public host.

## Business types
The app first asks what kind of business it is (restaurant / cafe, grocery, pharmacy, retail shop, online store, something else). The type sets which extra views you get and how columns are guessed: peak hours and average bill for a restaurant; the few items that make most of the revenue, items with no recent sales and average basket for grocery, pharmacy and retail; orders and average order value for an online store. The sales forecast itself works the same way for every type.

## What a file needs
A date column and a sales amount column (or quantity and unit price), one row per day or per sale. Optional: an item
column for best sellers. Several amount columns (Cash + Card) are added together. A workbook with the built-in template
layout (Daily Sales, Expenses, Purchases sheets) is recognised and also gets the cash and supplier-credit tabs.

## Test
    pip install -r requirements-dev.txt
    python -m pytest -q tests/test_core.py tests/test_mapping.py tests/test_types.py tests/test_app_smoke.py

## Layout
    app.py              UI only (Streamlit)
    core/config.py      template layout (sheet names, column ranges) and constants
    core/profiles.py    the business types (data only)
    core/mapping.py     any CSV/Excel -> clean sales table (header detection, column guessing, dates, numbers)
    core/workbook.py    the built-in template workbook -> DataFrames
    core/analytics.py   KPIs, weekday pattern, best sellers, monthly cash, supplier balances
    core/forecast.py    backtested daily sales forecast
    core/insights.py    plain-English summaries
    tests/              unit tests, synthetic restaurant/grocery/online-shop files, app smoke tests

## Deploying
See DEPLOY.md for the free step-by-step guide.
