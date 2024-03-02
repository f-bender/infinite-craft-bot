import json
from collections import OrderedDict
from dataclasses import asdict
from pathlib import Path
from pprint import pformat
from typing import Iterable

import pandas as pd

from infinite_craft_bot.globals import PROJECT_ROOT
from infinite_craft_bot.persistence.common import DataError, Element, ElementPath, FileRepository

# the number of digits that the file names have (3 -> "000.csv", "001.csv", ...)
NUM_PAGINATION_DIGITS = 3


class PaginatedCsvRepository(FileRepository):
    def __init__(self, data_dir: Path = PROJECT_ROOT / "data" / "csv", write_access: bool = False) -> None:
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

        self.recipes_dir = data_dir / "recipes"
        self.elements_dir = data_dir / "elements"
        self.elements_paths_dir = data_dir / "elements_paths"

        self.current_recipes_file = self._sorted_pagination_files(self.recipes_dir)[-1]
        self.current_elements_file = self._sorted_pagination_files(self.elements_dir)[-1]

    @staticmethod
    def _sorted_pagination_files(dir: Path) -> list[Path]:
        files = sorted(dir.iterdir(), key=lambda path: path.name)

        if (filenames := [file.name for file in files]) != [
            f"{i:>0{NUM_PAGINATION_DIGITS}}.csv" for i in range(len(files))
        ]:
            raise DataError(f"Corrupted pagination! Found files {filenames} in directory '{dir.name}'!")

        return files

    @property
    def reserved_paths(self) -> tuple[Path, ...]:
        return (self.recipes_dir, self.elements_dir, self.elements_paths_dir)

    def load_recipes(self) -> OrderedDict[frozenset[str], str]:
        recipes_df = pd.concat(pd.read_csv(file) for file in self._sorted_pagination_files(self.recipes_dir))

        result = OrderedDict(
            (frozenset((recipe["first"], recipe["second"])), recipe["result"]) for _, recipe in recipes_df.iterrows()
        )

        if len(result) != len(recipes_df):
            raise DataError(
                f"{self.recipes_dir} contains duplicated recipes:\n" + pformat(self._find_duplicate_recipes(recipes_df))
            )

        return result

    @staticmethod
    def _find_duplicate_recipes(recipes_df: pd.DataFrame) -> list[dict[str, str]]:
        # not in dict -> not seen yet
        # value False -> seen once, not yet added to duplicates list
        # value True -> seen more than once, is already added to duplicates list
        seen: dict[frozenset[str], bool] = {}
        duplicates = []
        for _, recipe in recipes_df.iterrows():
            recipe_frozenset = frozenset((recipe["first"], recipe["second"]))
            match seen.get(recipe_frozenset):
                case None:
                    seen[recipe_frozenset] = False
                case False:
                    duplicates.append(recipe)
                    seen[recipe_frozenset] = True

        return duplicates

    def load_elements(self) -> set[Element]:
        elements_df = pd.concat(pd.read_csv(file) for file in self._sorted_pagination_files(self.elements_dir))

        if (duplicate_idxs := elements_df.duplicated("text")).any():
            raise DataError(
                f"{self.elements_dir} contains duplicated elements:\n" + elements_df[duplicate_idxs].to_string()
            )

        return {
            Element(text=element["text"], emoji=element["emoji"], discovered=element["discovered"])
            for _, element in elements_df.iterrows()
        }

    # TODO the rest from here

    def load_elements_paths(self) -> dict[str, ElementPath]:
        with self.elements_paths_json.open("r", encoding="UTF-8") as f:
            return {
                element: ElementPath(ancestors=props["anc"], path=props["path"])
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

        self._add_item(self.recipes_json, (first, second, result))

    def _add_item(self, csv_file: Path, item: Iterable[str]) -> None:
        with csv_file.open("a", encoding="UTF-8") as f:
            f.write(",".join(f'"{token}"' if "," in token else token for token in item) + "\n")
