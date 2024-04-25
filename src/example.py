from pathlib_next.uri import UriPath, Query
from pathlib_next.uri.schemes import *
from pathlib_next.utils.sync import PathSyncer
from pathlib_next.utils import glob

query = Query({'test':'://$#!1', 'test2&': [1,2]})
q2 =  Query(str(query)).to_dict()
dest = UriPath('file:./_ssh')
dest = UriPath(dest)
test_ = UriPath('file:') / 'test'
empty = UriPath()
uri = dest.as_uri()

print(list(dest.iterdir()))
test1 = dest / 'test' / 'test2/'
print(test1)

sftp_root = UriPath('sftp://root@sftpexample/')
print(sftp_root.as_posix())
authkeys = sftp_root / 'root/.ssh/authorized_keys'
print(authkeys.as_posix())

def checksum(uri:UriPath):
    stat = uri.stat()
    return hash(stat.st_size)
syncer =PathSyncer(checksum, remove_missing=False)
syncer.sync((sftp_root / 'root/.ssh'), dest, dry_run=True)

rocky_repo = UriPath('http://dl.rockylinux.org/pub')

glob_test = UriPath("file:./**/*.py")

for path in glob.glob(glob_test, recursive=True):
    print(path)

print(rocky_repo.is_dir())
print(list(rocky_repo.iterdir()))
