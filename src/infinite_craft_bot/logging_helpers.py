import logging
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
import time
from typing import Callable, Self

from infinite_craft_bot.globals import PROJECT_ROOT


def configure_logging(log_dir: Path = PROJECT_ROOT / "logs") -> None:
    logging.getLogger().setLevel(logging.DEBUG)

    # Create formatter
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S")

    # Create TimedRotatingFileHandler for all log messages
    rotating_handler = TimedRotatingFileHandler(log_dir / "debug.log", when="S", interval=300, backupCount=1)
    rotating_handler.setLevel(logging.DEBUG)
    rotating_handler.setFormatter(formatter)
    logging.getLogger().addHandler(rotating_handler)

    # Create TimedRotatingFileHandler for INFO and above
    info_handler = TimedRotatingFileHandler(log_dir / "info.log", when="H", interval=2, backupCount=1)
    info_handler.setLevel(logging.INFO)
    info_handler.setFormatter(formatter)
    logging.getLogger().addHandler(info_handler)

    # Create console handler for warnings and above
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(formatter)
    logging.getLogger().addHandler(console_handler)

    logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)


class LogTimer:
    def __init__(self, log_func: Callable[[str], None], name: str) -> None:
        self.log_func = log_func
        self.name = name

    def __enter__(self) -> Self:
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        elapsed_time = time.perf_counter() - self.start_time
        time_str = f"{elapsed_time:.3g}s" if elapsed_time > 0.1 else f"{elapsed_time * 1_000:.3g}ms"
        self.log_func(f"{time_str} ({self.name})")
