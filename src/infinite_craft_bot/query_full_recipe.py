from dataclasses import dataclass
from functools import reduce
from itertools import chain, combinations
from typing import Callable, Collection, Iterable, Optional

from rich import print

from infinite_craft_bot.persistence.common import FileRepository


@dataclass(slots=True, frozen=True)
class Operation:
    first: str
    second: str
    result: str


def all_subsets[T](elements: Collection[T]) -> Iterable[set[T]]:
    """Returns all subsets of the input, of all sizes (from 0 to N, where N is the size of the input).

    The subsets are guaranteed to be returned ordered ascending by size, i.e. the first element is the empty set
    (`set()`), and the last element is the set of all elements (`set(elements)`).
    """
    return (set(x) for x in chain.from_iterable(combinations(elements, n) for n in range(len(elements) + 1)))


class FullRecipeQuery:
    def __init__(self, repository: FileRepository) -> None:
        self.element_ancestors = {element: val.ancestors for element, val in repository.load_elements_paths().items()}

    def query_full_recipe(self, element: str) -> list[list[Operation]]:
        """Returns the full recipe to create the given element, as a list of operations.

        If the exact element name doens't exist, some variations are tried instead (changes in capitalization, or
        replacing similar-looking characters).
        If even given those variations, the element isn't found, None is returned.

        An operation is made out of a first element, a second element, and a result element.
        """
        # try to find a fitting name, even if the *exact* requested element doesn't exist
        element_names = {name for name in self.name_variations(element) if name in self.element_ancestors}

        return [self._query_full_recipe(element_name) for element_name in element_names]

    @staticmethod
    def name_variations(element_name: str) -> Iterable[str]:
        transformations: list[Callable[[str], str]] = [
            lambda s: s.replace("'", "’"),
            lambda s: s.replace(" ", ""),
            str.title,
            str.upper,
            str.lower,
            # str.title also capitalizes after special character
            lambda s: " ".join(word.capitalize() for word in s.split()),
        ]

        return (
            reduce(lambda name, func: func(name), transforms, element_name)
            for transforms in all_subsets(transformations)
        )

    def _query_full_recipe(self, element: str) -> list[Operation]:
        if element not in self.element_ancestors:
            raise ValueError("Unknown element!")

        ancestors = self.element_ancestors[element]
        if ancestors is None:
            return []

        first, second = ancestors
        return list(dict.fromkeys(self._query_full_recipe(first) + self._query_full_recipe(second))) + [
            Operation(first=first, second=second, result=element)
        ]


# TODO basically make this a function of the UI class
def print_full_recipes(operation_lists: list[list[Operation]]) -> None:
    if not operation_lists:
        print("Unknown element!")
        return

    if len(operation_lists) > 1:
        print(
            "[bold]There exist multiple variations of this element: "
            + ", ".join(f"[green]{operations[-1].result}[/green]" for operations in operation_lists)
        )
        print()

    for idx, operations in enumerate(operation_lists):
        if idx != 0:
            print()

        if not operations:
            print(f"[bold]{operations[-1].result} is a root element!")
            continue

        steps = len(operations)
        print(f"[bold]It takes {steps} step{'s' if steps > 1 else ''} to craft [green]{operations[-1].result}[/green]:")

        first_max_length = max(len(op.first) for op in operations)
        second_max_length = max(len(op.second) for op in operations)

        for operation in operations:
            print(
                f"{operation.first:>{first_max_length}} + {operation.second:<{second_max_length}} = {operation.result}"
            )
