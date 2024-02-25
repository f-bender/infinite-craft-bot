from io import BytesIO
import os
from pathlib import Path
import json
from collections import OrderedDict
from dataclasses import asdict, dataclass
from typing import Any, Iterable, Optional

import fasteners

from infinite_craft_bot.globals import PROJECT_ROOT


# NOTE: From a clean architecture standpoint, these classes should be defined in the application core, not in the
# persistence module. But for now, this is a shortcut I'm taking.
@dataclass(slots=True, frozen=True)
class ElementPath:
    ancestors: Optional[tuple[str, str]]
    path: set[str]


@dataclass(slots=True, frozen=True)
class Element:
    text: str
    emoji: str
    discovered: bool


class WriteAccessLocked(Exception):
    pass


class NoWriteAccess(Exception):
    pass


class FileRepository:

    def __init__(self, data_dir: Path = PROJECT_ROOT / "data", write_access: bool = False) -> None:
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
        self.data_dir = data_dir
        self.recipes_json = data_dir / "recipes.json"
        self.elements_json = data_dir / "elements.json"
        self.elements_paths_json = data_dir / "elements_paths.json"

        self.lockfile = self.data_dir / ".lock"
        self.lock = fasteners.InterProcessLock(self.lockfile)

        if write_access:
            if not self.lock.acquire(blocking=False):
                raise WriteAccessLocked()

    @property
    def has_write_access(self) -> bool:
        return self.lock.acquired

    def acquire_write_access(self) -> bool:
        if not self.lock.acquired:
            return self.lock.acquire(blocking=False)
        return True

    def release_write_access(self) -> None:
        if self.lock.acquired:
            self.lock.release()

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
            return OrderedDict(
                (frozenset([recipe["first"], recipe["second"]]), recipe["result"]) for recipe in json.load(f)["recipes"]
            )

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
                element: ElementPath(ancestors=props["anc"], path=props["path"])
                for element, props in json.load(f).items()
            }

    def save_element_paths(self, elements_paths: dict[str, ElementPath]) -> None:
        """This will overwrite the current elements_paths json file."""
        with self.elements_json.open("w", encoding="UTF-8") as f:
            json.dump(
                {
                    element_name: {"anc": element_path.ancestors, "path": element_path.path}
                    for element_name, element_path in elements_paths.items()
                },
                f,
                ensure_ascii=False,
                indent=4,
            )

    def save_arbitrary_binary_file(
        self, content: BytesIO, filename: str, subdirs: Optional[Iterable[str]] = None
    ) -> None:
        file_path = self.data_dir
        for subdir in subdirs or []:
            file_path = file_path / subdir

        file_path = file_path / filename
        if file_path in (self.elements_json, self.elements_paths_json, self.recipes_json):
            raise ValueError(f"The filename '{filename}' is not allowed as it's used internally!")

        with file_path.open("wb") as f:
            f.write(content.getvalue())

    def add_element(self, element: Element) -> None:
        if not self.lock.acquired:
            raise NoWriteAccess()

        self._add_item(self.elements_json, asdict(element))

    def add_recipe(self, ingredients: frozenset[str], result: str) -> None:
        if not self.lock.acquired:
            raise NoWriteAccess()

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
