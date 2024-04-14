from uripath.uri import Uri
from uripath.schemes import *
from uripath.sync import PathSync

dest = Uri('file:./_ssh')
uri = dest.as_uri()

sftp_root = Uri('sftp://root@sftpexample/')
authkeys = sftp_root / 'root/.ssh/authorized_keys'

def checksum(uri:Uri):
    stat = uri.stat()
    return hash(stat.st_size)
syncer =PathSync(checksum, remove_missing=False)
syncer.sync((sftp_root / 'root/.ssh'), dest, dry_run=False)
