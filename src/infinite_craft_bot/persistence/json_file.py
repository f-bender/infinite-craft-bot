import json
import os
from collections import OrderedDict
from dataclasses import asdict
from pathlib import Path
from pprint import pformat
from typing import Any

from infinite_craft_bot.globals import PROJECT_ROOT
from infinite_craft_bot.persistence.common import DataError, Element, ElementPath, FileRepository


class JsonRepository(FileRepository):
    def __init__(self, data_dir: Path = PROJECT_ROOT / "data" / "json", write_access: bool = False) -> None:
        """Repository of elements and recipes, saved as files.

        Args:
            data_dir: Diretory to use as the location for all saved files.
            write_access: Whether write access to the elements and recipes files is required. Additions to these files
                are ensured to only happen in one process, such that another process doesn't accidentally start and
                write to those files at the same time, resulting in an invalid state, or potentially even a corrupted
                json.

        Raises:
            WriteAccessLocked: If write_access is requested, but can't be granted because another instance (or process)
                already has write access.
        """
        super().__init__(data_dir, write_access)

        self.recipes_json = data_dir / "recipes.json"
        self.elements_json = data_dir / "elements.json"
        self.elements_paths_json = data_dir / "elements_paths.json"

    @property
    def reserved_paths(self) -> tuple[Path, ...]:
        return (self.recipes_json, self.elements_json, self.elements_paths_json)

    def load_recipes(self) -> OrderedDict[frozenset[str], str]:
        """Returns the recipes, as an ordered dict, loaded from a json file.

        Keys are frozensets of the both elements that are being combined. The frozenset may contain only one element,
        meaning that the item is being combined with itself.

        Structure of the underlying json file:
        {
            "recipes": [
                {"first": "<first-element-name>", "second": "<second-element-name>", "result": "<result-element-name>"},
                {"first": "<first-element-name>", "second": "<second-element-name>", "result": "<result-element-name>"},
                ...
                {"first": "<first-element-name>", "second": "<second-element-name>", "result": "<result-element-name>"},
                {"first": "<first-element-name>", "second": "<second-element-name>", "result": "<result-element-name>"}
            ]
        }
        """
        with self.recipes_json.open("r", encoding="UTF-8") as f:
            raw_recipes_list = json.load(f)["recipes"]

        result = OrderedDict(
            (frozenset((recipe["first"], recipe["second"])), recipe["result"]) for recipe in raw_recipes_list
        )

        if len(result) != len(raw_recipes_list):
            raise DataError(
                f"{self.recipes_json} contains duplicated recipes:\n"
                + pformat(self._find_duplicate_recipes(raw_recipes_list))
            )

        return result

    @staticmethod
    def _find_duplicate_recipes(raw_recipes_list: list[dict[str, str]]) -> list[dict[str, str]]:
        # not in dict -> not seen yet
        # value False -> seen once, not yet added to duplicates list
        # value True -> seen more than once, is already added to duplicates list
        seen: dict[frozenset[str], bool] = {}
        duplicates = []
        for recipe in raw_recipes_list:
            recipe_frozenset = frozenset((recipe["first"], recipe["second"]))
            match seen.get(recipe_frozenset):
                case None:
                    seen[recipe_frozenset] = False
                case False:
                    duplicates.append(recipe)
                    seen[recipe_frozenset] = True

        return duplicates

    # TODO: check that there are no duplicate elements (similar to load_recipes) (simply check name ("text" field))
    def load_elements(self) -> set[Element]:
        """Returns the elements, as a set, loaded from a json file.

        The items of the set are `Element`s, having a "text" (name of the element), "emoji" (emoji representing the
        element), and "discovered" (whether this element was discovered by us) property.

        Structure of the underlying json file:
        {
            "elements": [
                {"text": "<element-name>", "emoji": "<element-emoji>", "discovered": true/false},
                {"text": "<element-name>", "emoji": "<element-emoji>", "discovered": true/false},
                ...
                {"text": "<element-name>", "emoji": "<element-emoji>", "discovered": true/false},
                {"text": "<element-name>", "emoji": "<element-emoji>", "discovered": true/false}
            ]
        }
        """
        with self.elements_json.open("r", encoding="UTF-8") as f:
            return {
                Element(text=element["text"], emoji=element["emoji"], discovered=element["discovered"])
                for element in json.load(f)["elements"]
            }

    def load_elements_paths(self) -> dict[str, ElementPath]:
        with self.elements_paths_json.open("r", encoding="UTF-8") as f:
            return {
                element: ElementPath(ancestors=props["anc"], path=set(props["path"]))
                for element, props in json.load(f).items()
            }

    def save_element_paths(self, elements_paths: dict[str, ElementPath]) -> None:
        """This will overwrite the current elements_paths json file."""
        with self.elements_paths_json.open("w", encoding="UTF-8") as f:
            json.dump(
                {
                    element_name: {"anc": element_path.ancestors, "path": list(element_path.path)}
                    for element_name, element_path in elements_paths.items()
                },
                f,
                ensure_ascii=False,
                indent=4,
            )

    def _add_element(self, element: Element) -> None:
        self._add_item(self.elements_json, asdict(element))

    def _add_recipe(self, ingredients: frozenset[str], result: str) -> None:
        match len(ingredients):
            case 1:
                (first,) = (second,) = ingredients
            case 2:
                first, second = ingredients
            case _:
                raise ValueError("Ingredients needs to have 1 or 2 elements!")

        self._add_item(self.recipes_json, {"first": first, "second": second, "result": result})

    def _add_item(self, json_file: Path, item: dict[str, Any]) -> None:
        """Adds the provided (json-serializable) item to the provided json file.

        The json file is assumed to have this structure:
        {
            "<some-name>": [
                {"prop_1": "val_1", ..., "prop_n": "val_n"},
                {"prop_1": "val_1", ..., "prop_n": "val_n"},
                ...
                {"prop_1": "val_1", ..., "prop_n": "val_n"},
                {"prop_1": "val_1", ..., "prop_n": "val_n"}
            ]
        }
        where `item` then also has the structure {"prop_1": "val_1", ..., "prop_n": "val_1"}.

        Note that the structure and the formatting of the file has to match exactly, since the item is inserted at a
        location which is a hard-coded amount of characters before the end of the file.
        """
        with json_file.open("r+", encoding="UTF-8") as f:
            # move cursor to the closing "}" of the last element
            f.seek(0, os.SEEK_END)
            f.seek(f.tell() - 10)

            # remove everything after this point
            f.truncate()

            # add the new element, and re-add the closing parentheses
            new_element_str = json.dumps(item, ensure_ascii=False)
            f.write(f",\n        {new_element_str}\n    ]\n}}")
