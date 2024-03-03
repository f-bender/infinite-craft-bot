import io
from collections import Counter

import matplotlib.pyplot as plt
import pandas as pd

from infinite_craft_bot.persistence.common import ElementPath, FileRepository


def compute_and_save_stats(elements_paths: dict[str, ElementPath], repository: FileRepository) -> None:
    depth_counts = Counter([len(el_path.path) for el_path in elements_paths.values()])

    repository.save_arbitrary_data_to_file(make_depths_plot(depth_counts), subdirs=["stats"], filename="depths.svg")

    repository.save_arbitrary_data_to_file(
        io.StringIO(collect_some_stats(elements_paths, depth_counts)), subdirs=["stats"], filename="stats.txt"
    )


def make_depths_plot(depth_counts: Counter) -> io.BytesIO:
    plt.bar(*zip(*depth_counts.items()))
    plt.xlabel("Depth of Element")
    plt.ylabel("Number of Elements")
    plt.yscale("log")

    svg_bytes_io = io.BytesIO()
    plt.savefig(svg_bytes_io, format="svg")
    plt.close()

    return svg_bytes_io


def collect_some_stats(elements_paths: dict[str, ElementPath], depth_counts: Counter) -> str:
    stats_str = ""

    for stat_name, row in (
        pd.DataFrame([len(el_path.path) for el_path in elements_paths.values()]).describe().iterrows()
    ):
        stats_str += f"{str(stat_name).title():>5}: {row.iloc[0]:.6g}\n"

    stats_str += "\n"

    deepest_elements = sorted(elements_paths, key=lambda el: len(elements_paths[el].path))[-10:]
    highest_depth = len(elements_paths[deepest_elements[-1]].path)

    stats_str += "Deepest elements:\n"
    stats_str += "\n".join(
        f"{len(elements_paths[element].path):>{len(str(highest_depth))}}: {element}" for element in deepest_elements
    )

    stats_str += "\n\n"

    most_common_depth, num_elements = depth_counts.most_common()[0]
    stats_str += f"Most elements at depth {most_common_depth} ({num_elements} elements)"

    stats_str += "\n\n"

    stats_str += "Number of elements per depth:\n"
    num_elements_cumulative = 0
    for depth, num_elements in sorted(depth_counts.items()):
        num_elements_cumulative += num_elements
        stats_str += (
            f"{depth:>{len(str(highest_depth))}}: {num_elements:>6} (cumulative {num_elements_cumulative:>7})\n"
        )

    return stats_str
