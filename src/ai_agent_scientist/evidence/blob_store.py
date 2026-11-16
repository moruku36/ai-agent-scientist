"""Local immutable exact-byte evidence blob helper (standard library only).

Proposed/implemented scope: store and verify opaque bytes under their SHA-256
digest in one trusted, owner-controlled directory. It accepts no records,
issues no receipts, authorizes nothing and performs no JSON canonicalization.

Trust profile: single trusted owner / single writer on POSIX. The root and its
ancestors are trusted and must not be controlled concurrently by an attacker.
The helper fails closed when the required primitives are unavailable.
"""

from __future__ import annotations

import errno
import hashlib
import os
import stat
import uuid
from pathlib import Path

__all__ = [
    "BlobStore",
    "BlobStoreError",
    "InvalidInput",
    "BlobTooLarge",
    "BlobNotFound",
    "BlobIntegrityError",
    "BlobIOError",
]

_HEX = frozenset("0123456789abcdef")
_CHUNK = 65536


class BlobStoreError(Exception):
    """Base class. Messages never contain payload bytes."""


class InvalidInput(BlobStoreError):
    """Invalid type, cap, digest or root shape."""


class BlobTooLarge(BlobStoreError):
    """Data or stored object exceeds the configured cap."""


class BlobNotFound(BlobStoreError):
    """No final object exists for a valid digest."""


class BlobIntegrityError(BlobStoreError):
    """Stored bytes do not match the digest, or the final entry is a symlink/nonregular."""


class BlobIOError(BlobStoreError):
    """Filesystem failure or unsupported primitive. The cause is chained."""


