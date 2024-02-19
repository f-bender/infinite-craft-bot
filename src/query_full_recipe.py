from dataclasses import dataclass
import json
from pathlib import Path
from typing import NoReturn
from rich import print


PROJECT_ROOT = Path(__file__).parents[1].absolute()

ELEMENTS_PATHS_JSON = PROJECT_ROOT / "data" / "elements_paths.json"

ELEMENT_ANCESTORS = {
    element: val["anc"] for element, val in json.load(ELEMENTS_PATHS_JSON.open("r", encoding="UTF-8")).items()
}


@dataclass(slots=True, frozen=True)
class Operation:
    first: str
    second: str
    result: str


def query_full_recipe(element: str) -> list[Operation]:
    if element not in ELEMENT_ANCESTORS:
        raise ValueError("Unknown element!")

    ancestors = ELEMENT_ANCESTORS[element]
    if ancestors is None:
        return []

    first, second = ELEMENT_ANCESTORS[element]
    return list(dict.fromkeys(query_full_recipe(first) + query_full_recipe(second))) + [
        Operation(first=first, second=second, result=element)
    ]


def print_full_recipe(operations: list[Operation]) -> None:
    if not operations:
        print("[bold]It's a root element!")
        return

    steps = len(operations)
    print(f"[bold]It takes {steps} step{'s' if steps > 1 else ''} to craft [green]{operations[-1].result}[/green]:")

    first_max_length = max(len(op.first) for op in operations)
    second_max_length = max(len(op.second) for op in operations)

    for operation in operations:
        print(f"{operation.first:>{first_max_length}} + {operation.second:<{second_max_length}} = {operation.result}")


def main() -> NoReturn:
    while True:
        print("\n[yellow]Enter an element to get its recipe:", end=" ")
        element = input().strip()
        print()

        try:
            operations = query_full_recipe(element)
        except ValueError as e:
            try:
                operations = query_full_recipe(element.title())
            except ValueError as e:
                print(e)
                continue

        print_full_recipe(operations)


if __name__ == "__main__":
    main()
