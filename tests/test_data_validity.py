from pprint import pformat

from infinite_craft_bot.persistence.csv_file import PaginatedCsvRepository

REPOSITORY = PaginatedCsvRepository()

RECIPES = REPOSITORY.load_recipes()
ELEMENTS = {element.text for element in REPOSITORY.load_elements()}


def test_elements_have_been_made() -> None:
    produced_by_recipe_elements = set(RECIPES.values()) | {"Water", "Wind", "Fire", "Earth"}
    elements_not_produced: list[str] = []
    for element in ELEMENTS:
        if element not in produced_by_recipe_elements:
            elements_not_produced.append(element)

    assert not elements_not_produced, pformat(elements_not_produced)


def test_if_made_using_nothing() -> None:
    elements_made_using_nothing: list[str] = []
    for ingredients, result in RECIPES.items():
        if "Nothing" in ingredients:
            elements_made_using_nothing.append(result)

    assert not elements_made_using_nothing, pformat(elements_made_using_nothing)


def test_ingredients_have_been_made() -> None:
    produced_elements = {"Water", "Earth", "Wind", "Fire"}
    ingredients_not_produced: list[str] = []
    for ingredients, result in RECIPES.items():
        if not all(i in produced_elements for i in ingredients):
            first, second = list(ingredients)
            if first not in produced_elements:
                ingredients_not_produced.append(first)
            if second not in produced_elements:
                ingredients_not_produced.append(second)

        produced_elements.add(result)

    assert not ingredients_not_produced, pformat(ingredients_not_produced)


def test_made_elements_are_saved() -> None:
    produced_elements = (set(RECIPES.values()) | {"Water", "Wind", "Fire", "Earth"}) - {"Nothing"}
    elements_not_saved: list[str] = []
    for element in produced_elements:
        if element not in ELEMENTS:
            elements_not_saved.append(element)

    assert not elements_not_saved, pformat(elements_not_saved)


def test_nothing_not_in_elements() -> None:
    assert not "Nothing" in ELEMENTS
