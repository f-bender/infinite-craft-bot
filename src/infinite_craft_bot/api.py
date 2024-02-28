import logging
import time
from typing import Optional

import requests
from ratelimit import limits, sleep_and_retry

from infinite_craft_bot.persistence import Element

logger = logging.getLogger(__name__)

URL_TEMPLATE = "https://neal.fun/api/infinite-craft/pair?first={first}&second={second}"
HEADERS = {
    # directly copied from a request made when using Infinite Craft in the browser
    # (F12 -> Network tab -> click on "pair?..." request -> Headers tab -> Request Headers)
    "Accept": "*/*",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-US,en;q=0.9,de-DE;q=0.8,de;q=0.7",
    "Referer": "https://neal.fun/infinite-craft/",
    "Sec-Ch-Ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
}


class ApiChanged(Exception):
    pass


# TODO observe how well `ratelimit` works (alternative: https://github.com/vutran1710/PyrateLimiter)
@sleep_and_retry
@limits(calls=14, period=3)  # below 5/s!
def craft_items(first: str, second: str, session: Optional[requests.Session] = None) -> Optional[Element]:
    get = session.get if session else requests.get

    before_request = time.perf_counter()

    try:
        response = get(URL_TEMPLATE.format(first=first, second=second), headers=HEADERS, timeout=10)
    except Exception as e:
        logger.warning(f"Crafting failed: {e}")
        return None

    request_duration = time.perf_counter() - before_request
    (logger.debug if request_duration < 2 else logger.info)(f"{request_duration:.3g}s (Request)")

    if response.ok:
        element_json = response.json()
        if set(element_json) != {"result", "emoji", "isNew"}:
            message = f"The API has changed and the keys of the JSON results are now {set(element_json)}!"
            logger.error(message)
            raise ApiChanged(message)

        return Element(text=element_json["result"], emoji=element_json["emoji"], discovered=element_json["isNew"])

    # TODO in case of a 429 "Too Many Requests" error, the response header contains the number of seconds until we're
    # allowed to make reqeusts again. Read this, and sleep for that time!
    logger.warning(f"Crafting failed: {response.status_code} {response.reason}")
    return None
