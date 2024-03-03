import ast
from collections import OrderedDict
from math import ceil
from pathlib import Path
from typing import Iterable

import pandas as pd  # type: ignore

from infinite_craft_bot.globals import PROJECT_ROOT
from infinite_craft_bot.persistence.common import DataError, Element, ElementPath, FileRepository

# the number of digits that the file names have (3 -> "000.csv", "001.csv", ...)
NUM_PAGINATION_DIGITS = 5
ITEMS_PER_FILE = 50_000


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
        # every line is one item, except for the first line (csv header) -> - 1
        self.num_recipes_in_current_file = sum(1 for _ in self.current_recipes_file.open("r", encoding="UTF-8")) - 1

        self.current_elements_file = self._sorted_pagination_files(self.elements_dir)[-1]
        # every line is one item, except for the first line (csv header) -> - 1
        self.num_elements_in_current_file = sum(1 for _ in self.current_elements_file.open("r", encoding="UTF-8")) - 1

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

        result = OrderedDict()

        def update_result(recipe_row: pd.Series) -> None:
            result[frozenset((recipe_row["first"], recipe_row["second"]))] = recipe_row["result"]

        recipes_df.apply(update_result, axis=1)  # type: ignore

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

        result = set()

        def update_result(element_row: pd.Series) -> None:
            result.add(
                Element(text=element_row["text"], emoji=element_row["emoji"], discovered=element_row["discovered"])
            )

        elements_df.apply(update_result, axis=1)  # type: ignore

        return result

    def load_elements_paths(self) -> dict[str, ElementPath]:
        elements_paths_df = pd.concat(
            pd.read_csv(file) for file in self._sorted_pagination_files(self.elements_paths_dir)
        )

        result = {}

        def update_result(element_path_row: pd.Series) -> None:
            result[element_path_row["element"]] = ElementPath(
                ancestors=(
                    ast.literal_eval(element_path_row["ancestors"])
                    if not pd.isna(element_path_row["ancestors"])
                    else None
                ),
                path=ast.literal_eval(element_path_row["path"]),
            )

        elements_paths_df.apply(update_result, axis=1)  # type: ignore

        return result

    def save_element_paths(self, elements_paths: dict[str, ElementPath]) -> None:
        """This will overwrite the current elements_paths files."""
        elements_paths_df = pd.DataFrame(
            [
                {"element": element, "ancestors": el_path.ancestors, "path": el_path.path}
                for element, el_path in elements_paths.items()
            ]
        )

        self.elements_paths_dir.mkdir(exist_ok=True)

        for page in range(ceil(len(elements_paths_df) / ITEMS_PER_FILE)):
            elements_paths_df[page * ITEMS_PER_FILE : (page + 1) * ITEMS_PER_FILE].to_csv(
                self.elements_paths_dir / f"{page:0>{NUM_PAGINATION_DIGITS}}.csv", index=False
            )

    def _add_element(self, element: Element) -> None:
        if self.num_elements_in_current_file >= ITEMS_PER_FILE:
            self.current_elements_file = (
                self.current_elements_file.parent
                / f"{int(self.current_elements_file.stem) + 1:0>{NUM_PAGINATION_DIGITS}}.csv"
            )
            with self.current_elements_file.open("w", encoding="UTF-8") as f:
                f.write("text,emoji,discovered\n")

            self.num_elements_in_current_file = 0

        self._add_item(self.current_elements_file, (element.text, element.emoji, str(element.discovered)))
        self.num_elements_in_current_file += 1

    def _add_recipe(self, ingredients: frozenset[str], result: str) -> None:
        if self.num_recipes_in_current_file >= ITEMS_PER_FILE:
            self.current_recipes_file = (
                self.current_recipes_file.parent
                / f"{int(self.current_recipes_file.stem) + 1:0>{NUM_PAGINATION_DIGITS}}.csv"
            )
            with self.current_recipes_file.open("w", encoding="UTF-8") as f:
                f.write("first,second,result\n")

            self.num_recipes_in_current_file = 0

        match len(ingredients):
            case 1:
                (first,) = (second,) = ingredients
            case 2:
                first, second = ingredients
            case _:
                raise ValueError("Ingredients needs to have 1 or 2 elements!")

        self._add_item(self.current_recipes_file, (first, second, result))
        self.num_recipes_in_current_file += 1

    def _add_item(self, csv_file: Path, item: Iterable[str]) -> None:
        with csv_file.open("a", encoding="UTF-8") as f:
            f.write(",".join(f'"{token}"' if "," in token else token for token in item) + "\n")
