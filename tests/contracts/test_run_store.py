"""Scientist27: exactly four self-contained scenarios; authored, NOT EXECUTED."""
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from ai_agent_scientist.evidence.blob_store import BlobIntegrityError, BlobStore
from ai_agent_scientist.records.run_record import RunRecordRefused
from ai_agent_scientist.records.run_store import (
    RunStoreRefused,
    load_run_record,
    store_run_record,
)


class RunStoreTests(unittest.TestCase):
    def test_S01_private_exact_byte_roundtrip_with_null_usage(self):
        raw = (
            b' {\n "run_id":"run-1", "attempt_id":"attempt-1",'
            b' "replicate_id":"replicate-1", "project_id":"project-1",'
            b' "protocol_revision":"protocol-1", "candidate_revision":"candidate-1",'
            b' "status":"failed", "validity":"unchecked", "artifacts":[], '
            b'"metrics":{"score":null}, '
            b'"usage":{"wall_seconds":null,"incremental_api_usd":null},'
            b' "limitations":["Synthetic; no evaluation."]\n}\n'
        )
        digest = hashlib.sha256(raw).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = BlobStore(root, max_blob_bytes=len(raw))
            with mock.patch.object(store, "put", wraps=store.put) as put:
                stored = store_run_record(store, raw, max_bytes=len(raw))
                put.assert_called_once_with(raw)
                self.assertIs(put.call_args.args[0], raw)
            with mock.patch.object(store, "get", wraps=store.get) as get:
                loaded = load_run_record(store, digest, max_bytes=len(raw))
                get.assert_called_once_with(digest)
            self.assertIs(stored.data, raw)
            self.assertEqual(stored.sha256, digest)
            self.assertEqual(loaded, stored)
            self.assertEqual(loaded.data, raw)
            self.assertEqual((root / digest).read_bytes(), raw)
            self.assertIsNone(loaded.usage.wall_seconds)
            self.assertIsNone(loaded.usage.incremental_api_usd)

    def test_S02_invalid_record_is_rejected_before_put_without_writes(self):
        raw = b'{"run_id":"private-sentinel"}'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = BlobStore(root, max_blob_bytes=1024)
            with mock.patch.object(store, "put", wraps=store.put) as put:
                with self.assertRaises(RunRecordRefused) as refused:
                    store_run_record(store, raw)
                put.assert_not_called()
            self.assertEqual(tuple(root.iterdir()), ())
            self.assertEqual(refused.exception.args, ("run record refused",))
            self.assertIsNone(refused.exception.__cause__)
            self.assertIsNone(refused.exception.__context__)

    def test_S03_invalid_digest_is_rejected_before_get(self):
        digest = "A" * 64
        with tempfile.TemporaryDirectory() as directory:
            store = BlobStore(Path(directory), max_blob_bytes=1024)
            with mock.patch.object(store, "get", wraps=store.get) as get:
                with self.assertRaises(RunStoreRefused) as refused:
                    load_run_record(store, digest)
                get.assert_not_called()
            self.assertEqual(refused.exception.args, ("run store refused",))
            self.assertIsNone(refused.exception.__cause__)
            self.assertIsNone(refused.exception.__context__)

    def test_S04_tampered_blob_preserves_actual_integrity_error_without_retry(self):
        raw = (
            b'{"run_id":"run-1","attempt_id":"attempt-1",'
            b'"replicate_id":"replicate-1","project_id":"project-1",'
            b'"protocol_revision":"protocol-1","candidate_revision":"candidate-1",'
            b'"status":"failed","validity":"unchecked","artifacts":[], '
            b'"metrics":{},"usage":{"wall_seconds":null,"incremental_api_usd":null},'
            b'"limitations":[]}'
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = BlobStore(root, max_blob_bytes=1024)
            digest = store.put(raw)
            final = root / digest
            final.write_bytes(b"tampered")
            actual_get = store.get
            storage_error = None

            def observe_get(requested):
                nonlocal storage_error
                try:
                    return actual_get(requested)
                except BlobIntegrityError as error:
                    storage_error = error
                    raise

            with mock.patch.object(store, "get", side_effect=observe_get) as get:
                with self.assertRaises(BlobIntegrityError) as refused:
                    load_run_record(store, digest)
                get.assert_called_once_with(digest)
            self.assertIs(refused.exception, storage_error)
            self.assertEqual(final.read_bytes(), b"tampered")
