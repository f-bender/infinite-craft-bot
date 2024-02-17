import json
import logging
import os
import random
import sys
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

import requests
from rich import print

from lock import call_if_free

HERE = Path(__file__).parent.absolute()

ELEMENTS_JSON = HERE / "elements.json"
RECIPES_JSON = HERE / "recipes.json"
LOCK_FILE = HERE / f"{__name__}.lock"

ELEMENT_SEPARATOR = ","  # character to separate elements to combine with in interactive mode

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

    interactive = "-i" in sys.argv[1:]
    if interactive:
        print(f"[yellow]Starting in interactive mode! Enter your ingredients, separated by '{ELEMENT_SEPARATOR}'")

    elements = {element["text"] for element in load_elements(ELEMENTS_JSON)["elements"]}
    # keep track of elements in a list separately, to support random.choice()
    # then, nothing in the loop is bottlenecking to O(n)
    elements_list = list(elements)

    recipes = {frozenset([recipe["first"], recipe["second"]]) for recipe in load_elements(RECIPES_JSON)["recipes"]}

    while True:
        if interactive:
            user_input = input().strip()
            if user_input.count(ELEMENT_SEPARATOR) != 1:
                print(f"You must specify exactly 2 elements separated by '{ELEMENT_SEPARATOR}'!")
                continue

            first, second = (x.strip() for x in user_input.split(ELEMENT_SEPARATOR))

            # usually, the element names adhere to .title() format, so try that out in case the exact name is not in the
            # known elements
            if first not in elements:
                if first.title() in elements:
                    first = first.title()
                else:
                    print(f"'{first}' is not a known element!")
                    continue

            if second not in elements:
                if second.title() in elements:
                    second = second.title()
                else:
                    print(f"'{second}' is not a known element!")
                    continue
        else:
            first, second = random.choice(elements_list), random.choice(elements_list)

        recipe = frozenset([first, second])

        # "Nothing" is not actually an element you can use for crafting
        # It shouldn't be part of the elements anyways, but this is an extra safety barrier
        if recipe in recipes or "Nothing" in recipe:
            if interactive:
                print("[grey50]Already known recipe!")
            continue

        if not interactive:
            time.sleep(delay_s)

        result = craft_items(first, second)
        if not result:
            continue

        recipes.add(recipe)
        add_element(RECIPES_JSON, {"first": first, "second": second, "result": result["result"]})
        # "Nothing" is not actually an element, but the indication of a recipe being invalid.
        # We still want to save recipes resulting in "Nothing", but it should not be saved as an element
        if result["result"] in elements or result["result"] == "Nothing":
            if interactive:
                print(f"[grey50]Already known result: {result['result']}")
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
            headers={
                # directly copied from a request made when using Infinite Craft in the browser
                # (F12 -> Network tab -> click on "pair?..." request -> Headers tab -> Request Headers)
                "Accept": "*/*",
                "Accept-Encoding": "gzip, deflate, br",
                "Accept-Language": "en-US,en;q=0.9,de-DE;q=0.8,de;q=0.7",
                "Referer": "https://neal.fun/infinite-craft/",
                "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
                "Sec-Ch-Ua-Mobile": "?0",
                "Sec-Ch-Ua-Platform": '"Windows"',
                "Sec-Fetch-Dest": "empty",
                "Sec-Fetch-Mode": "cors",
                "Sec-Fetch-Site": "same-origin",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            },
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
    call_if_free(main, LOCK_FILE)
