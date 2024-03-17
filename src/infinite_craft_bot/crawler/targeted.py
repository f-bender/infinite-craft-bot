import bisect
from io import StringIO
import logging
import re
import threading
from contextlib import nullcontext
import time
from typing import Optional

import numpy as np

from infinite_craft_bot.crawler.common import Crawler
from infinite_craft_bot.globals import PROJECT_ROOT
from infinite_craft_bot.persistence.common import Element, FileRepository
from infinite_craft_bot.text_similarity import TextSimilarityCalculator

logger = logging.getLogger(__name__)

# TODO: store embeddings, to avoid having to compute all of them every time!
CACHED_EMBEDDINGS_FILE = PROJECT_ROOT / "data" / "_cached_element_embeddings.npz"


def make_valid_directory_name(name):
    # Define the pattern for invalid characters
    invalid_chars = re.compile(r'[<>:"/\\|?*\x00-\x1F]')  # Including control characters

    # Replace invalid characters with underscores
    valid_name = re.sub(invalid_chars, "_", name)

    # Remove leading and trailing whitespaces and dots
    valid_name = valid_name.strip(". ").rstrip()

    # Limit length of name to 255 characters (Windows limit)
    valid_name = valid_name[:255]

    return valid_name


class TargetedCrawler(Crawler):
    def __init__(
        self, repository: FileRepository, target_element: str, higher_similarity_prioritization_factor: float = 500
    ) -> None:
        self.text_similarity_calculator = TextSimilarityCalculator()
        self.target_element = target_element
        self.target_element_embedding = self.text_similarity_calculator.compute_embeddings([self.target_element])[0]

        self.higher_similarity_prioritization_factor = higher_similarity_prioritization_factor

        super().__init__(repository)

    def init_locks(self) -> None:
        """Initialization of locks executed in __init__()."""
        # in case multiple locks need to be acquired, they should always be acquired in the order in which they are
        # listed here (which happens to be longest name to shortest name)!
        self.elements_to_target_similarity_lock: Optional[threading.Lock] = None
        self.elements_repository_lock: Optional[threading.Lock] = None
        self.recipes_repository_lock: Optional[threading.Lock] = None
        self.forbidden_pattern_lock = threading.Lock()
        self.sorted_elements_lock = threading.Lock()
        self.recipes_lock: Optional[threading.Lock] = None

    def create_locks(self) -> None:
        """Creation of locks that is only done when crawl_multithreaded() is called."""
        self.elements_to_target_similarity_lock = threading.Lock()
        self.elements_repository_lock = threading.Lock()
        self.recipes_repository_lock = threading.Lock()
        self.sorted_elements_lock = threading.Lock()
        self.recipes_lock = threading.Lock()

    def _sort_key(self, element_name: str) -> float:
        penalty = 0
        if self.forbidden_pattern is not None and (
            bool(self.forbidden_pattern.search(element_name.lower())) ^ bool(self.whitelist)
        ):
            penalty = 100

        # negate in order to sort from highest to lowest (bisect.insort doesn't provide "revsere" argument)
        return -(self.elements_to_target_similarity[element_name] - 0.01 * len(element_name) - penalty)

    def load_forbidden_pattern(self) -> tuple[Optional[re.Pattern], Optional[bool]]:
        try:
            forbidden_patterns = self.repository.load_arbitrary_data_from_file(
                subdirs=["targeted", make_valid_directory_name(self.target_element)],
                filename="forbidden_patterns.txt",
                encoding="utf-8",
            )
        except FileNotFoundError:
            # create the file without any contents, to make it easy for the user to start adding to it
            self.repository.save_arbitrary_data_to_file(
                content=StringIO(""),
                subdirs=["targeted", make_valid_directory_name(self.target_element)],
                filename="forbidden_patterns.txt",
                encoding="utf-8",
            )
            return None, None

        # TODO: a more fine-grained system (probably using json or so), where you can specify "boost"-regexes and
        # TODO  "penalty"-regexes. For each boost regex an element matches with, it gets scored higher. For each
        # TODO  penalty-regex-match, it gets scored lower.

        # TODO: maybe in the future even such fine-grained control that first and second element of the combination have
        # TODO  different filters/regexes (e.g. such that I can try to specifically combine video-related elements with
        # TODO  game-related elements, to try and get Video Game)

        # TODO: maybe, instead of a config file, have the "config" be an actual pyhton code file where basically
        # TODO  there is a function which computes the "fitness value" of a given element, and this python code file
        # TODO  is read and passed into "eval", i.e. "compiled" into an actual function which is then used to sort
        # TODO  the elements list (in case of a syntax error or so, do nothing; do as if nothing had changed)
        # TODO  -> then later have this compute 2 separate fitness values for first and second
        #! -> could make use of importlib.reload instead of using eval:
        #! https://chat.openai.com/share/5d5ae8c6-73b7-4963-a6dd-ef9d1beae74b

        forbidden_patterns = forbidden_patterns.strip()
        if not forbidden_patterns:
            return None, None

        whitelist = False
        patterns = forbidden_patterns.split("\n")
        if patterns[0] == "WHITELIST":
            whitelist = True
            patterns = patterns[1:]

        if not patterns:
            return None, None

        return re.compile("|".join(patterns)), whitelist

    def init_data(self) -> None:
        """Initialization of in-memory data this class keeps track of, executed in __init__()."""
        self.sorted_elements = [element.text for element in self.repository.load_elements()]

        elements_to_embeddings = self.get_element_embeddings()

        logger.debug("Computing similarities to target...")
        self.elements_to_target_similarity = {
            element: self.text_similarity_calculator.similarity(self.target_element_embedding, element_embedding)
            for element, element_embedding in elements_to_embeddings.items()
        }
        logger.debug("Done!")

        self.forbidden_pattern, self.whitelist = self.load_forbidden_pattern()
        logger.info(f"Forbidden pattern: {self.forbidden_pattern}")

        self.sorted_elements.sort(key=self._sort_key)
        logger.info(
            f"Already known elements most similar to '{self.target_element}':\n"
            + "\n".join(f"{i:>2}: {el}" for i, el in enumerate(self.sorted_elements[:100]))
        )

        self.recipes = set(self.repository.load_recipes())

    def get_element_embeddings(self) -> dict[str, np.ndarray]:
        elements_to_embeddings: dict[str, np.ndarray] = {}
        if CACHED_EMBEDDINGS_FILE.is_file():
            logger.debug("Loading cached embeddings...")
            data = np.load(CACHED_EMBEDDINGS_FILE, allow_pickle=True)
            logger.debug("Done!")
            elements_to_embeddings.update(dict(zip(data["texts"], data["embeddings"])))

        non_cached_elements = [el for el in self.sorted_elements if el not in elements_to_embeddings]

        if non_cached_elements:
            logger.debug("Computing remaining embeddings...")
            element_embeddings = self.text_similarity_calculator.compute_embeddings(non_cached_elements)
            logger.debug("Done!")

            elements_to_embeddings.update(dict(zip(non_cached_elements, element_embeddings)))

            logger.debug("Saving embeddings to cache file...")
            np.savez(
                CACHED_EMBEDDINGS_FILE,
                texts=list(elements_to_embeddings.keys()),
                embeddings=list(elements_to_embeddings.values()),
            )
            logger.debug("Done!")

        return elements_to_embeddings

    def target_similarity(self, element: str) -> float:
        element_embedding = self.text_similarity_calculator.compute_embeddings([element])[0]
        return self.text_similarity_calculator.similarity(self.target_element_embedding, element_embedding)

    def periodically_update_forbidden_substrings(self) -> None:
        while True:
            time.sleep(10)
            new_forbidden_pattern, new_whitelist = self.load_forbidden_pattern()
            if (new_forbidden_pattern, new_whitelist) != (self.forbidden_pattern, self.whitelist):
                logger.info(f"New forbidden pattern: {new_forbidden_pattern}")
                with self.forbidden_pattern_lock, self.sorted_elements_lock:
                    self.forbidden_pattern, self.whitelist = new_forbidden_pattern, new_whitelist
                    self.sorted_elements.sort(key=self._sort_key)

    def crawl_multithreaded(self, num_threads: int, blocking: bool = True) -> None:
        threading.Thread(target=self.periodically_update_forbidden_substrings, daemon=True).start()
        return super().crawl_multithreaded(num_threads, blocking)

    def sample_elements(self) -> tuple[str, str]:
        num_elements = len(self.sorted_elements)

        exp_scale = len(self.sorted_elements) / self.higher_similarity_prioritization_factor

        while True:
            i = j = num_elements
            while not (i < num_elements and j < num_elements):
                i, j = np.random.exponential(scale=exp_scale, size=2)
                i, j = int(abs(i)), int(abs(j))

            first, second = self.sorted_elements[i], self.sorted_elements[j]
            if frozenset((first, second)) in self.recipes:
                continue

            logger.debug(
                f"{num_elements} -> {(i, j)}, sims "
                f"({self.elements_to_target_similarity[first]:.3g}, {self.elements_to_target_similarity[second]:.3g}) "
                f"({first}, {second})"
            )
            return first, second

    def element_already_known(self, element_name: str) -> bool:
        return element_name in self.elements_to_target_similarity

    def process_new_element(self, element: Element, first: str, second: str) -> None:
        with self.elements_repository_lock or nullcontext():
            self.repository.add_element(element)

        # add at correct index (keeping it sorted) using bisection
        new_element_target_similarity = self.target_similarity(element.text)
        with (
            self.elements_to_target_similarity_lock or nullcontext(),
            self.forbidden_pattern_lock or nullcontext(),
            self.sorted_elements_lock or nullcontext(),
        ):
            self.elements_to_target_similarity[element.text] = new_element_target_similarity
            bisect.insort(self.sorted_elements, element.text, key=self._sort_key)

        # TODO: self.ui.print_finding(new_element=result_element, depth=len(new_element_path), first=first, second=second)
        self.print_finding(new_element=element, first=first, second=second)
        # TODO/

        if element.text == self.target_element:
            print("\n" * 20)
            print(f"######################## FOUND TARGET ELEMENT '{self.target_element}'!!! ########################")
            print("\n" * 20)

    def exit_condition(self) -> bool:
        # NOTE: by "not caring" if we have found our target, we can re-frame this as a crawler which finds elements
        # related to a certain concept
        return False
        # return self.target_element in self.elements_to_target_similarity
