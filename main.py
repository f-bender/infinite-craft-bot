import bisect
import json
import logging
import os
import random
import sys
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

import numpy as np
import requests
from rich import print

from lock import call_if_free

# increase this number to increasingly select lower-depth elements for combination rather than higher-depth ones
LOWER_DEPTH_PRIORITIZATION_FACTOR = 25

HERE = Path(__file__).parent.absolute()

ELEMENTS_JSON = HERE / "elements.json"
RECIPES_JSON = HERE / "recipes.json"
ELEMENTS_PATHS_JSON = HERE / "elements_paths.json"
LOCK_FILE = HERE / f"{Path(__file__).stem}.lock"

ELEMENT_SEPARATOR = ","  # character to separate elements to combine with in interactive mode

logger = logging.getLogger(__name__)

# Set the logging level to the lowest priority (DEBUG) to capture all messages
logger.setLevel(logging.DEBUG)

# Create a formatter with a timestamp
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S")

# Create a file handler for general logs that rotates every midnight
file_handler = TimedRotatingFileHandler(HERE / "logs" / "problems.log", when="H", interval=2, backupCount=1, delay=True)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

# Add the file handler to the logger
logger.addHandler(file_handler)

# Create a separate file handler for debug logs
debug_file_handler = TimedRotatingFileHandler(
    HERE / "logs" / "debug.log", when="M", interval=5, backupCount=1, delay=True
)
debug_file_handler.setLevel(logging.DEBUG)  # Set the handler level to DEBUG
debug_file_handler.setFormatter(formatter)

# Add the debug file handler to the logger
logger.addHandler(debug_file_handler)

MIN_DELAY_S = 1
MAX_DELAY_S = 64

delay_s: float = 4


# TODO: refactor into smaller functions
def main() -> None:
    global delay_s

    interactive = "-i" in sys.argv[1:]
    if interactive:
        print(f"[yellow]Starting in interactive mode! Enter your ingredients, separated by '{ELEMENT_SEPARATOR}'")

    _element_paths = json.load(ELEMENTS_PATHS_JSON.open("r", encoding="UTF-8"))
    elements_to_path: dict[str, set[str]] = {
        element["text"]: set(_element_paths[element["text"]]["path"])
        for element in load_elements(ELEMENTS_JSON)["elements"]
    }
    # list of tuples (element_name, element_path), sorted by path length
    sorted_elements = list(elements_to_path)
    sorted_elements.sort(key=lambda el: len(elements_to_path[el]))

    recipes = {frozenset([recipe["first"], recipe["second"]]) for recipe in load_elements(RECIPES_JSON)["recipes"]}

    t: Optional[float] = None
    while True:
        if interactive:
            user_input = input().strip()
            if user_input.count(ELEMENT_SEPARATOR) != 1:
                print(f"You must specify exactly 2 elements separated by '{ELEMENT_SEPARATOR}'!")
                continue

            first, second = (x.strip() for x in user_input.split(ELEMENT_SEPARATOR))

            # usually, the element names adhere to .title() format, so try that out in case the exact name is not in the
            # known elements
            if first not in elements_to_path:
                if first.title() in elements_to_path:
                    first = first.title()
                else:
                    print(f"'{first}' is not a known element!")
                    continue

            if second not in elements_to_path:
                if second.title() in elements_to_path:
                    second = second.title()
                else:
                    print(f"'{second}' is not a known element!")
                    continue
        else:
            first, second = sample_elements(sorted_elements, elements_to_path)

        recipe = frozenset([first, second])

        # "Nothing" is not actually an element you can use for crafting
        # It shouldn't be part of the elements anyways, but this is an extra safety barrier
        if recipe in recipes or "Nothing" in recipe:
            if interactive:
                print("[grey50]Already known recipe!")
            continue

        if not interactive:
            if t:
                logger.debug(f"Iteration took {(time.perf_counter() - t) * 1_000:.3g}ms")
            time.sleep(delay_s)

        result = craft_items(first, second)
        t = time.perf_counter()
        if not result:
            continue

        recipes.add(recipe)
        add_element(RECIPES_JSON, {"first": first, "second": second, "result": result["result"]})

        new_element_name = result["result"]
        # "Nothing" is not actually an element, but the indication of a recipe being invalid.
        # We still want to save recipes resulting in "Nothing", but it should not be saved as an element
        if new_element_name == "Nothing":
            if interactive:
                print("[grey50]Nothing")
            continue

        new_element_path = elements_to_path[first] | elements_to_path[second] | {new_element_name}

        if new_element_name in elements_to_path:
            if interactive:
                print(f"[grey50]Already known result: {new_element_name}")

            old_length = len(elements_to_path[new_element_name])
            new_length = len(new_element_path)
            if new_length < old_length:
                print_finding(
                    new_element=result, depth=new_length, previous_depth=old_length, first=first, second=second
                )
                elements_to_path[new_element_name] = new_element_path

            continue

        # actually new element

        elements_to_path[new_element_name] = new_element_path
        # add at correct index (keeping it sorted) using bisection
        bisect.insort(sorted_elements, new_element_name, key=lambda el_name: len(elements_to_path[el_name]))
        add_element(ELEMENTS_JSON, {"text": result["result"], "emoji": result["emoji"], "discovered": result["isNew"]})

        print_finding(new_element=result, depth=len(new_element_path), first=first, second=second)


