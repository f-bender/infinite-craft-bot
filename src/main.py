import bisect
import json
import logging
import os
import random
import sys
import time
from multiprocessing.pool import ThreadPool
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import NoReturn, Optional

import numpy as np
import requests
import rich

from lock import call_if_free

# increase this number to increasingly select lower-depth elements for combination rather than higher-depth ones
LOWER_DEPTH_PRIORITIZATION_FACTOR = 25

# the higher this value, the more likely a combination is discarded if their paths don't overlap well
# 0 => no combinations are discarded due to overlap/synergy issues
# 0.5 => a single non-overlap leads to discarding with 29.29% probability, 2 non-overlaps -> 42.27%, ...
# 1 => a single non-overlap leads to discarding with 50% probability, 2 non-overlaps -> 66.67%, ...
# 3 => a single non-overlap leads to discarding with 93.75% probability
NON_SYNERGY_PENALIZATION_COEFFICIENT = 0.5
assert NON_SYNERGY_PENALIZATION_COEFFICIENT >= 0

PROJECT_ROOT = Path(__file__).parents[1].absolute()

ELEMENTS_JSON = PROJECT_ROOT / "data" / "elements.json"
RECIPES_JSON = PROJECT_ROOT / "data" / "recipes.json"
ELEMENTS_PATHS_JSON = PROJECT_ROOT / "data" / "elements_paths.json"
LOCK_FILE = PROJECT_ROOT / f"{Path(__file__).stem}.lock"

ELEMENT_SEPARATOR = ","  # character to separate elements to combine with in interactive mode

logger = logging.getLogger(__name__)

# Set the logging level to the lowest priority (DEBUG) to capture all messages
logger.setLevel(logging.DEBUG)

# Create a formatter with a timestamp
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S")

# Create a file handler for general logs that rotates every midnight
file_handler = TimedRotatingFileHandler(
    PROJECT_ROOT / "logs" / "problems.log", when="H", interval=2, backupCount=1, delay=True
)
file_handler.setLevel(logging.INFO)
file_handler.setFormatter(formatter)

# Add the file handler to the logger
logger.addHandler(file_handler)

# Create a separate file handler for debug logs
debug_file_handler = TimedRotatingFileHandler(
    PROJECT_ROOT / "logs" / "debug.log", when="M", interval=5, backupCount=1, delay=True
)
debug_file_handler.setLevel(logging.DEBUG)  # Set the handler level to DEBUG
debug_file_handler.setFormatter(formatter)

# Add the debug file handler to the logger
logger.addHandler(debug_file_handler)

# Create a console handler for warnings and higher
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.WARNING)  # Set the handler level to WARNING
console_handler.setFormatter(formatter)

# Add the console handler to the logger
logger.addHandler(console_handler)

MAX_NUM_PARALLEL_CRAFTS = 5
num_parallel_crafts: int = 1

#! suspected rate limit: 5 requests per second (it's definitely no higher than that! and most likely not lower!)
#! Watch out: doing ANY manual requests while this script is working at capacity immediately leads to
#! an exceeded rate limit and a 1 hour ban!
#! => 2 parallel requests every 0.4 seconds!
#! OR: 5 parallel requests every 1 second
#! (sometime requests take up to 0.5 seconds, in that case this is slightly faster over time)
MIN_DELAY_S = 1.0
MAX_DELAY_S = 64.0

delay_s = MIN_DELAY_S


def update_delay(increase: bool = False) -> None:
    global delay_s, num_parallel_crafts

    if increase:
        num_parallel_crafts = max(num_parallel_crafts - 1, 1)
    else:
        num_parallel_crafts = min(num_parallel_crafts + 1, MAX_NUM_PARALLEL_CRAFTS)

    before = delay_s

    match delay_s, increase:
        case 0, True:
            # never occurs if branch 3 isn't active
            delay_s = MIN_DELAY_S
        case _, True:
            delay_s = min(delay_s * 2, MAX_DELAY_S)
        #! THIS BRANCH MUST REMAIN DISABLED WHEN MULTIPLE THREADS ARE USED
        # case x, False if x == MIN_DELAY_S:
        #     delay_s = 0
        case x, False if x > 0:
            delay_s = max(delay_s / 2, MIN_DELAY_S)

    if delay_s != before:
        logger.debug(("Increasing" if increase else "Decreasing") + f" delay to {delay_s:.3g}s")


