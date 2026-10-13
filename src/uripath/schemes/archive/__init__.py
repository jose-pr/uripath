from __future__ import annotations

from ._base import ArchiveURIPath as ArchiveURIPath
from ._base import _split_archive_path as _split_archive_path
from .tar import TarURIPath as TarURIPath
from .zip import ZipURIPath as ZipURIPath

# `archive+zip:` and `archive+tar:` are second scheme names of `ZipURIPath` and
# `TarURIPath` (they pin the format, which the extension-detecting `archive:`
# does not); these class names stay importable.
ArchiveZipURIPath = ZipURIPath
ArchiveTarURIPath = TarURIPath
