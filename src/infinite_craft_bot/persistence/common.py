from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass
from io import BytesIO, StringIO
from pathlib import Path
from typing import Collection, Iterable, Optional

import fasteners


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


class DataError(Exception):
    pass


class FileRepository(ABC):

    def __init__(self, data_dir: Path, write_access: bool = False) -> None:
        self.data_dir = data_dir

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

    @property
    @abstractmethod
    def reserved_paths(self) -> Collection[Path]: ...

    @abstractmethod
    def load_recipes(self) -> OrderedDict[frozenset[str], str]: ...

    @abstractmethod
    def load_elements(self) -> set[Element]: ...

    @abstractmethod
    def load_elements_paths(self) -> dict[str, ElementPath]: ...

    @abstractmethod
    def save_element_paths(self, elements_paths: dict[str, ElementPath]) -> None: ...

    def add_element(self, element: Element) -> None:
        if not self.has_write_access:
            raise NoWriteAccess()

        self._add_element(element)

    @abstractmethod
    def _add_element(self, element: Element) -> None: ...

    def add_recipe(self, ingredients: frozenset[str], result: str) -> None:
        if not self.has_write_access:
            raise NoWriteAccess()

        self._add_recipe(ingredients=ingredients, result=result)

    @abstractmethod
    def _add_recipe(self, ingredients: frozenset[str], result: str) -> None: ...

    def save_arbitrary_data_to_file(
        self, content: BytesIO | StringIO, filename: str, subdirs: Optional[Iterable[str]] = None
    ) -> None:
        # NOTE we don't require write access here because this is a single operation that overwrites the entire file,
        # i.e. there is basically no risk of multiple threads/processes stepping on each other's feet
        file_path = self.data_dir
        for subdir in subdirs or []:
            file_path = file_path / subdir

        file_path = file_path / filename
        if any(file_path.is_relative_to(reserved_path) for reserved_path in self.reserved_paths):
            raise ValueError(f"The filename '{filename}' is not allowed as it's used internally!")

        file_path.parent.mkdir(parents=True, exist_ok=True)

        with file_path.open("wb" if isinstance(content, BytesIO) else "w") as f:
            f.write(content.getvalue())

    def load_arbitrary_data_from_file(self, filename: str, subdirs: Optional[Iterable[str]] = None) -> str:
        """Raises an error if the file doesn't exist."""
        file_path = self.data_dir
        for subdir in subdirs or []:
            file_path = file_path / subdir
        file_path = file_path / filename

        return file_path.open("r").read()
