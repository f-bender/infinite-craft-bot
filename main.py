import json
import logging
import os
import random
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

import requests
from rich import print

HERE = Path(__file__).parent.absolute()
ELEMENTS_JSON = HERE / "elements.json"
RECIPES_JSON = HERE / "recipes.json"

logger = logging.getLogger(__name__)

# Set the logging level to the lowest priority (DEBUG) to capture all messages
logger.setLevel(logging.INFO)

# Create a formatter with a timestamp
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

# Create a file handler that rotates every midnight
file_handler = TimedRotatingFileHandler(HERE / "logs" / "problems.log", when="H", interval=2, backupCount=1, delay=True)
file_handler.setFormatter(formatter)

# Add the file handler to the logger
logger.addHandler(file_handler)

MIN_DELAY_S = 1
MAX_DELAY_S = 64

delay_s: float = 4


def main() -> None:
    global delay_s

    elements = {element["text"] for element in load_elements(ELEMENTS_JSON)["elements"]}
    # keep track of elements in a list separately, to support random.choice()
    # then, nothing in the loop is bottlenecking to O(n)
    elements_list = list(elements)

    recipes = {frozenset([recipe["first"], recipe["second"]]) for recipe in load_elements(RECIPES_JSON)["recipes"]}

    while True:
        first, second = random.choice(elements_list), random.choice(elements_list)
        # first, second = input().strip().split("+")  # manual mode
        recipe = frozenset([first, second])
        # "Nothing" is not actually an element you can use for crafting
        # It shouldn't be part of the elements anyways, but this is an extra safety barrier
        if recipe in recipes or "Nothing" in recipe:
            continue

        time.sleep(delay_s)
        result = craft_items(first, second)
        if not result:
            continue

        recipes.add(recipe)
        add_element(RECIPES_JSON, {"first": first, "second": second, "result": result["result"]})
        # "Nothing" is not actually an element, but the indication of a recipe being invalid.
        # We still want to save recipes resulting in "Nothing", but it should not be saved as an element
        if result["result"] in elements or result["result"] == "Nothing":
            continue

        elements.add(result["result"])
        elements_list.append(result["result"])
        add_element(ELEMENTS_JSON, {"text": result["result"], "emoji": result["emoji"], "discovered": result["isNew"]})

        color = "[green]" if result["isNew"] else ""
        new_element_str = f"{result['emoji']:>5} {result['result']}"
        print(f"{color}{new_element_str:<50} ({first} + {second})")


def load_elements(file: Path) -> dict[str, list[dict[str, str]]]:
    """Returns the elements loaded from a json file.

    Structure:
    {
        "elements"/"recipes": [
            {
                "text": "<element-name>",
                "emoji": "<element-emoji>",
                "discovered": true/false
            },
            ...
        ]
    }
    """
    with file.open("r", encoding="UTF-8") as f:
        return json.load(f)


def add_element(file: Path, new_element: dict[str, str]) -> None:
    with file.open("r+", encoding="UTF-8") as f:
        # move cursor to the closing "}" of the last element
        f.seek(0, os.SEEK_END)
        f.seek(f.tell() - 10)

        # remove everything after this point
        f.truncate()

        # add the new element, and re-add the closing parentheses
        new_element_str = json.dumps(new_element, ensure_ascii=False)
        f.write(f",\n        {new_element_str}\n    ]\n}}")


def craft_items(item1: str, item2: str) -> Optional[dict[str, str]]:
    global delay_s
    try:
        # TODO keep an open session
        t0 = time.perf_counter()
        response = requests.get(
            f"https://neal.fun/api/infinite-craft/pair?first={item1}&second={item2}",
            headers={"Referer": "https://neal.fun/infinite-craft/"},
            timeout=10,
        )
        t = time.perf_counter() - t0
        (logger.debug if t < 2 else logger.info)(f"Request took {t:.3g}s")

        if response.ok:
            delay_s = max(MIN_DELAY_S, delay_s / 2)
            return response.json()
        else:
            logger.warning(f"Crafting failed: {response.status_code} {response.reason}")
            if response.status_code == 429 and response.reason == "Too Many Requests":
                delay_s = min(MAX_DELAY_S, delay_s * 2)
                logger.info(f"Backing off - delay = {delay_s}s")
    except Exception as e:
        logger.warning(f"Crafting failed: {e}")

    return None


if __name__ == "__main__":
    main()
