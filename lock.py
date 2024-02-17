from pathlib import Path
from typing import Callable

import fasteners


def call_if_free(func: Callable[[], None], lock_file: Path) -> None:
    lock = fasteners.InterProcessLock(lock_file)

    try:
        if lock.acquire(blocking=False):
            func()
        else:
            print("Program already running in another instance! Exiting...")
            return
    finally:
        if lock.acquired:
            lock.release()
