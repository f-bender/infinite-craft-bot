"""Quick and dirty script to remove duplicate recipes. 

Should not be required anymore since I take care not to save duplicate recipes anymore.
"""

from pathlib import Path
import json

PROJECT_ROOT = Path(__file__).parents[1].absolute()

RECIPES_JSON = PROJECT_ROOT / "data" / "recipes.json"
UNIQUE_RECIPES_JSON = PROJECT_ROOT / "data" / "recipes_unique.json"

seen_recipes: set[frozenset[str]] = set()
lines: list[str] = []
with RECIPES_JSON.open("r", encoding="UTF-8") as f:
    for line in f:
        if line in ("{\n", '    "recpies": [\n', "    ]\n", "}"):
            lines.append(line)
            continue

        if not line.startswith(" "* 8 + '{"first": "') and line.endswith('"},\n'):
            print(f"irregular line: '{line}'")

        recipe_dict = json.loads(line.strip().rstrip(","))
        recipe = frozenset([recipe_dict["first"], recipe_dict["second"]])
        if recipe in seen_recipes:
            print(f"removing duplicate of {recipe}")
            continue

        seen_recipes.add(recipe)
        lines.append(line)

print(len(lines) - 4)

with UNIQUE_RECIPES_JSON.open("w", encoding="UTF-8") as f:
    f.write("".join(lines))
