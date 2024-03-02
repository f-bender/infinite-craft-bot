import logging
import time
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Callable, Self

from infinite_craft_bot.globals import PROJECT_ROOT


def configure_logging(subcommand: str, log_dir: Path = PROJECT_ROOT / "logs") -> None:
    log_dir = log_dir / subcommand
    log_dir.mkdir(parents=True, exist_ok=True)

    logging.getLogger().setLevel(logging.DEBUG)

    # Create formatter
    file_formatter = logging.Formatter(
        "%(asctime)s - [%(thread)5d] %(name)-50s - %(levelname)-8s - %(message)s", datefmt="%H:%M:%S"
    )

    # Create TimedRotatingFileHandler for all log messages
    rotating_handler = TimedRotatingFileHandler(log_dir / "debug.log", when="S", interval=300, backupCount=1)
    rotating_handler.setLevel(logging.DEBUG)
    rotating_handler.setFormatter(file_formatter)
    logging.getLogger().addHandler(rotating_handler)

    # Create TimedRotatingFileHandler for INFO and above
    info_handler = TimedRotatingFileHandler(log_dir / "info.log", when="H", interval=2, backupCount=1)
    info_handler.setLevel(logging.INFO)
    info_handler.setFormatter(file_formatter)
    logging.getLogger().addHandler(info_handler)

    console_formatter = logging.Formatter(
        "%(asctime)s - [%(thread)d] %(name)s - %(levelname)s - %(message)s", datefmt="%H:%M:%S"
    )

    # Create console handler for warnings and above
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(console_formatter)
    logging.getLogger().addHandler(console_handler)

    logging.getLogger("urllib3.connectionpool").setLevel(logging.WARNING)


class LogElapsedTime:
    def __init__(self, log_func: Callable[[str], None], label: str) -> None:
        self.log_func = log_func
        self.label = label

    def __enter__(self) -> Self:
        self.start_time = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        elapsed_time = time.perf_counter() - self.start_time
        time_str = f"{elapsed_time:.3g}s" if elapsed_time > 0.1 else f"{elapsed_time * 1_000:.3g}ms"
        self.log_func(f"{time_str} ({self.label})")
