"""A crawler that randomly samples from the elements to combine.

Sampling can be skewed towards high or low depth, or completely random.
"""

import bisect
import concurrent.futures
from contextlib import nullcontext
from enum import Enum, auto
from functools import partial
import logging
import sys
import threading
from typing import NoReturn, Optional

import rich
from infinite_craft_bot.api import craft_items

from infinite_craft_bot.crawler import sample_elements
from infinite_craft_bot.persistence import Element, FileRepository,  WriteAccessLocked

logger = logging.getLogger(__name__)


# maybe actually make this three separate modules? and just move truly common parts to a common place...
class SamplingStrategy(Enum):
    LOW_DEPTH = auto()
    RANDOM = auto()
    HIGH_DEPTH = auto()


class ProbibalisticCrawler:

    # TODO: maybe implement an abstract crawler class, that basically already has a template crawling loop, but provides
    # the ability to specify callbacks that are called at various points throughout the crawling loop (a lot like
    # pytorch lightning; I imagine it just like this video shows:
    # https://lightning.ai/docs/pytorch/stable/_static/fetched-s3-assets/pl_readme_gif_2_0.mp4 )
    # then low-depth, random, and high-depth are separate subclasses of crawler, just lite interactive and brute-force

    def __init__(self, sampling_strategy: SamplingStrategy, repository: FileRepository) -> None:
        # The repository itself is responsible for making sure that it is the only instance that has write access to its
        # underlying files. We as the crawler are responsible for making sure that we don't use its writing functions
        # concurrently.
        self.repository = repository
        if not self.repository.acquire_write_access():  # we need write access to add elements and repices to the repository
            raise WriteAccessLocked()

        elements = repository.load_elements()

        _element_paths = repository.load_elements_paths()
        self.elements_to_path: dict[str, set[str]] = {
            element.text: set(_element_paths[element.text].path) for element in elements
        }
        self.sorted_elements = [element.text for element in elements]
        self.sorted_elements.sort(key=lambda el: len(self.elements_to_path[el]))

        self.recipes = set(self.repository.load_recipes())

        match sampling_strategy:
            case SamplingStrategy.LOW_DEPTH:
                self.sampling_function = partial(
                    sample_elements.skewed_towards_low_depth,
                    elements_sorted_ascending_by_depth=self.sorted_elements,
                    elements_to_path=self.elements_to_path,
                    discard_result_predicate=lambda ingredients: frozenset(ingredients) in self.recipes,
                )
            case SamplingStrategy.RANDOM:
                self.sampling_function = partial(
                    sample_elements.fully_random,
                    discard_result_predicate=lambda ingredients: frozenset(ingredients) in self.recipes,
                )
            case SamplingStrategy.HIGH_DEPTH:
                raise NotImplementedError()

        self.elements_lock: Optional[threading.Lock] = None
        self.recipes_lock: Optional[threading.Lock] = None

    # TODO make CTRL+C actually work (maybe needs to be handled within the thread)
    # maybe this requires using simple threading.Threads (which would be ok with me actually)
    def crawl_multithreaded(self, num_threads: int) -> None:
        # one idea would be to have the threads send messages (in Rust this would be using channels, in Pyhton I'm not
        # sure...), and let this main thread collect these message and process them by writing them to files etc.
        # but due to the lack of true parallelism due to the GIL, I might as well just do IO in every single thread
        self.elements_lock = threading.Lock()
        self.recipes_lock = threading.Lock()

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
            futures = [executor.submit(self.crawl) for _ in range(num_threads)]

            try:
                concurrent.futures.wait(futures)
            except KeyboardInterrupt:
                print("Interrupting all threads")
                for future in futures:
                    future.cancel()

        self.elements_lock = self.recipes_lock = None

    def crawl(self) -> NoReturn:
        while True:
            first, second = self.sampling_function()
            result_element = craft_items(first, second)

            if not result_element:
                continue

            # TODO: change to `self.ui.indicate_request_started()` (or rather finished...)
            print(".", end="")
            sys.stdout.flush()  # required to correctly display this in Windows Terminal
            # TODO/

            recipe = frozenset((first, second))
            self.recipes.add(recipe)

            with self.recipes_lock or nullcontext():
                self.repository.add_recipe(ingredients=recipe, result=result_element.text)

            # "Nothing" is not actually an element, but the indication of a recipe being invalid.
            # We still want to save recipes resulting in "Nothing", but it should not be saved as an element
            if result_element.text == "Nothing":
                continue

            new_element_path = self.elements_to_path[first] | self.elements_to_path[second] | {result_element.text}

            if result_element.text in self.elements_to_path:
                old_length = len(self.elements_to_path[result_element.text])
                new_length = len(new_element_path)
                if new_length < old_length:
                    # TODO: self.ui.print_finding() (or similar)
                    self.print_finding(
                        new_element=result_element,
                        depth=new_length,
                        previous_depth=old_length,
                        first=first,
                        second=second,
                    )
                    # TODO/
                    self.elements_to_path[result_element.text] = new_element_path
                    # sort again, such that the element moves to its new correct place in the list
                    # (now that its path is shorter)
                    self.sorted_elements.sort(key=lambda el: len(self.elements_to_path[el]))
                continue

            # actually new element

            self.elements_to_path[result_element.text] = new_element_path
            # add at correct index (keeping it sorted) using bisection
            bisect.insort(
                self.sorted_elements, result_element.text, key=lambda el_name: len(self.elements_to_path[el_name])
            )
            with self.elements_lock or nullcontext():
                self.repository.add_element(result_element)

            # TODO: self.ui.print_finding(new_element=result_element, depth=len(new_element_path), first=first, second=second)
            self.print_finding(new_element=result_element, depth=len(new_element_path), first=first, second=second)
            # TODO/

    # TODO move to ui class
    @staticmethod
    def print_finding(
        new_element: Element, depth: int, first: str, second: str, previous_depth: Optional[int] = None
    ) -> None:
        """Unified format of printing new elements (green if new discovery else white) and shorter paths (yellow)."""
        color_str = "[green]" if new_element.discovered else "[yellow]" if previous_depth is not None else ""
        new_element_str = f"{new_element.emoji:>5} {new_element.text}"
        depth_str = f"({previous_depth} -> {depth})" if previous_depth is not None else f"({depth})"
        ingredients_str = f"({first} + {second})"

        print("\r", end="")
        rich.print(f"{color_str}{new_element_str:<50} {depth_str:>12} {ingredients_str}")
