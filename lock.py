from pathlib import Path
from typing import Callable

import fasteners


def call_if_free(func: Callable[[], None], lock_file: Path) -> bool:
    lock = fasteners.InterProcessLock(lock_file)

    try:
        if lock.acquire(blocking=False):
            func()
            return True
        else:
            return False
    finally:
        if lock.acquired:
            lock.release()