def _valid_digest(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(c in _HEX for c in value)


class BlobStore:
    def __init__(self, root: Path, *, max_blob_bytes: int) -> None:
        if not isinstance(root, Path):
            raise InvalidInput("root must be a pathlib.Path")
        if type(max_blob_bytes) is not int or max_blob_bytes < 1:
            raise InvalidInput("max_blob_bytes must be an int >= 1")
        self._require_primitives()
        self._root = root
        self._cap = max_blob_bytes
        self._check_root()

    # ------------------------------------------------------------------ public

    def put(self, data: bytes) -> str:
        if type(data) is not bytes:
            raise InvalidInput("data must be exact bytes")
        if len(data) > self._cap:
            raise BlobTooLarge("data exceeds max_blob_bytes")
        self._check_root()
        digest = hashlib.sha256(data).hexdigest()
        final = self._root / digest

        # Existing destination: verify, never overwrite or repair.
        try:
            self._read_final(final, digest)
            return digest
        except BlobNotFound:
            pass

        stage = self._root / (".%s.%s.stage" % (digest, uuid.uuid4().hex))
        created = None
        try:
            fd = self._open_stage(stage)
            created = stage
            self._fill_stage(fd, data)
            try:
                os.link(stage, final)
            except FileExistsError:
                # Lost an install race or appeared meanwhile: verify, no replacement.
                self._read_final(final, digest)
            except OSError as exc:
                raise BlobIOError("cannot install blob") from exc
            self._unlink_stage(created)
            created = None
            self._fsync_dir()
        except BaseException as exc:
            cleanup_err = self._cleanup(created)
            if cleanup_err is not None:
                exc.add_note("staging cleanup also failed: %r" % (cleanup_err,))
            raise
        return digest

    def get(self, sha256: str) -> bytes:
        if not _valid_digest(sha256):
            raise InvalidInput("sha256 must be 64 lowercase hex characters")
        self._check_root()
        return self._read_final(self._root / sha256, sha256)

    # ----------------------------------------------------------------- helpers

    @staticmethod
    def _require_primitives() -> None:
        needed = ("link", "fsync", "O_NOFOLLOW", "O_DIRECTORY", "O_EXCL")
        missing = [n for n in needed if not hasattr(os, n)]
        if missing:
            raise BlobIOError("unsupported platform primitives: %s" % ", ".join(missing))

    def _check_root(self) -> None:
        try:
            st = os.lstat(self._root)
        except (FileNotFoundError, NotADirectoryError) as exc:
            raise InvalidInput("root does not exist") from exc
        except OSError as exc:
            raise BlobIOError("cannot inspect root") from exc
        if stat.S_ISLNK(st.st_mode):
            raise InvalidInput("root must not be a symlink")
        if not stat.S_ISDIR(st.st_mode):
            raise InvalidInput("root must be a directory")

    def _read_final(self, path: Path, digest: str) -> bytes:
        try:
            st = os.lstat(path)
        except FileNotFoundError as exc:
            raise BlobNotFound("blob not found") from exc
        except OSError as exc:
            raise BlobIOError("cannot inspect blob") from exc
        if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
            raise BlobIntegrityError("final entry is a symlink or not a regular file")
        if st.st_size > self._cap:
            raise BlobTooLarge("stored object exceeds max_blob_bytes")
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        try:
            fd = os.open(path, flags)
        except FileNotFoundError as exc:
            raise BlobNotFound("blob disappeared") from exc
        except OSError as exc:
            if exc.errno == errno.ELOOP:
                raise BlobIntegrityError("final entry is a symlink") from exc
            raise BlobIOError("cannot open blob") from exc
        try:
            data = self._read_fd(fd)
        except OSError as exc:
            self._close_quiet(fd)
            raise BlobIOError("cannot read blob") from exc
        except BaseException:
            self._close_quiet(fd)
            raise
        try:
            os.close(fd)
        except OSError as exc:
            raise BlobIOError("cannot close blob") from exc
        if hashlib.sha256(data).hexdigest() != digest:
            raise BlobIntegrityError("stored bytes do not match digest")
        return data

    def _read_fd(self, fd: int) -> bytes:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise BlobIntegrityError("final entry is not a regular file")
        remaining = self._cap + 1
        chunks = []
        while remaining > 0:
            chunk = os.read(fd, min(_CHUNK, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > self._cap:
            raise BlobTooLarge("stored object exceeds max_blob_bytes")
        return data

    def _open_stage(self, stage: Path) -> int:
        flags = (
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        )
        try:
            return os.open(stage, flags, 0o600)
        except OSError as exc:
            raise BlobIOError("cannot create staging file") from exc

    def _fill_stage(self, fd: int, data: bytes) -> None:
        try:
            view = memoryview(data)
            off = 0
            while off < len(data):
                n = os.write(fd, view[off:])
                if n <= 0:
                    raise OSError(errno.EIO, "zero-length write")
                off += n
            os.fsync(fd)
        except OSError as exc:
            self._close_quiet(fd)
            raise BlobIOError("cannot write staging file") from exc
        except BaseException:
            self._close_quiet(fd)
            raise
        try:
            os.close(fd)
        except OSError as exc:
            raise BlobIOError("cannot close staging file") from exc

    def _unlink_stage(self, stage: Path) -> None:
        try:
            os.unlink(stage)
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise BlobIOError("cannot remove staging file") from exc

    def _cleanup(self, stage):
        if stage is None:
            return None
        try:
            os.unlink(stage)
        except FileNotFoundError:
            return None
        except OSError as exc:
            return exc
        return None

    def _fsync_dir(self) -> None:
        try:
            fd = os.open(
                self._root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
            )
        except OSError as exc:
            raise BlobIOError("cannot open root for directory sync") from exc
        try:
            os.fsync(fd)
        except OSError as exc:
            self._close_quiet(fd)
            raise BlobIOError("directory sync failed") from exc
        try:
            os.close(fd)
        except OSError as exc:
            raise BlobIOError("cannot close root") from exc

    @staticmethod
    def _close_quiet(fd: int) -> None:
        try:
            os.close(fd)
        except OSError:
            pass
