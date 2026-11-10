"""Business types. Data only: what each type is called, which columns to look for, which extra views it gets."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    key: str
    label: str
    blurb: str                 # one line shown under the choice
    item_label: str            # what an item is called ("Dish", "Medicine")
    items_tab: str
    basket_label: str          # what one sale is called ("Average bill")
    item_hints: tuple          # column names to prefer when looking for the item column
    focus_tab: str             # name of the type-specific tab ("" = none)
    panels: tuple              # which extra views it gets: hourly, basket, abc, slow
    default_horizon: int       # forecast days shown first
    slow_days: int             # "no sale for N days" starting point
    slow_note: str


_STOCK_NOTE = "This tool only sees sales, not stock. Check what is actually on your shelves before acting."

PROFILES = {p.key: p for p in [
    Profile("restaurant", "Restaurant / cafe", "Peak hours, best-selling dishes, average bill. Forecast shown for the next 7 days.",
            "Dish", "Menu", "Average bill", ("dish", "menu item", "menu", "food item", "item name", "item"),
            "Peak hours & bills", ("hourly", "basket"), 7, 14,
            "Dishes not ordered recently: consider whether they belong on the menu."),
    Profile("grocery", "Grocery / supermarket", "Fast and slow movers, the few products that bring most of the revenue, average basket.",
            "Product", "Products", "Average basket", ("product", "product name", "sku", "item name", "item"),
            "Stock watch", ("abc", "slow", "basket"), 14, 30, _STOCK_NOTE),
    Profile("pharmacy", "Pharmacy", "Fast and slow-selling medicines, the few products that bring most of the revenue, average sale.",
            "Medicine / product", "Medicines", "Average sale",
            ("medicine", "medicine name", "drug", "drug name", "generic name", "brand name", "product name", "item name"),
            "Stock watch", ("abc", "slow", "basket"), 14, 60,
            "No recent sales does not mean expired or overstocked. Check stock and expiry dates yourself."),
    Profile("retail", "Retail shop", "Best sellers, slow movers, average basket.",
            "Product", "Products", "Average basket", ("product", "product name", "item", "item name"),
            "Stock watch", ("abc", "slow", "basket"), 14, 30, _STOCK_NOTE),
    Profile("online", "Online store", "Orders, average order value, best-selling products, growth.",
            "Product", "Products", "Average order value", ("lineitem name", "product title", "product name", "product"),
            "Orders", ("basket", "abc"), 14, 30, _STOCK_NOTE),
    Profile("other", "Something else", "The core views: sales trend, weekday pattern and a forecast.",
            "Item", "Items", "Average sale", (), "", (), 14, 30, _STOCK_NOTE),
]}
