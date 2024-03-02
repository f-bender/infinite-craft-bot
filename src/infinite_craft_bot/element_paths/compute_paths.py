import logging
from itertools import count
from typing import Iterable, OrderedDict

import pandas as pd

from infinite_craft_bot.element_paths.path_stats import compute_and_save_stats
from infinite_craft_bot.persistence import ElementPath, FileRepository

#! This script most likely contains a bug: at commit 'e7a9ce4', Jesus Shark was determined to be the deepest element
#! at depth 400, and *later*, at commit 'f5c7c69', after more recipes where explored, Jesus Shark was determined to be
#! the deepest element at depth 404; i.e. new recipes increased the depth of Jesus Shark,
#! which should never be possible!
# * The good news: overall, the stats seem reasonable, in each iteration the average depths goes down.
# * It just looks like iterating like this, until no more changes occur, doesn't guarantee the optimal depth to be found.
# * (Which I didn't expect)

logger = logging.getLogger(__name__)


def compute_elements_paths(
    recipes: OrderedDict[frozenset[str], str], root_elements: Iterable[str] = ("Water", "Fire", "Wind", "Earth")
) -> dict[str, ElementPath]:
    elements_paths: dict[str, ElementPath] = {element: ElementPath(None, set()) for element in root_elements}

    # convert the dict items into their three elements first, second, result *once* in the beginning, to avoid having
    # to do this during every iteration (purely for efficiency reasons)
    recipes_as_tuples: list[tuple[str, str, str]] = []
    for ingredients, result in recipes.items():
        match len(ingredients):
            case 1:
                (first,) = (second,) = ingredients
            case _:
                first, second = ingredients
        recipes_as_tuples.append((first, second, result))

    for i in count():
        logger.info(f"Iteration {i}...")
        modified = False

        for first, second, result in recipes_as_tuples:
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

        logger.info(
            f"Current stats:\n{pd.DataFrame([len(el_path.path) for el_path in elements_paths.values()]).describe()}"
        )
        if not modified:
            break

    return elements_paths


def compute_and_save_elements_paths(repository: FileRepository, save_stats: bool = False) -> None:
    recipes = repository.load_recipes()
    elements_paths = compute_elements_paths(recipes)
    repository.save_element_paths(elements_paths)

    if save_stats:
        compute_and_save_stats(elements_paths=elements_paths, repository=repository)
