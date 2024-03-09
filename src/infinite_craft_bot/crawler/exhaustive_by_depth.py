import bisect
import io
import logging
import threading
from contextlib import nullcontext
from typing import Optional, cast

from infinite_craft_bot.crawler.common import Crawler
from infinite_craft_bot.persistence.common import Element

logger = logging.getLogger(__name__)

#! Note: this seems to not be 100% thread-safe; I have encountered the same element being added twice

class ExhaustiveCrawler(Crawler):
    def init_locks(self) -> None:
        """Initialization of locks executed in __init__()."""
        # in case multiple locks need to be acquired, they should always be acquired in the order in which they are
        # listed here (which happens to be longest name to shortest name)!
        self.next_craft_combination_lock: Optional[threading.Lock] = None
        self.elements_repository_lock: Optional[threading.Lock] = None
        self.recipes_repository_lock: Optional[threading.Lock] = None
        self.elements_to_path_lock: Optional[threading.Lock] = None
        self.sorted_elements_lock: Optional[threading.Lock] = None
        self.recipes_lock: Optional[threading.Lock] = None

    def create_locks(self) -> None:
        """Creation of locks that is only done when crawl_multithreaded() is called."""
        self.next_craft_combination_lock = threading.Lock()
        self.elements_repository_lock = threading.Lock()
        self.recipes_repository_lock = threading.Lock()
        self.elements_to_path_lock = threading.Lock()
        self.sorted_elements_lock = threading.Lock()
        self.recipes_lock = threading.Lock()

    def init_data(self) -> None:
        """Initialization of in-memory data this class keeps track of, executed in __init__()."""
        elements = self.repository.load_elements()

        _element_paths = self.repository.load_elements_paths()
        self.elements_to_path: dict[str, set[str]] = {
            element.text: set(_element_paths[element.text].path) for element in elements
        }
        self.sorted_elements = [element.text for element in elements]
        # sort primarily by depth, then (if depth is equal) by element name (alphabetically)
        # -> fully deterministic order
        self.sorted_elements.sort(key=lambda el: (len(self.elements_to_path[el]), el))

        # not in the dict: un-explored
        # in the dict with value False: committed to (by one of the threads), but result not yet available
        # in the dict with value True: fully explored
        self.recipes: dict[frozenset[str], bool] = {ingredients: True for ingredients in self.repository.load_recipes()}  # type: ignore

        # every combination of elements beneath this index tuple has been explored (indices into sorted elements array)
        self.next_craft_combination: tuple[int, int] = 0, 0
        try:
            self.next_craft_combination = cast(
                tuple[int, int],
                tuple(
                    int(x)
                    for x in self.repository.load_arbitrary_data_from_file(
                        subdirs=["exhaustive"], filename="next_craft_combination.txt"
                    )
                    .strip()
                    .split(",")
                ),
            )
        except Exception as e:
            logger.warning(f"Can't load last crafted combination: {e}\nStarting from (0, 0)")

        # TODO add a test which makes sure that the saved "next craft combination" is actually what comes out if
        #      next_craft_combination is set to 0, 0, and then update_next_craft_combination is applied

        old_next_craft_combination = self.next_craft_combination
        # no need to use locks here since this happens single-threadedly (setup)
        self.update_next_craft_combiantion()

        if self.next_craft_combination != old_next_craft_combination:
            logger.warning(
                f"Found already explored recipes leading to an increase of next_craft_combination from "
                f"{old_next_craft_combination} up to {self.next_craft_combination} during initialization."
            )

    def update_next_craft_combiantion(self) -> None:
        updated = False
        while self.recipes.get(frozenset(self.sorted_elements[x] for x in self.next_craft_combination)) is True:
            updated = True
            self.next_craft_combination = self.increment_dual_index_tuple(self.next_craft_combination)
        
        if not updated:
            return

        depth = len(self.elements_to_path[self.sorted_elements[self.next_craft_combination[0]]])

        logger.debug(f"next_craft_combination updated to {self.next_craft_combination} (depth {depth})")

        self.repository.save_arbitrary_data_to_file(
            content=io.StringIO(",".join(str(x) for x in self.next_craft_combination)),
            subdirs=["exhaustive"],
            filename="next_craft_combination.txt",
        )

    def sample_elements(self) -> tuple[str, str]:
        with (
            self.next_craft_combination_lock or nullcontext(),
            self.sorted_elements_lock or nullcontext(),
            self.recipes_lock or nullcontext(),
        ):
            current_index_to_try = self.next_craft_combination
            while True:
                first = self.sorted_elements[current_index_to_try[0]]
                second = self.sorted_elements[current_index_to_try[1]]

                ingredients = frozenset((first, second))
                if ingredients not in self.recipes:
                    self.recipes[ingredients] = False
                    break

                current_index_to_try = self.increment_dual_index_tuple(current_index_to_try)

        logger.debug(f"{first} + {second}")
        return first, second

    @staticmethod
    def increment_dual_index_tuple(dual_index_tuple: tuple[int, int]) -> tuple[int, int]:
        if dual_index_tuple[0] == dual_index_tuple[1]:
            return dual_index_tuple[0] + 1, 0

        return dual_index_tuple[0], dual_index_tuple[1] + 1

    def process_recipe(self, recipe: frozenset[str], result: str) -> None:
        """Process the recipe after a successful crafting request."""
        with (
            self.next_craft_combination_lock or nullcontext(),
            self.elements_to_path_lock or nullcontext(),
            self.sorted_elements_lock or nullcontext(),
            self.recipes_lock or nullcontext(),
        ):
            self.recipes[recipe] = True
            self.update_next_craft_combiantion()

        with self.recipes_repository_lock or nullcontext():
            self.repository.add_recipe(ingredients=recipe, result=result)

    def element_already_known(self, element_name: str) -> bool:
        with self.elements_to_path_lock or nullcontext():
            return element_name in self.elements_to_path

    def process_known_element(self, result_element: Element, first: str, second: str) -> None:
        with (
            self.elements_to_path_lock or nullcontext(),
            self.sorted_elements_lock or nullcontext(),
        ):
            new_element_path = self.elements_to_path[first] | self.elements_to_path[second] | {result_element.text}

            previous_depth = len(self.elements_to_path[result_element.text])
            new_depth = len(new_element_path)

            if new_depth < previous_depth:
                self.print_finding(
                    new_element=result_element,
                    depth=new_depth,
                    previous_depth=previous_depth,
                    first=first,
                    second=second,
                )
                self.elements_to_path[result_element.text] = new_element_path
                # sort again, such that the element moves to its new correct place in the list
                # (now that its path is shorter)
                self.sorted_elements.sort(key=lambda el: len(self.elements_to_path[el]))

    def process_new_element(self, element: Element, first: str, second: str) -> None:
        with self.elements_repository_lock or nullcontext():
            self.repository.add_element(element)

        # add at correct index (keeping it sorted) using bisection
        with self.elements_to_path_lock or nullcontext(), self.sorted_elements_lock or nullcontext():
            new_element_path = self.elements_to_path[first] | self.elements_to_path[second] | {element.text}
            self.elements_to_path[element.text] = new_element_path
            bisect.insort(
                self.sorted_elements,
                element.text,
                key=lambda el_name: (len(self.elements_to_path[el_name]), el_name),
            )

        # TODO: self.ui.print_finding(new_element=result_element, depth=len(new_element_path), first=first, second=second)
        self.print_finding(new_element=element, depth=len(new_element_path), first=first, second=second)
        # TODO/
