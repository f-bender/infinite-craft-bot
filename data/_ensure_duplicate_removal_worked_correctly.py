import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[1].absolute()

RECIPES_JSON = PROJECT_ROOT / "data" / "recipes.json"
UNIQUE_RECIPES_JSON = PROJECT_ROOT / "data" / "recipes_unique.json"

recipes = [
    frozenset([recipe["first"], recipe["second"]])
    for recipe in json.load(RECIPES_JSON.open("r", encoding="UTF-8"))["recipes"]
]

recipes_unique = [
    frozenset([recipe["first"], recipe["second"]])
    for recipe in json.load(UNIQUE_RECIPES_JSON.open("r", encoding="UTF-8"))["recipes"]
]


def remove_duplicates(l):
    uniq = set()
    r = []
    for elem in l:
        if elem in uniq:
            continue
        uniq.add(elem)
        r.append(elem)
    return r

print(len(recipes))
print(len(recipes_unique))

recipes_without_duplicates = remove_duplicates(recipes)
recipes_unique_without_duplicates = remove_duplicates(recipes_unique)

print(len(recipes_without_duplicates))
print(len(recipes_unique_without_duplicates))

assert remove_duplicates(recipes) == remove_duplicates(recipes_unique)