def print_finding(
    new_element: dict[str, str], depth: int, first: str, second: str, previous_depth: Optional[int] = None
) -> None:
    """Unified format of printing new elements (green if new discovery else white) and shorter paths (yellow)."""
    color_str = "[green]" if new_element["isNew"] else "[yellow]" if previous_depth is not None else ""
    new_element_str = f"{new_element['emoji']:>5} {new_element['result']}"
    depth_str = f"({previous_depth} -> {depth})" if previous_depth is not None else f"({depth})"
    ingredients_str = f"({first} + {second})"

    print(f"{color_str}{new_element_str:<50} {depth_str:>12} {ingredients_str}")


def sample_elements(sorted_elements: list[str], elements_to_path: dict[str, set[str]]) -> tuple[str, str]:
    num_elements = len(sorted_elements)

    mean = 0
    std_deviation = len(sorted_elements) / LOWER_DEPTH_PRIORITIZATION_FACTOR

    while True:
        i = j = num_elements
        while not (i < num_elements and j < num_elements):
            i, j = np.random.normal(mean, std_deviation, size=2)
            i, j = int(abs(i)), int(abs(j))

        first_name, second_name = sorted_elements[i], sorted_elements[j]
        first_path, second_path = elements_to_path[first_name], elements_to_path[second_name]

        path_lengths = len(first_path), len(second_path)
        intersection_length = len(first_path & second_path)

        # the highest overlap that would be possible given the path lenths, minus the actual overlap (intersection)
        # -> This many nodes of the path could have overlapped but didn't
        non_overlapping_path_length = min(path_lengths) - intersection_length
        keep_probability = (1 / (1 + non_overlapping_path_length))**0.5

        logger.debug(
            f"{num_elements} -> {(i, j)}, depths {path_lengths} -> "
            f"{sum(path_lengths) + 1 - intersection_length}, intersect {intersection_length}, "
            f"prob {keep_probability:.3g} ({(first_name, second_name)})"
        )
        if random.random() < keep_probability:
            logger.debug("Accepted!")
            return first_name, second_name
        else:
            logger.debug("Discarded!")


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
    # TODO: inline; this function adds no value
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
            if delay_s > MIN_DELAY_S:
                delay_s = max(MIN_DELAY_S, delay_s / 2)
                logger.debug(f"Reducing delay to {delay_s:.3g}s")
            return response.json()
        else:
            logger.warning(f"Crafting failed: {response.status_code} {response.reason}")
            delay_s = min(MAX_DELAY_S, delay_s * 2)
            logger.info(f"Backing off - delay = {delay_s:.3g}s")
    except Exception as e:
        logger.warning(f"Crafting failed: {e}")

    return None


if __name__ == "__main__":
    call_if_free(main, LOCK_FILE)