# TODO: refactor into smaller functions
def main() -> NoReturn:
    global delay_s

    interactive = "-i" in sys.argv[1:]
    if interactive:
        rich.print(f"[yellow]Starting in interactive mode! Enter your ingredients, separated by '{ELEMENT_SEPARATOR}'")

    t0 = time.perf_counter()
    _element_paths = json.load(ELEMENTS_PATHS_JSON.open("r", encoding="UTF-8"))
    elements_to_path: dict[str, set[str]] = {
        element["text"]: set(_element_paths[element["text"]]["path"])
        for element in load_elements(ELEMENTS_JSON)["elements"]
    }
    # list of tuples (element_name, element_path), sorted by path length
    sorted_elements = list(elements_to_path)
    sorted_elements.sort(key=lambda el: len(elements_to_path[el]))

    recipes = {frozenset([recipe["first"], recipe["second"]]) for recipe in load_elements(RECIPES_JSON)["recipes"]}
    rich.print(f"Loaded elements and recipes in {time.perf_counter() - t0:.3g}s")

    t: Optional[float] = None
    t_total: Optional[float] = None
    while True:
        if interactive:
            user_input = input().strip()
            if user_input.count(ELEMENT_SEPARATOR) != 1:
                rich.print(f"You must specify exactly 2 elements separated by '{ELEMENT_SEPARATOR}'!")
                continue

            first, second = (x.strip() for x in user_input.split(ELEMENT_SEPARATOR))

            # usually, the element names adhere to .title() format, so try that out in case the exact name is not in the
            # known elements
            if first not in elements_to_path:
                if first.title() in elements_to_path:
                    first = first.title()
                else:
                    rich.print(f"'{first}' is not a known element!")
                    continue

            if second not in elements_to_path:
                if second.title() in elements_to_path:
                    second = second.title()
                else:
                    rich.print(f"'{second}' is not a known element!")
                    continue

            pair = frozenset([first, second])

            if pair in recipes or "Nothing" in pair:
                rich.print("[grey50]Already known recipe!")
                continue

            pairs = [pair]
        else:
            pairs = [
                sample_elements(sorted_elements, elements_to_path, recipes=recipes) for _ in range(num_parallel_crafts)
            ]

        if not interactive:
            if t:
                iteration_time = time.perf_counter() - t
                logger.debug(f"{iteration_time * 1_000:.3g}ms (Iteration)")
            if t_total and (total_loop_time := time.perf_counter() - t_total) < delay_s:
                # TODO: sleep based on how long ago the last request was made (such that there is a fixed time in between requests)
                # ? or maybe rather a fixed time in between a response being received and a new reqeust being made?
                time.sleep(delay_s - total_loop_time)
                #! carefully monitor... but it seems like I'm not getting rate limited anymore, even without this sleep
                # TODO in case this reliably works, think about trying multi-threading/async to increase the rate of requests
            t_total = time.perf_counter()

        with ThreadPool(processes=num_parallel_crafts) as pool:
            results = pool.starmap(craft_items, (tuple(pair) for pair in pairs))
        
        t = time.perf_counter()

        for recipe, result in zip(pairs, results):
            first, second = tuple(recipe)

            if not result:
                continue

            print(".", end="")
            sys.stdout.flush()  # required to correctly display this in Windows Terminal

            recipes.add(recipe)
            add_element(RECIPES_JSON, {"first": first, "second": second, "result": result["result"]})

            new_element_name = result["result"]
            # "Nothing" is not actually an element, but the indication of a recipe being invalid.
            # We still want to save recipes resulting in "Nothing", but it should not be saved as an element
            if new_element_name == "Nothing":
                if interactive:
                    rich.print("[grey50]Nothing")
                continue

            new_element_path = elements_to_path[first] | elements_to_path[second] | {new_element_name}

            if new_element_name in elements_to_path:
                if interactive:
                    rich.print(f"[grey50]Already known result: {new_element_name}")

                old_length = len(elements_to_path[new_element_name])
                new_length = len(new_element_path)
                if new_length < old_length:
                    print_finding(
                        new_element=result, depth=new_length, previous_depth=old_length, first=first, second=second
                    )
                    elements_to_path[new_element_name] = new_element_path
                    # sort again, such that the element moves to its new correct place in the list
                    # (now that its path is shorter)
                    sorted_elements.sort(key=lambda el: len(elements_to_path[el]))

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

    print("\r", end="")
    rich.print(f"{color_str}{new_element_str:<50} {depth_str:>12} {ingredients_str}")


def sample_elements(
    sorted_elements: list[str], elements_to_path: dict[str, set[str]], recipes: set[frozenset]
) -> frozenset[str]:
    num_elements = len(sorted_elements)

    mean = 0
    std_deviation = len(sorted_elements) / LOWER_DEPTH_PRIORITIZATION_FACTOR

    while True:
        i = j = num_elements
        while not (i < num_elements and j < num_elements):
            i, j = np.random.normal(mean, std_deviation, size=2)
            i, j = int(abs(i)), int(abs(j))

        first_name, second_name = sorted_elements[i], sorted_elements[j]
        recipe = frozenset([first_name, second_name])
        if recipe in recipes:
            continue

        first_path, second_path = elements_to_path[first_name], elements_to_path[second_name]

        path_lengths = len(first_path), len(second_path)
        intersection_length = len(first_path & second_path)

        # the highest overlap that would be possible given the path lenths, minus the actual overlap (intersection)
        # -> This many nodes of the path could have overlapped but didn't
        non_overlapping_path_length = min(path_lengths) - intersection_length
        keep_probability = (1 / (1 + non_overlapping_path_length)) ** NON_SYNERGY_PENALIZATION_COEFFICIENT

        logger.debug(
            f"{num_elements} -> {(i, j)}, depths {path_lengths} -> "
            f"{sum(path_lengths) + 1 - intersection_length}, intersect {intersection_length}, "
            f"prob {keep_probability:.3g} ({(first_name, second_name)})"
        )
        if random.random() < keep_probability:
            return first_name, second_name


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
        (logger.debug if t < 2 else logger.info)(f"{t:.3g}s (Request)")

        if response.ok:
            update_delay(increase=False)
            return response.json()
        else:
            logger.warning(f"Crafting failed: {response.status_code} {response.reason}")
            update_delay(increase=True)
    except Exception as e:
        logger.warning(f"Crafting failed: {e}")

    return None


if __name__ == "__main__":
    success = call_if_free(main, LOCK_FILE)
    if not success:
        rich.print("Program is already running in another instance! Exiting with exit code 1...")
        sys.exit(1)
