import json
from math import ceil
from pathlib import Path

import pandas as pd

ITEMS_PER_FILE = 50_000
NUM_PAGINATION_DIGITS = 5

JSON_DIR = Path(__file__).parent / "json"
CSV_DIR = Path(__file__).parent / "csv"

CSV_ELEMENTS_DIR = CSV_DIR / "elements"
CSV_RECIPES_DIR = CSV_DIR / "recipes"

CSV_ELEMENTS_DIR.mkdir(parents=True, exist_ok=True)
CSV_RECIPES_DIR.mkdir(parents=True, exist_ok=True)


def convert_elements() -> None:
    elements_df = pd.DataFrame(json.load((JSON_DIR / "elements.json").open("r", encoding="UTF-8"))["elements"])

    for page in range(ceil(len(elements_df) / ITEMS_PER_FILE)):
        elements_df_page = elements_df[page * ITEMS_PER_FILE : (page + 1) * ITEMS_PER_FILE]
        print(ITEMS_PER_FILE, page, len(elements_df_page))
        elements_df_page.to_csv(CSV_ELEMENTS_DIR / f"{page:0>{NUM_PAGINATION_DIGITS}}.csv", index=False)


def convert_recipes() -> None:
    recipes_df = pd.DataFrame(json.load((JSON_DIR / "recipes.json").open("r", encoding="UTF-8"))["recipes"])

    for page in range(ceil(len(recipes_df) / ITEMS_PER_FILE)):
        recipes_df_page = recipes_df[page * ITEMS_PER_FILE : (page + 1) * ITEMS_PER_FILE]
        print(ITEMS_PER_FILE, page, len(recipes_df_page))
        recipes_df_page.to_csv(CSV_RECIPES_DIR / f"{page:0>{NUM_PAGINATION_DIGITS}}.csv", index=False)


convert_elements()
convert_recipes()
