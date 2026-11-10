"""Drives the real Streamlit app headlessly (local-path mode) on synthetic files."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from tests import fixtures as fx

APP = str(Path(__file__).resolve().parent.parent / "app.py")


def start(monkeypatch):
    monkeypatch.setenv("SHOP_TRACKER_LOCAL", "1")
    return AppTest.from_file(APP, default_timeout=120).run()


def run(tmp_path, monkeypatch, business, name, blob):
    path = tmp_path / name
    path.write_bytes(blob)
    at = start(monkeypatch)
    at.radio(key="business_type").set_value(business).run()
    at.sidebar.radio[0].set_value("Local file path").run()
    at.sidebar.text_input[0].set_value(str(path)).run()
    return at


def test_app_asks_for_the_business_type_first(monkeypatch):
    at = start(monkeypatch)
    assert not at.exception
    assert [r.options for r in at.radio][0] == ["Restaurant / cafe", "Grocery / supermarket", "Pharmacy",
                                                "Retail shop", "Online store", "Something else"]
    assert len(at.sidebar.radio) == 0 and len(at.sidebar.file_uploader) == 0  # nothing to upload yet


@pytest.mark.parametrize("business,name,blob,tabs", [
    ("restaurant", "orders.csv", fx.restaurant_csv(), ["Overview", "Forecast", "Menu", "Peak hours & bills"]),
    ("pharmacy", "sales.csv", fx.pharmacy_csv(), ["Overview", "Forecast", "Medicines", "Stock watch"]),
    ("online", "shop.csv", fx.shopify_csv(), ["Overview", "Forecast", "Products", "Orders"]),
    ("grocery", "daily.xlsx", fx.grocery_xlsx(), ["Overview", "Forecast"]),
    ("other", "orders.csv", fx.restaurant_csv(), ["Overview", "Forecast", "Items"]),
])
def test_each_business_type_gets_its_own_views(tmp_path, monkeypatch, business, name, blob, tabs):
    at = run(tmp_path, monkeypatch, business, name, blob)
    assert not at.exception and not at.error
    assert [t.label for t in at.tabs] == tabs
    assert len(at.metric) >= 4


def test_forecast_horizon_default_follows_the_business_type(tmp_path, monkeypatch):
    restaurant = run(tmp_path, monkeypatch, "restaurant", "o.csv", fx.restaurant_csv())
    assert restaurant.slider(key="horizon:restaurant").value == 7
    pharmacy = run(tmp_path, monkeypatch, "pharmacy", "p.csv", fx.pharmacy_csv())
    assert pharmacy.slider(key="horizon:pharmacy").value == 14


def test_missing_columns_are_explained_not_hidden(tmp_path, monkeypatch):
    at = run(tmp_path, monkeypatch, "restaurant", "daily.xlsx", fx.grocery_xlsx())
    assert any("unlock" in i.value for i in at.info)


def test_unreadable_file_shows_an_error_not_a_traceback(tmp_path, monkeypatch):
    at = run(tmp_path, monkeypatch, "retail", "notes.txt", b"hello")
    assert not at.exception and at.error
