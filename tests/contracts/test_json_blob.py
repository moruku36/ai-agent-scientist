"""J01-J08: strict JSON reads of BlobStore bytes (authored; not yet executed)."""
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from ai_agent_scientist.evidence import json_blob
from ai_agent_scientist.evidence.blob_store import (
    BlobIntegrityError,
    BlobIOError,
    BlobNotFound,
    BlobStore,
    BlobTooLarge,
)
from ai_agent_scientist.evidence.json_blob import (
    InvalidJSONBlob,
    load_json_blob,
    parse_json_bytes,
)

CAP = 4096
BS = bytes([92])
SENT = "zq-sentinel-key"
PARSE = "ai_agent_scientist.evidence.json_blob.parse_json_bytes"


def snap(root):
    out = {}
    for d, _, names in os.walk(root):
        for n in names:
            p = Path(d) / n
            st = p.stat()
            out[str(p.relative_to(root))] = (st.st_size, st.st_mtime_ns, p.read_bytes())
    return out


class JsonBlobTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def put(self, data, store=None):
        store = store or BlobStore(self.root, max_blob_bytes=CAP)
        store.put(data)
        return store, hashlib.sha256(data).hexdigest()

    def test_J01_roundtrip(self):
        text = '{"name":"é☃","n":[1,2.5,-0.0,true,false,null],"o":{"k":"v"},"big":123456789012345678901234567890}'
        store, d = self.put(text.encode("utf-8"))
        got = load_json_blob(store, d)
        self.assertEqual(got, {"name": "é☃", "n": [1, 2.5, -0.0, True, False, None],
                               "o": {"k": "v"}, "big": 123456789012345678901234567890})
        for raw, want in ((b"3", 3), (b'"x"', "x"), (b"null", None), (b"[]", [])):
            s, dd = self.put(raw, store)
            self.assertEqual(load_json_blob(s, dd), want)

    def test_J02_duplicate_keys(self):
        esc = b'{"' + SENT.encode() + b'":1,"' + BS + b'u007aq-sentinel-key":2}'
        cases = [b'{"a":1,"a":2}', b'{"x":{"a":1,"b":2,"a":3}}', b'[{"k":1,"k":1}]',
                 b'{"' + SENT.encode() + b'":1,"' + SENT.encode() + b'":2}', esc]
        for raw in cases:
            with self.assertRaises(InvalidJSONBlob) as cm:
                parse_json_bytes(raw)
            self.assertNotIn(SENT, str(cm.exception))
            self.assertNotIn(SENT, repr(cm.exception))
        # No Unicode normalization: composed and decomposed keys differ.
        text = '{"%s":1,"e%s":2}' % (chr(0xE9), chr(0x301))
        self.assertEqual(len(parse_json_bytes(text.encode("utf-8"))), 2)

    def test_J03_nonfinite(self):
        for raw in (b"NaN", b"Infinity", b"-Infinity", b"[1e999]", b'{"a":[-1e999]}',
                    b'{"a":{"b":NaN}}', b'[[Infinity]]'):
            with self.assertRaises(InvalidJSONBlob):
                parse_json_bytes(raw)
        self.assertEqual(parse_json_bytes(b"[1.5,-2e3,1e-999]"), [1.5, -2000.0, 0.0])

    def test_J04_encodings(self):
        bom = bytes([0xEF, 0xBB, 0xBF])
        bad = [b'"' + bytes([0xFF]) + b'"', bom + b"{}"]
        for enc in ("utf-16", "utf-16-le", "utf-16-be", "utf-32", "utf-32-le"):
            bad.append("{}".encode(enc))
        for raw in bad:
            with self.assertRaises(InvalidJSONBlob):
                parse_json_bytes(raw)
        self.assertEqual(parse_json_bytes(b"{}"), {})

    def test_J05_malformed_and_types(self):
        for raw in (b"{", b"[1,]", b"{} x", b"{}{}", b"", b"   "):
            with self.assertRaises(InvalidJSONBlob) as cm:
                parse_json_bytes(raw)
            self.assertIsInstance(cm.exception.__cause__, ValueError)
        with self.assertRaises(InvalidJSONBlob) as cm:
            parse_json_bytes(bytes([0xFF]))
        self.assertIsInstance(cm.exception.__cause__, UnicodeDecodeError)

        class B(bytes):
            pass

        for bad in (B(b"{}"), bytearray(b"{}"), "{}", memoryview(b"{}"), None):
            with self.assertRaises(TypeError):
                parse_json_bytes(bad)
        import sys
        if sys.get_int_max_str_digits() > 0:
            with self.assertRaises(InvalidJSONBlob):
                parse_json_bytes(b"1" * (sys.get_int_max_str_digits() + 10))

    def test_J06_store_failures_skip_parse(self):
        store, d = self.put(b'{"a":1}')
        missing = hashlib.sha256(b"absent").hexdigest()
        with mock.patch(PARSE) as p:
            with self.assertRaises(BlobNotFound):
                load_json_blob(store, missing)
            files = [f for f in self.root.rglob("*") if f.is_file() and f.read_bytes() == b'{"a":1}']
            self.assertEqual(len(files), 1)
            files[0].write_bytes(b'{"a":2}')
            with self.assertRaises(BlobIntegrityError):
                load_json_blob(BlobStore(self.root, max_blob_bytes=CAP), d)
            p.assert_not_called()

    def test_J07_oversize_and_io(self):
        big = b'"' + b"a" * 200 + b'"'
        _, d = self.put(big)
        small = BlobStore(self.root, max_blob_bytes=64)
        with mock.patch(PARSE) as p:
            with self.assertRaises(BlobTooLarge):
                load_json_blob(small, d)
            p.assert_not_called()
            err = BlobIOError("injected")
            store = mock.Mock()
            store.get.side_effect = err
            digest = "ab" * 32
            with self.assertRaises(BlobIOError) as cm:
                load_json_blob(store, digest)
            self.assertIs(cm.exception, err)
            store.get.assert_called_once_with(digest)
            self.assertEqual(store.mock_calls, [mock.call.get(digest)])
            p.assert_not_called()

    def test_J08_representations_readonly_recursion(self):
        a = b'{"a":1,"b":[1,2]}'
        b = b"{ " + bytes([10]) + b' "b" : [1, 2] , "a" : 1 }'
        store, da = self.put(a)
        _, db = self.put(b, store)
        self.assertNotEqual(da, db)
        before = snap(self.root)
        fresh = BlobStore(self.root, max_blob_bytes=CAP)
        self.assertEqual(load_json_blob(fresh, da), load_json_blob(fresh, db))
        self.assertEqual(load_json_blob(fresh, da), {"a": 1, "b": [1, 2]})
        self.assertEqual(snap(self.root), before)
        with mock.patch.object(json_blob.json, "loads", side_effect=RecursionError):
            with self.assertRaises(InvalidJSONBlob) as cm:
                parse_json_bytes(b"[]")
        self.assertIsInstance(cm.exception.__cause__, RecursionError)


if __name__ == "__main__":
    unittest.main()
