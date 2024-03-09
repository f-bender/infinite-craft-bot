import bisect
import logging
import threading
from contextlib import nullcontext
from typing import Optional

import numpy as np

from infinite_craft_bot.crawler.common import Crawler
from infinite_craft_bot.globals import PROJECT_ROOT
from infinite_craft_bot.persistence.common import Element, FileRepository
from infinite_craft_bot.text_similarity import TextSimilarityCalculator

logger = logging.getLogger(__name__)

# TODO: store embeddings, to avoid having to compute all of them every time!
CACHED_EMBEDDINGS_FILE = PROJECT_ROOT / "data" / "_cached_element_embeddings.npz"


class TargetedCrawler(Crawler):
    def __init__(
        self, repository: FileRepository, target_element: str, higher_similarity_prioritization_factor: float = 100
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
        self.sorted_elements_lock: Optional[threading.Lock] = None
        self.recipes_lock: Optional[threading.Lock] = None

    def create_locks(self) -> None:
        """Creation of locks that is only done when crawl_multithreaded() is called."""
        self.elements_to_target_similarity_lock = threading.Lock()
        self.elements_repository_lock = threading.Lock()
        self.recipes_repository_lock = threading.Lock()
        self.sorted_elements_lock = threading.Lock()
        self.recipes_lock = threading.Lock()

    def init_data(self) -> None:
        """Initialization of in-memory data this class keeps track of, executed in __init__()."""
        self.sorted_elements = [element.text for element in self.repository.load_elements()]

        elements_to_embeddings =  self.get_element_embeddings()

        logger.debug("Computing similarities to target...")
        self.elements_to_target_similarity = {
            element: self.text_similarity_calculator.similarity(self.target_element_embedding, element_embedding)
            for element, element_embedding in elements_to_embeddings.items()
        }
        logger.debug("Done!")

        self.sorted_elements.sort(key=lambda el: -self.elements_to_target_similarity[el])

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

    def sample_elements(self) -> tuple[str, str]:
        num_elements = len(self.sorted_elements)

        mean = 0
        std_deviation = len(self.sorted_elements) / self.higher_similarity_prioritization_factor

        while True:
            i = j = num_elements
            while not (i < num_elements and j < num_elements):
                i, j = np.random.normal(mean, std_deviation, size=2)
                i, j = int(abs(i)), int(abs(j))

            first, second = self.sorted_elements[i], self.sorted_elements[j]
            if frozenset((first, second)) in self.recipes:
                continue

            logger.debug(
                f"{num_elements} -> {(i, j)}, sims "
                f"({self.elements_to_target_similarity[first]:.3g}, {self.elements_to_target_similarity[second]:.3g}) "
                f"({(first, second)})"
            )
            return first, second

    def element_already_known(self, element_name: str) -> bool:
        return element_name in self.elements_to_target_similarity

    def process_new_element(self, element: Element, first: str, second: str) -> None:
        with self.elements_repository_lock or nullcontext():
            self.repository.add_element(element)

        # add at correct index (keeping it sorted) using bisection
        new_element_target_similarity = self.target_similarity(element.text)
        with self.elements_to_target_similarity_lock or nullcontext(), self.sorted_elements_lock or nullcontext():
            self.elements_to_target_similarity[element.text] = new_element_target_similarity
            bisect.insort(
                self.sorted_elements,
                element.text,
                key=lambda el: -self.elements_to_target_similarity[el],
            )

        # TODO: self.ui.print_finding(new_element=result_element, depth=len(new_element_path), first=first, second=second)
        self.print_finding(new_element=element, first=first, second=second)
        # TODO/

    def exit_condition(self) -> bool:
        return self.target_element in self.elements_to_target_similarity
