# Archives: `zip:`, `tar:`, `archive:`

`archive+zip:` and `archive+tar:` are second scheme names of `ZipURIPath` and
`TarURIPath` (they pin the format, which `archive:` detects); `ArchiveZipURIPath` and
`ArchiveTarURIPath` stay importable as aliases of those two classes.

::: uripath.schemes.ArchiveURIPath

::: uripath.schemes.ZipURIPath

::: uripath.schemes.TarURIPath

`uripath.schemes.MEMBER_SPOOL_BYTES` is the size above which the content of an
archive member read into memory is spooled to a temporary file; assign a
different number to change it.
