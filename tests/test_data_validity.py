import json
from pathlib import Path
from pprint import pformat

PROJECT_ROOT = Path(__file__).parents[1].absolute()
ELEMENTS_JSON = PROJECT_ROOT / "data" / "elements.json"
RECIPES_JSON = PROJECT_ROOT / "data" / "recipes.json"

recipes = {
    frozenset([recipe["first"], recipe["second"]]): recipe["result"]
    for recipe in json.load(RECIPES_JSON.open("r", encoding="UTF-8"))["recipes"]
}
elements = {element["text"] for element in json.load(ELEMENTS_JSON.open("r", encoding="UTF-8"))["elements"]}


def test_elements_have_been_made() -> None:
    produced_by_recipe_elements = set(recipes.values()) | {"Water", "Wind", "Fire", "Earth"}
    elements_not_produced: list[str] = []
    for element in elements:
        if element not in produced_by_recipe_elements:
            elements_not_produced.append(element)

    assert not elements_not_produced, pformat(elements_not_produced)


def test_if_made_using_nothing() -> None:
    elements_made_using_nothing: list[str] = []
    for ingredients, result in recipes.items():
        if "Nothing" in ingredients:
            elements_made_using_nothing.append(result)

    assert not elements_made_using_nothing, pformat(elements_made_using_nothing)


def test_ingredients_have_been_made() -> None:
    produced_elements = {"Water", "Earth", "Wind", "Fire"}
    ingredients_not_produced: list[str] = []
    for ingredients, result in recipes.items():
        if not all(i in produced_elements for i in ingredients):
            first, second = list(ingredients)
            if first not in produced_elements:
                ingredients_not_produced.append(first)
            if second not in produced_elements:
                ingredients_not_produced.append(second)

        produced_elements.add(result)

    assert not ingredients_not_produced, pformat(ingredients_not_produced)


def test_made_elements_are_saved() -> None:
    produced_elements = (set(recipes.values()) | {"Water", "Wind", "Fire", "Earth"}) - {"Nothing"}
    elements_not_saved: list[str] = []
    for element in produced_elements:
        if element not in elements:
            elements_not_saved.append(element)

    assert not elements_not_saved, pformat(elements_not_saved)


def test_nothing_not_in_elements() -> None:
    assert not "Nothing" in elements


def test_no_duplicate_recipes() -> None:
    # in case of an off-by-one error here, make sure that recipes.json ends with hex 7d
    # (viewing the file as hex, using e.g. xxd)
    assert len(recipes) == sum(1 for _ in RECIPES_JSON.open("r", encoding="UTF-8")) - 4
