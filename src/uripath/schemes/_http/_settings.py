"""The two module-level settings of the HTTP schemes. Code reads them as
attributes of this module, so assigning one applies at once."""

from __future__ import annotations

DEFAULT_TIMEOUT = (10, 60)
"""`(connect, read)` timeout, in seconds, `HTTPBackend` sends with every
request unless the caller supplies `timeout` (`HTTPBackend(timeout=...)`,
`with_transport(timeout=...)`, `with_session(..., timeout=...)`, or per
request); `timeout=None` there waits without a limit."""


MAX_LISTING_BYTES = 8 * 1024 * 1024
"""Most bytes of a reply the library reads whole, after any content decoding: a
directory index, and a reply it needs for what it says (a PROPFIND's, a git
API's, `HTTPBackend.request(stream=False)`'s). A longer body raises
`OSError(EFBIG)` naming the path and closes the connection. The body of a
reply nobody looks at (a write's, a DELETE's) is read up to this many bytes
and dropped. Raise it for an index that is legitimately larger; parsing costs
about a second per megabyte. Read at the time of each use."""
