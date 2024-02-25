from pathlib import Path
from typing import Callable

import fasteners


def call_if_free(func: Callable[[], None], lock_id: str) -> bool:
    lock = fasteners.InterProcessLock(Path(__file__) / ".locks" / f"{lock_id}.lock")

    try:
        if lock.acquire(blocking=False):
            func()
            return True
        else:
            return False
    finally:
        if lock.acquired:
            lock.release()
