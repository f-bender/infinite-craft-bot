import argparse
import logging

from rich import print

from infinite_craft_bot.crawler.exhaustive_by_depth import ExhaustiveCrawler
from infinite_craft_bot.crawler.probibalistic import ProbibalisticCrawler, SamplingStrategy
from infinite_craft_bot.crawler.targeted import TargetedCrawler
from infinite_craft_bot.element_paths.compute_paths import compute_and_save_elements_paths
from infinite_craft_bot.logging_helpers import configure_logging
from infinite_craft_bot.persistence.csv_file import PaginatedCsvRepository
from infinite_craft_bot.query_full_recipe import FullRecipeQuery, print_full_recipes

logger = logging.getLogger(__name__)

NUM_THREADS = 15


def main() -> None:
    """CLI entrypoint."""
    args = parse_args()

    configure_logging(subcommand=args.subcommand)

    if args.compute_element_paths or args.subcommand == "compute_paths":
        logger.info("Computing elements' paths...")
        compute_and_save_elements_paths(repository=PaginatedCsvRepository(), save_stats=args.save_path_stats)

    match args.subcommand:
        case "query":
            logger.info("Starting full recipe querying...")
            query_full_recipes_continuously()
        case "crawl":
            match args.crawl_mode:
                case "low":
                    logger.info("Crawling in low-depth mode...")
                    crawler = ProbibalisticCrawler(
                        sampling_strategy=SamplingStrategy.LOW_DEPTH,
                        repository=PaginatedCsvRepository(write_access=True),
                    )
                    crawler.crawl_multithreaded(num_threads=NUM_THREADS)
                case "exhaust":
                    logger.info("Crawling in exhaustive by depth mode...")
                    crawler = ExhaustiveCrawler(repository=PaginatedCsvRepository(write_access=True))
                    crawler.crawl_multithreaded(num_threads=NUM_THREADS)
                case "target":
                    if args.target_element is None:
                        raise ValueError("Need to specify a target element in targetted mode!")
                    logger.info(f"Crawling in targetted mode: trying to find '{args.target_element}'...")
                    crawler = TargetedCrawler(
                        repository=PaginatedCsvRepository(write_access=True), target_element=args.target_element
                    )
                    crawler.crawl_multithreaded(num_threads=NUM_THREADS)
                case _:
                    raise ValueError(f"Unknown crawl mode: `{args.crawl_mode}")
        case "compute_paths":
            pass
        case _:
            raise ValueError(f"Unknown subcommand: '{args.subcommand}'")

    # note that all the (pretty) printing should go here (e.g. print_findings)
    # (if it's getting much, perhaps make this a directory with multiple files for better organiaztion
    # i.e. cli/__init__.py, cli/printing.py, ...)
    #! Actually, it's not that simple. I want to show things to the user from the inside of the crawler.
    #! The best idea is probably to (separately from this) create a ui.py file with a UI class (which could
    #! theoretically in the future have different, e.g. GUI implementations), which is then provided to the crawlers.
    #! (-> dependency injection)
    #! this would have to have functions like
    #! display_finding(element: Element, depth: int, first: str, second: str, previous_depth: Optional[int] = None)
    #! indicate_request_started(): print(".", end="")
    #! and so on

    # TODO: use git LFS for files inside data/

    # TODO: file pagination for recipes and elements (limit to e.g. 100k items/lines per file)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument("subcommand", type=str, choices=["crawl", "query", "compute_paths"], default="crawl")
    parser.add_argument(
        "--compute_element_paths",
        "-p",
        action="store_true",
        help=(
            "Whether to compute element paths before executing the specified command. Note that up-to-date element "
            "paths are required for some crawlers to work, and for the recipe queries to give up-to-date information."
        ),
    )
    parser.add_argument(
        "--save_path_stats",
        "-s",
        action="store_true",
        help=(
            "Whether to save stats about the element paths after computing them. "
            "Only has an effect if `--compute_paths` is set."
        ),
    )
    parser.add_argument("--crawl_mode", "-m", type=str, choices=["low", "exhaust", "target"], default="low")
    parser.add_argument("--target_element", "-t", type=str, default=None)

    return parser.parse_args()


def query_full_recipes_continuously() -> None:
    query = FullRecipeQuery(PaginatedCsvRepository())

    while True:
        print("\n[yellow]Enter an element to get its recipe:", end=" ")
        try:
            element = input().strip()
        except KeyboardInterrupt:
            return
        print()

        print_full_recipes(query.query_full_recipe(element))
