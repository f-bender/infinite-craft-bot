from collections import Counter
import io
import matplotlib.pyplot as plt
from typing import Optional
from rich import print

from infinite_craft_bot.persistence import FileRepository


# TODO separate stats from plot
def compute_stats(elements: dict[str, tuple[Optional[tuple[str, str]], set[str]]], repository: FileRepository) -> None:
    depth_counts = Counter([len(path) for _, path in elements.values()])

    deepest_element = max(elements, key=lambda el: len(elements[el][1]))
    print(f"Deepest element: {deepest_element} ({len(elements[deepest_element][1])} deep)")

    most_common_depth, num_elements = depth_counts.most_common()[0]
    print(f"Most elements at depth {most_common_depth} ({num_elements} elements)")

    plt.bar(*zip(*depth_counts.items()))
    plt.xlabel("Depth of Element")
    plt.ylabel("Number of Elements")
    plt.yscale("log")

    svg_bytes_io = io.BytesIO()
    plt.savefig(svg_bytes_io, format="svg")

    plt.close()

    repository.save_arbitrary_data_to_file(svg_bytes_io, subdirs=["stats"], filename="depths.svg")

# TODO main method where elements_paths are read from repoistory, and then stats are calculated and plots made
