from itertools import count
from typing import Iterable, OrderedDict

import pandas as pd
from rich import print

from infinite_craft_bot.persistence import ElementPath, FileRepository


#! This script most likely contains a bug: at commit 'e7a9ce4', Jesus Shark was determined to be the deepest element
#! at depth 400, and *later*, at commit 'f5c7c69', after more recipes where explored, Jesus Shark was determined to be
#! the deepest element at depth 404; i.e. new recipes increased the depth of Jesus Shark,
#! which should never be possible!
# * The good news: overall, the stats seem reasonable, in each iteration the average depths goes down.
# * It just looks like iterating like this, until no more changes occur, doesn't guarantee the optimal depth to be found.
# * (Which I didn't expect)


def compute_elements_paths(
    recipes: OrderedDict[frozenset[str], str], root_elements: Iterable[str] = ("Water", "Fire", "Wind", "Earth")
) -> dict[str, ElementPath]:

    # TODO transfer elements_paths and/or recipes to more efficient representation, then measure the timing difference
    # (Measure-Command { <command> } in powershell)
    # get on par with (or reasonably close to) the previous implementation at src/compute_element_paths.py before deleting it
    # (right now it's ~16s vs ~14s)
    elements_paths: dict[str, ElementPath] = {element: ElementPath(None, set()) for element in root_elements}

    # TODO use UI class instead of print, or just use logging and consider this information which doesn't need to be shown to the user
    # (probably the latter)
    for i in count():
        print(f"Iteration {i}...")
        modified = False

        for ingredients, result in recipes.items():
            match len(ingredients):
                case 1:
                    (first,) = (second,) = ingredients
                case _:
                    first, second = ingredients

            new_path = elements_paths[first].path | elements_paths[second].path | {result}
            if result in elements_paths:
                # if this path is faster, set it as the path to this element
                if len(new_path) < len(elements_paths[result].path):
                    new_ancestors = (first, second)
                    elements_paths[result] = ElementPath(new_ancestors, new_path)
                    modified = True
            else:
                new_ancestors = (first, second)
                elements_paths[result] = ElementPath(new_ancestors, new_path)
                modified = True

        print("Stats:")
        print(pd.DataFrame([len(el_path.path) for el_path in elements_paths.values()]).describe())
        print()
        if not modified:
            print("Done!")
            break

    return elements_paths


# TODO better naming
def compute_and_save_elements_paths(repository: FileRepository) -> None:
    recipes = repository.load_recipes()
    elements_paths = compute_elements_paths(recipes)
    repository.save_element_paths(elements_paths)
