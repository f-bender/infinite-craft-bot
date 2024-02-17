import json
from pathlib import Path

HERE = Path(__file__).parent.absolute()
ELEMENTS_JSON = HERE / "elements.json"
RECIPES_JSON = HERE / "recipes.json"

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

recipes = {frozenset([recipe["first"], recipe["second"]]): recipe["result"] for recipe in load_elements(RECIPES_JSON)["recipes"]}
elements = {element["text"] for element in load_elements(ELEMENTS_JSON)["elements"]}

def check_elements_have_been_made():
    produced_elements = set(recipes.values()) | {"Water", "Wind", "Fire", "Earth"}
    for element in elements:
        if element not in produced_elements:
            print(element)

def check_if_made_using_nothing():
    for ingredidents, result in recipes.items():
        if "Nothing" in ingredidents:
            print(result)
            for i, r in recipes.items():
                if i == ingredidents or r in i:
                    continue
                if r == result:
                    break
            else:
                print("No other!")

def check_ingredients_have_been_made():
    produced_elements = {"Water", "Earth", "Wind", "Fire"}
    for ing, res in recipes.items():
        if not all(i in produced_elements for i in ing):
            first, second = list(ing)
            if first not in produced_elements:
                print(first)
            if second not in produced_elements:
                print(second)
        produced_elements.add(res)

# no outputs indicates everything is fine
print("made using nothing:")
check_if_made_using_nothing()
print()
print("ingredients have been made:")
check_ingredients_have_been_made()
print()
print("elements have been made:")
check_elements_have_been_made()