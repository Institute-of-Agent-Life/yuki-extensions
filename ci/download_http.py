"""Bounded retries for read-only, checksum-pinned CI asset transport."""
import sys
from time import sleep
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def read_get(request, *, timeout=60):
    if isinstance(request, Request) and (request.get_method() != "GET" or request.data is not None):
        raise ValueError("CI asset retries require GET")
    for attempt in range(3):
        try:
            with urlopen(request, timeout=timeout) as response:
                return response.read()
        except HTTPError as error:
            error.close()
            retry_after = error.headers is not None and error.headers.get("Retry-After") is not None
            if error.code not in {502, 503, 504} or retry_after or attempt == 2:
                raise
            delay = (1, 2)[attempt]
            print(f"CI asset GET HTTP {error.code}; retry {attempt + 2}/3 after {delay}s",
                  file=sys.stderr, flush=True)
            sleep(delay)
