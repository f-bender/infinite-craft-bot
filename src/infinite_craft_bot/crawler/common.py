import logging
import sys
import threading
from abc import ABC, abstractmethod
from contextlib import nullcontext
from typing import NoReturn, Optional

import rich

from infinite_craft_bot.api import ServerError, craft_items
from infinite_craft_bot.logging_helpers import LogElapsedTime
from infinite_craft_bot.persistence.common import Element, FileRepository, WriteAccessLocked

logger = logging.getLogger(__name__)


class Crawler(ABC):

    # TODO: maybe implement an abstract crawler class, that basically already has a template crawling loop, but provides
    # the ability to specify callbacks that are called at various points throughout the crawling loop (a lot like
    # pytorch lightning; I imagine it just like this video shows:
    # https://lightning.ai/docs/pytorch/stable/_static/fetched-s3-assets/pl_readme_gif_2_0.mp4 )
    # then low-depth, random, and high-depth are separate subclasses of crawler, just lite interactive and brute-force
    # * NOTE: this accepts some ugliness in the super-class, traded in for conciseness in the sub-classes

    def __init__(self, repository: FileRepository) -> None:
        # The repository itself is responsible for making sure that it is the only instance that has write access to its
        # underlying files. We as the crawler are responsible for making sure that we don't use its writing functions
        # concurrently.
        self.repository = repository
        # we need write access to add elements and repices to the repository
        if not self.repository.acquire_write_access():
            raise WriteAccessLocked()

        self.init_data()
        self.init_locks()

    def init_locks(self) -> None:
        """Initialization of locks executed in __init__()."""
        # in case multiple locks need to be acquired, they should always be acquired in the order in which they are
        # listed here (which happens to be longest name to shortest name)!
        self.elements_repository_lock: Optional[threading.Lock] = None
        self.recipes_repository_lock: Optional[threading.Lock] = None
        self.elements_list_lock: Optional[threading.Lock] = None
        self.elements_set_lock: Optional[threading.Lock] = None
        self.recipes_lock: Optional[threading.Lock] = None

    def create_locks(self) -> None:
        """Creation of locks that is only done when crawl_multithreaded() is called."""
        self.elements_repository_lock = threading.Lock()
        self.recipes_repository_lock = threading.Lock()
        self.elements_list_lock = threading.Lock()
        self.elements_set_lock = threading.Lock()
        self.recipes_lock = threading.Lock()

    def init_data(self) -> None:
        """Initialization of in-memory data this class keeps track of, executed in __init__()."""
        self.elements_list = [element.text for element in self.repository.load_elements()]
        self.elements_set = set(self.elements_list)
        self.recipes = set(self.repository.load_recipes())

    def crawl_multithreaded(self, num_threads: int, blocking: bool = True) -> None:
        if num_threads <= 1:
            raise ValueError("`num_threads` must be at least 2! To crawl single-threadedly, call `crawl()` directly.")

        self.create_locks()

        for _ in range(num_threads - int(blocking)):
            threading.Thread(target=self.crawl, daemon=True).start()

        if blocking:
            try:
                self.crawl()
            except KeyboardInterrupt:
                sys.exit(0)

        return None

    def crawl(self) -> None:
        logger.debug("Starting to crawl...")
        while True:
            with LogElapsedTime(log_func=logger.debug, label="Sampling"):
                first, second = self.sample_elements()

            tries = 0
            result_element: Optional[Element] = None
            while result_element is None:
                try:
                    result_element = craft_items(first, second)
                except ServerError:
                    tries += 1
                    if tries > 3:
                        logger.critical(f"Seems like '{first}' and '{second}' cannot be combined - moving on!")
                        break

            if result_element is None:
                continue

            with LogElapsedTime(log_func=logger.debug, label="Iteration"):
                self.after_successful_request()

                recipe = frozenset((first, second))

                self.process_recipe(recipe, result_element.text)

                # "Nothing" is not actually an element, but the indication of a recipe being invalid.
                # We still want to save recipes resulting in "Nothing", but it should not be saved as an element
                if result_element.text == "Nothing":
                    self.process_nothing_result(first=first, second=second)
                    continue

                if self.element_already_known(result_element.text):
                    self.process_known_element(result_element, first=first, second=second)
                    continue

                self.process_new_element(result_element, first=first, second=second)

                if self.exit_condition():
                    return

    def exit_condition(self) -> bool:
        return False

    @abstractmethod
    def sample_elements(self) -> tuple[str, str]:
        """How to sample elements."""

    def after_successful_request(self) -> None:
        # TODO: change to `self.ui.indicate_request_started()` (or rather finished...)
        print(".", end="")
        sys.stdout.flush()  # required to correctly display this in Windows Terminal
        # TODO/

    def process_recipe(self, recipe: frozenset[str], result: str) -> None:
        """Process the recipe after a successful crafting request."""
        with self.recipes_lock or nullcontext():
            self.recipes.add(recipe)

        with self.recipes_repository_lock or nullcontext():
            self.repository.add_recipe(ingredients=recipe, result=result)

    def process_nothing_result(self, first: str, second: str) -> None:
        pass

    def element_already_known(self, element_name: str) -> bool:
        with self.elements_set_lock or nullcontext():
            return element_name in self.elements_set

    def process_known_element(self, result_element: Element, first: str, second: str) -> None:
        pass

    def process_new_element(self, element: Element, first: str, second: str) -> None:
        with self.elements_set_lock or nullcontext():
            self.elements_set.add(element.text)
        with self.elements_list_lock or nullcontext():
            self.elements_list.append(element.text)

        with self.elements_repository_lock or nullcontext():
            self.repository.add_element(element)

    # TODO move to ui class
    @staticmethod
    def print_finding(
        new_element: Element, first: str, second: str, depth: Optional[int] = None, previous_depth: Optional[int] = None
    ) -> None:
        """Unified format of printing new elements (green if new discovery else white) and shorter paths (yellow)."""
        color_str = "[green]" if new_element.discovered else "[yellow]" if previous_depth is not None else ""
        new_element_str = f"{new_element.emoji:>5} {new_element.text}"
        depth_str = (
            f"({previous_depth} -> {depth})"
            if previous_depth is not None
            else f"({depth})" if depth is not None else ""
        )
        ingredients_str = f"({first} + {second})"

        print("\r", end="")
        rich.print(f"{color_str}{new_element_str:<50} {depth_str:>12} {ingredients_str}")
