from __future__ import annotations

import threading as _threading
import time as _time

from ._parse import _IPAddress

#: How long `Source.is_local()` remembers an answer, in seconds, and for how
#: many hosts.
_LOCAL_TTL = 60.0
_LOCAL_CACHE_SIZE = 256
_local_cache: "dict[object, tuple[float, bool]]" = {}
_local_lock = _threading.Lock()


def _host_is_local(host: "str | _IPAddress") -> bool:
    now = _time.monotonic()
    with _local_lock:
        entry = _local_cache.get(host)
    if entry is not None and entry[0] > now:
        return entry[1]
    answer = _resolve_is_local(host)
    with _local_lock:
        if len(_local_cache) >= _LOCAL_CACHE_SIZE:
            for key in [k for k, (until, _) in _local_cache.items() if until <= now]:
                del _local_cache[key]
        while len(_local_cache) >= _LOCAL_CACHE_SIZE:
            del _local_cache[next(iter(_local_cache))]
        _local_cache[host] = (now + _LOCAL_TTL, answer)
    return answer


def _resolve_is_local(host: "str | _IPAddress") -> bool:
    # Imported here, not at module top: only this needs netimps, and every
    # `import uripath` would otherwise pay for its import.
    import netimps as _netimps

    if not isinstance(host, str):
        return _netimps.is_local_address(host)
    literal = _netimps.try_parse(host)
    if literal is not None:
        return _netimps.is_local_address(literal)
    addresses = _netimps.resolve(host, "a") + _netimps.resolve(host, "aaaa")
    return any(_netimps.is_local_address(address) for address in addresses)
