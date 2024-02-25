
from collections import Counter
import pandas as pd
import matplotlib.pyplot as plt
from itertools import count
import json
from pathlib import Path
from typing import Optional
from rich import print

from infinite_craft_bot.element_paths.make_plots import compute_stats

PROJECT_ROOT = Path(__file__).parents[1].absolute()

# TODO: script which tells you the steps to get to a given element, based on the outputs of this script

#! This script most likely contains a bug: at commit 'e7a9ce4', Jesus Shark was determined to be the deepest element
#! at depth 400, and *later*, at commit 'f5c7c69', after more recipes where explored, Jesus Shark was determined to be
#! the deepest element at depth 404; i.e. new recipes increased the depth of Jesus Shark,
#! which should never be possible!
#* The good news: overall, the stats seem reasonable, in each iteration the average depths goes down.
#* It just looks like iterating like this, until no more changes occur, doesn't guarantee the optimal depth to be found.
#* (Which I didn't expect)

def main() -> None:
    recipes = [
        # NOTE: don't need to save them as a dict with frozenset keys, because I never look up a recipe
        # (I just iterate over them)
        (recipe["first"], recipe["second"], recipe["result"])
        for recipe in json.load((PROJECT_ROOT / "data" / "recipes.json").open("r", encoding="UTF-8"))["recipes"]
    ]

    elements: dict[str, tuple[Optional[tuple[str, str]], set[str]]] = {
        # elements: (ancestors, path)
        "Water": (None, set()),
        "Fire": (None, set()),
        "Wind": (None, set()),
        "Earth": (None, set()),
    }

    for i in count():
        print(f"Iteration {i}...")
        modified = False

        for first, second, result in recipes:
            new_path = elements[first][1] | elements[second][1] | {result}
            if result in elements:
                # if this path is faster, set it as the path to this element
                if len(new_path) < len(elements[result][1]):
                    new_ancestors = (first, second)
                    elements[result] = (new_ancestors, new_path)
                    modified = True
            else:
                new_ancestors = (first, second)
                elements[result] = (new_ancestors, new_path)
                modified = True

        print("Stats:")
        print(pd.DataFrame([len(path) for _, path in elements.values()]).describe())
        print()
        if not modified:
            print("Done!")
            print()
            break

    with (PROJECT_ROOT / "data" / "elements_paths.json").open("w", encoding="UTF-8") as f:
        json.dump(
            {element: {"anc": ancestors, "path": list(path)} for element, (ancestors, path) in elements.items()},
            f,
            ensure_ascii=False,
            indent=4,
        )

    compute_stats(elements)


if __name__ == "__main__":
    main()
