"""This module contains different functions for sampling two elements to be combined from a list of elements."""

# different sampling functions may have different signatures, but the non-standard parameters will be applied using
# partial() initially, such that afterwards, a sampling function can be treated agnostically of which one it actually is
# I guess the "canonical" signature is f(elements: list[str]) -> tuple[str, str]

# don't expect the recipes as an input argument, instead accept a discard condition function (which will then be
# provided by main as `lambda first, second: frozenset([first, second]) in recipes`)

# * probably move these functions into the modules of their respective crawlers (if each is really only used by one crawler)

import logging
import random
from collections.abc import Sequence
from typing import Callable, Optional

import numpy as np

logger = logging.getLogger(__name__)


def skewed_towards_low_depth(
    elements_sorted_ascending_by_depth: list[str],
    elements_to_path: dict[str, set[str]],
    lower_depth_prioritization_factor: float = 25,
    non_synergy_penalization_coefficient: float = 0.5,
    discard_result_predicate: Optional[Callable[[tuple[str, str]], bool]] = None,
) -> tuple[str, str]:
    """Prioritizes low-depth elements, and high path-overlap of the two elements in sampling.

    IMPORTANT: This function assumes that the provided list of elements is sorted ascending by depth!

    The goal of this sampling method is to overwhelmingly create low-depth elements as crafting results.
    Sampling is probibalistic though, so there are no guarantees.

    Before returning a result, it will be checked by the `discard_result_predicate`, and if this returns `True`, the
    result is discarded and another sampling attmept is started. This function is thus guaranteed to never return a
    result which would be "flagged" by the `discard_result_predicate`.
    """
    num_elements = len(elements_sorted_ascending_by_depth)

    mean = 0
    std_deviation = len(elements_sorted_ascending_by_depth) / lower_depth_prioritization_factor

    while True:
        i = j = num_elements
        while not (i < num_elements and j < num_elements):
            i, j = np.random.normal(mean, std_deviation, size=2)
            i, j = int(abs(i)), int(abs(j))

        first_name, second_name = elements_sorted_ascending_by_depth[i], elements_sorted_ascending_by_depth[j]
        if discard_result_predicate is not None and discard_result_predicate((first_name, second_name)):
            continue

        first_path, second_path = elements_to_path[first_name], elements_to_path[second_name]

        path_lengths = len(first_path), len(second_path)
        intersection_length = len(first_path & second_path)

        # the highest overlap that would be possible given the path lenths, minus the actual overlap (intersection)
        # -> This many nodes of the path could have overlapped but didn't
        non_overlapping_path_length = min(path_lengths) - intersection_length
        keep_probability = (1 / (1 + non_overlapping_path_length)) ** non_synergy_penalization_coefficient

        logger.debug(
            f"{num_elements} -> {(i, j)}, depths {path_lengths} -> "
            f"{sum(path_lengths) + 1 - intersection_length}, intersect {intersection_length}, "
            f"prob {keep_probability:.3g} ({(first_name, second_name)})"
        )
        if random.random() < keep_probability:
            return first_name, second_name


def fully_random(
    elements: Sequence[str], discard_result_predicate: Optional[Callable[[tuple[str, str]], bool]] = None
) -> tuple[str, str]:
    """Samples fully randomly from the sequence of provided elements.

    Before returning a result, it will be checked by the `discard_result_predicate`, and if this returns `True`, the
    result is discarded and another sampling attmept is started. This function is thus guaranteed to never return a
    result which would be "flagged" by the `discard_result_predicate`.
    """
    while True:
        result = random.choice(elements), random.choice(elements)
        if discard_result_predicate is None or not discard_result_predicate(result):
            return result
