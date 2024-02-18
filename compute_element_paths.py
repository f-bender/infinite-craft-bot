from collections import Counter
import matplotlib.pyplot as plt
from itertools import count
import json
from pathlib import Path
from typing import Optional
from rich import print

HERE = Path(__file__).parent.absolute()


def main() -> None:
    recipes = [
        # NOTE: don't need to save them as a dict with frozenset keys, because I never look up a recipe
        # (I just iterate over them)
        (recipe["first"], recipe["second"], recipe["result"])
        for recipe in json.load((HERE / "recipes.json").open("r", encoding="UTF-8"))["recipes"]
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

        if not modified:
            print("Done!")
            break

    with (HERE / "elements_paths.json").open("w", encoding="UTF-8") as f:
        json.dump(
            {element: {"anc": ancestors, "path": list(path)} for element, (ancestors, path) in elements.items()},
            f,
            ensure_ascii=False,
            indent=4,
        )

    compute_stats(elements)


def compute_stats(elements: dict[str, tuple[Optional[tuple[str, str]], set[str]]]) -> None:
    depth_counts = Counter([len(path) for _, path in elements.values()])

    deepest_element = max(elements, key=lambda el: len(elements[el][1]))
    print(f"Deepest element: {deepest_element} ({len(elements[deepest_element][1])} deep)")

    most_common_depth, num_elements = depth_counts.most_common()[0]
    print(f"Most elements at depth {most_common_depth} ({num_elements} elements)")

    plt.bar(*zip(*depth_counts.items()))
    plt.savefig("stats.png")


if __name__ == "__main__":
    main()
