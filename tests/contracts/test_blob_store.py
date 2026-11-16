"""Twelve authored offline cases E01-E12 for the immutable blob helper.

Authored; execution is pending coordinator allocation. Temporary directories
only, deterministic mocks, no chmod and no global environment changes.
"""

import errno
import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from ai_agent_scientist.evidence import blob_store as bs  # noqa: E402

EMPTY = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
ABC = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def _sha(data):
    return hashlib.sha256(data).hexdigest()


class BlobStoreContract(unittest.TestCase):
    def _store(self, cap=64):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        return bs.BlobStore(root, max_blob_bytes=cap), root

    def test_E01(self):
        store, root = self._store()
        self.assertEqual(store.put(b"abc"), ABC)
        self.assertEqual(store.put(b""), EMPTY)
        self.assertEqual(sorted(os.listdir(root)), sorted([ABC, EMPTY]))
        self.assertEqual((root / ABC).read_bytes(), b"abc")
        self.assertEqual(store.get(ABC), b"abc")
        self.assertEqual(store.get(EMPTY), b"")

    def test_E02(self):
        store, root = self._store()
        d1 = store.put(b"same bytes")
        ino = os.stat(root / d1).st_ino
        other = bs.BlobStore(root, max_blob_bytes=64)
        d2 = other.put(b"same bytes")
        self.assertEqual(d1, d2)
        self.assertEqual(os.listdir(root), [d1])
        self.assertEqual(os.stat(root / d1).st_ino, ino)
        self.assertEqual((root / d1).read_bytes(), b"same bytes")

    def test_E03(self):
        store, root = self._store()
        payloads = [b'{"a":1}', b'{"a": 1}\n', b'{"a":2}']
        digests = [store.put(p) for p in payloads]
        self.assertEqual(len(set(digests)), 3)
        self.assertEqual(sorted(os.listdir(root)), sorted(digests))
        for p, d in zip(payloads, digests):
            self.assertEqual(d, _sha(p))
            self.assertEqual(store.get(d), p)

    def test_E04(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        root = base / "root"
        root.mkdir()
        for bad_cap in (True, 0, -1, 1.0, "8"):
            with self.assertRaises(bs.InvalidInput):
                bs.BlobStore(root, max_blob_bytes=bad_cap)
        with self.assertRaises(bs.InvalidInput):
            bs.BlobStore(base / "missing", max_blob_bytes=8)
        afile = base / "file"
        afile.write_bytes(b"x")
        with self.assertRaises(bs.InvalidInput):
            bs.BlobStore(afile, max_blob_bytes=8)
        link = base / "link"
        os.symlink(root, link)
        with self.assertRaises(bs.InvalidInput):
            bs.BlobStore(link, max_blob_bytes=8)
        with mock.patch.object(bs.os, "lstat", side_effect=PermissionError(errno.EACCES, "denied")):
            with self.assertRaises(bs.BlobIOError) as ctx:
                bs.BlobStore(root, max_blob_bytes=8)
        self.assertIsInstance(ctx.exception.__cause__, PermissionError)
        store = bs.BlobStore(root, max_blob_bytes=8)
        for bad in (bytearray(b"a"), "a", None):
            with self.assertRaises(bs.InvalidInput):
                store.put(bad)
        self.assertEqual(os.listdir(root), [])

    def test_E05(self):
        store, root = self._store(cap=8)
        d = store.put(b"12345678")
        with self.assertRaises(bs.BlobTooLarge):
            store.put(b"123456789")
        self.assertEqual(os.listdir(root), [d])
        self.assertEqual(store.get(d), b"12345678")

    def test_E06(self):
        store, root = self._store()
        bad = [ABC.upper(), "../" + ABC[3:], ABC[:63], "g" * 64, ABC + "0", "", None, 5, b"a" * 64]
        with mock.patch.object(bs.os, "lstat", side_effect=AssertionError("fs touched")), \
                mock.patch.object(bs.os, "open", side_effect=AssertionError("fs touched")):
            for value in bad:
                with self.assertRaises(bs.InvalidInput):
                    store.get(value)
        self.assertEqual(os.listdir(root), [])

    def test_E07(self):
        store, root = self._store()
        with self.assertRaises(bs.BlobNotFound):
            store.get(ABC)
        d = store.put(b"abc")
        with mock.patch.object(bs.os, "open", side_effect=PermissionError(errno.EACCES, "denied")):
            with self.assertRaises(bs.BlobIOError) as ctx:
                store.get(d)
        self.assertIsInstance(ctx.exception.__cause__, PermissionError)
        with mock.patch.object(bs.os, "read", side_effect=OSError(errno.EIO, "io")):
            with self.assertRaises(bs.BlobIOError):
                store.get(d)
        self.assertEqual(store.get(d), b"abc")

    def test_E08(self):
        store, root = self._store()
        d = store.put(b"original")
        (root / d).write_bytes(b"tampered")
        with self.assertRaises(bs.BlobIntegrityError):
            store.get(d)
        with self.assertRaises(bs.BlobIntegrityError):
            store.put(b"original")
        self.assertEqual((root / d).read_bytes(), b"tampered")
        self.assertEqual(os.listdir(root), [d])

    def test_E09(self):
        store, root = self._store(cap=8)
        big = b"123456789"
        (root / _sha(big)).write_bytes(big)
        with self.assertRaises(bs.BlobTooLarge):
            store.get(_sha(big))
        target = root.parent / (root.name + "-target")
        target.write_bytes(b"x")
        self.addCleanup(lambda: target.exists() and target.unlink())
        os.symlink(target, root / _sha(b"x"))
        with self.assertRaises(bs.BlobIntegrityError):
            store.get(_sha(b"x"))
        with self.assertRaises(bs.BlobIntegrityError):
            store.put(b"x")
        os.mkdir(root / _sha(b"y"))
        with self.assertRaises(bs.BlobIntegrityError):
            store.get(_sha(b"y"))
        with self.assertRaises(bs.BlobIntegrityError):
            store.put(b"y")
        self.assertTrue(os.path.islink(root / _sha(b"x")))
        self.assertTrue(os.path.isdir(root / _sha(b"y")))

    def test_E10(self):
        real_unlink = os.unlink
        with self.subTest("write failure"):
            store, root = self._store()
            with mock.patch.object(bs.os, "write", side_effect=OSError(errno.EIO, "io")):
                with self.assertRaises(bs.BlobIOError) as ctx:
                    store.put(b"abc")
            self.assertIsInstance(ctx.exception.__cause__, OSError)
            self.assertEqual(os.listdir(root), [])
        with self.subTest("fsync failure"):
            store, root = self._store()
            with mock.patch.object(bs.os, "fsync", side_effect=OSError(errno.EIO, "io")):
                with self.assertRaises(bs.BlobIOError):
                    store.put(b"abc")
            self.assertEqual(os.listdir(root), [])
        with self.subTest("link failure"):
            store, root = self._store()
            with mock.patch.object(bs.os, "link", side_effect=OSError(errno.EPERM, "no")):
                with self.assertRaises(bs.BlobIOError):
                    store.put(b"abc")
            self.assertEqual(os.listdir(root), [])
            with self.assertRaises(bs.BlobNotFound):
                store.get(ABC)
        with self.subTest("cleanup failure is reported"):
            store, root = self._store()
            with mock.patch.object(bs.os, "unlink", side_effect=PermissionError(errno.EACCES, "no")):
                with self.assertRaises(bs.BlobIOError):
                    store.put(b"abc")
            self.assertEqual(store.get(ABC), b"abc")
            for name in os.listdir(root):
                if name != ABC:
                    real_unlink(root / name)

    def test_E11(self):
        def make_racer(content):
            def racer(src, dst, *a, **k):
                with open(dst, "wb") as fh:
                    fh.write(content)
                raise FileExistsError(errno.EEXIST, "exists")
            return racer

        store, root = self._store()
        with mock.patch.object(bs.os, "link", side_effect=make_racer(b"abc")):
            self.assertEqual(store.put(b"abc"), ABC)
        self.assertEqual(os.listdir(root), [ABC])
        self.assertEqual((root / ABC).read_bytes(), b"abc")

        store2, root2 = self._store()
        with mock.patch.object(bs.os, "link", side_effect=make_racer(b"bad")):
            with self.assertRaises(bs.BlobIntegrityError):
                store2.put(b"abc")
        self.assertEqual(os.listdir(root2), [ABC])
        self.assertEqual((root2 / ABC).read_bytes(), b"bad")

    def test_E12(self):
        store, root = self._store()
        (root / ".orphan.stage").write_bytes(b"junk")
        real_fsync = os.fsync
        calls = [0]

        def flaky(fd):
            calls[0] += 1
            if calls[0] == 2:
                raise OSError(errno.EIO, "dir sync")
            return real_fsync(fd)

        with mock.patch.object(bs.os, "fsync", side_effect=flaky):
            with self.assertRaises(bs.BlobIOError):
                store.put(b"abc")
        self.assertEqual(sorted(os.listdir(root)), [".orphan.stage", ABC])
        reopened = bs.BlobStore(root, max_blob_bytes=64)
        ino = os.stat(root / ABC).st_ino
        self.assertEqual(reopened.get(ABC), b"abc")
        self.assertEqual(reopened.put(b"abc"), ABC)
        self.assertEqual(os.stat(root / ABC).st_ino, ino)
        self.assertEqual((root / ".orphan.stage").read_bytes(), b"junk")
        with self.assertRaises(bs.BlobNotFound):
            reopened.get(_sha(b"junk"))


if __name__ == "__main__":
    unittest.main()
