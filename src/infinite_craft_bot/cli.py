import logging
import sys
from infinite_craft_bot.crawler.probibalistic import ProbibalisticCrawler, SamplingStrategy
from infinite_craft_bot.element_paths.compute_paths import compute_and_save_elements_paths
from infinite_craft_bot.persistence import FileRepository


logger = logging.getLogger(__name__)


def main() -> None:
    """TODO: Create CLI entrypoint."""
    # query_main()

    if "-p" in sys.argv[1:]:
        compute_and_save_elements_paths(repository=FileRepository())
    else:
        crawler = ProbibalisticCrawler(sampling_strategy=SamplingStrategy.LOW_DEPTH, repository=FileRepository())
        crawler.crawl_multithreaded(num_threads=5)


    # TODO commandline arg parsing, mode choosing, delegating to the right crawler etc.

    # TODO also a mode for computing paths (and generating stas) -> even implementation left todo!

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
