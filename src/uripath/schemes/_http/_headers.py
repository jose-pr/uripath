"""Headers the HTTP schemes send for their own purposes."""

from __future__ import annotations

_IDENTITY_ENCODING = {"Accept-Encoding": "identity"}
"""Sent on content GETs and `stat()` probes: a transport advertises
gzip/deflate by default, and a stored blob must not come back as its encoded
form, while `Content-Length` would count the encoded bytes."""
