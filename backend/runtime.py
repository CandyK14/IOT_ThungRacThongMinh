import os


class SingleWorker:
    """OS lock prevents concurrent bot polling/outbox dispatch for the same database."""
    def __init__(self,path): self.path=path;self.file=None

    def acquire(self):
        self.file=open(str(self.path)+'.worker.lock','a+b')
        if os.name=='nt':
            import msvcrt
            if self.file.tell()==0:self.file.write(b'0');self.file.flush()
            self.file.seek(0)
            try:msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:self.file.close();raise RuntimeError('DB đã có một backend worker; dùng uvicorn --workers 1') from None
        else:
            import fcntl
            try:fcntl.flock(self.file,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError:self.file.close();raise RuntimeError('DB đã có backend worker') from None

    def release(self):
        if self.file:self.file.close();self.file=None
