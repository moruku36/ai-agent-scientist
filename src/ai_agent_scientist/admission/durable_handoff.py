"""Receiver-owned offline byte-bound receipts; no admission or dispatch.

Only a partial docs11 profile: exact envelope bytes, NOT logical/JCS identity.
The caller declares an independently authenticated principal/mapping, current
bindings/time/stores and a private local DB path, all outside candidate control.
See docs/22-durable-handoff-receipt.md for trust and resource assumptions.
"""
from __future__ import annotations

import os
import re
import sqlite3
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ai_agent_scientist.admission.handoff_binding import (
    PayloadBinding, load_bound_handoff_request,
)
from ai_agent_scientist.evidence.blob_store import BlobStore

__all__ = [
    'TrustedHandoffScope', 'DurableReceipt', 'DurableHandoffReceipts',
    'ReceiptConflict', 'ReceiptRevisionError', 'InvalidReceiptTransition',
    'ReceiptScopeError', 'ReceiptStorageError',
]

_MAX_INT = (1 << 63) - 1
_ROLES = ('scientist', 'ctf', 'sleep', 'evaluator')
_COLUMNS = ('principal, project_id, recipient, request_id, sender, message_id, '
            'request_sha256, payload_sha256, revision, state, recorded_at, updated_at')
_KEY = 'principal=? AND project_id=? AND recipient=? AND request_id=?'


class ReceiptConflict(ValueError):
    """A request or delivery key is already bound to different exact bytes."""


class ReceiptRevisionError(ValueError):
    """Invalid, stale or overflowing receiver revision."""


class InvalidReceiptTransition(ValueError):
    """No forward transition exists from the retained unresolved state."""


class ReceiptScopeError(ValueError):
    """Wire endpoints/project do not match the independently trusted mapping."""


class ReceiptStorageError(Exception):
    """Local SQLite/filesystem failure; chained diagnostics are owner-only."""


@dataclass(frozen=True, slots=True)
class TrustedHandoffScope:
    principal: str
    project_id: str
    sender: str
    recipient: str


@dataclass(frozen=True, slots=True)
class DurableReceipt:
    principal: str
    project_id: str
    recipient: str
    request_id: str
    sender: str
    message_id: str
    request_sha256: str
    payload_sha256: str
    revision: int
    state: str
    recorded_at: str
    updated_at: str


def _text(value: object) -> str:
    # Guard before comparisons, encoding or SQL binding; bound local metadata.
    if type(value) is not str or not value:
        raise TypeError('receipt identifiers must be exact nonempty strings')
    try:
        size = len(value.encode('utf-8'))
    except UnicodeError:
        raise ValueError('invalid receipt identifier') from None
    if size > 1024 or '\x00' in value:
        raise ValueError('invalid receipt identifier')
    return value


def _clock(now: datetime) -> str:
    if type(now) is not datetime or now.tzinfo is not timezone.utc:
        raise TypeError('now must be a UTC-aware datetime')
    return now.isoformat(timespec='microseconds').replace('+00:00', 'Z')


def _revision(value: object) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_INT:
        raise ReceiptRevisionError('invalid receipt revision')
    return value


class DurableHandoffReceipts:
    """One trusted local SQLite path and immutable caller identity mapping.

    Constructor initializes only the private internal table. Each operation
    opens/closes its own connection. No payload or complete envelope is stored.
    Authentication and filesystem ownership provisioning are caller duties.
    """

    def __init__(self, db_path: str, *, scope: TrustedHandoffScope) -> None:
        if type(scope) is not TrustedHandoffScope:
            raise TypeError('scope must be an exact TrustedHandoffScope')
        for value in (scope.principal, scope.project_id, scope.sender, scope.recipient):
            _text(value)
        if scope.sender not in _ROLES or scope.recipient not in _ROLES:
            raise ValueError('invalid trusted endpoint mapping')
        if type(db_path) is not str or not db_path or '\x00' in db_path:
            raise TypeError('db_path must be an absolute local string path')
        path = Path(db_path)
        if not path.is_absolute() or '..' in path.parts:
            raise ValueError('db_path must be an absolute local path')
        self._path, self._scope = path, scope
        self._identity = None
        try:
            self._check_directory()
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
            except FileExistsError:
                pass
            else:
                os.close(fd)
            self._check_path()
        except OSError as exc:
            raise ReceiptStorageError('cannot prepare receipt database') from exc
        with self._transaction(write=True) as conn:
            # Internal-only schema; does not change any canonical/wire schema.
            conn.execute('''CREATE TABLE IF NOT EXISTS durable_handoff_receipts (
                principal TEXT NOT NULL, project_id TEXT NOT NULL,
                recipient TEXT NOT NULL, request_id TEXT NOT NULL,
                sender TEXT NOT NULL, message_id TEXT NOT NULL,
                request_sha256 TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
                revision INTEGER NOT NULL, state TEXT NOT NULL,
                recorded_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                PRIMARY KEY (principal, project_id, recipient, request_id),
                UNIQUE (principal, project_id, recipient, message_id),
                CHECK ((revision=1 AND state='recorded') OR
                       (revision=2 AND state='reconciliation_required'))
            )''')

    def _check_directory(self) -> None:
        # Best-effort accidental misconfiguration checks, not hostile DB defense.
        for parent in self._path.parents:
            if not stat.S_ISDIR(os.lstat(parent).st_mode):
                raise ReceiptStorageError('database ancestors must be real directories')
        root = os.lstat(self._path.parent)
        if root.st_uid != os.getuid() or stat.S_IMODE(root.st_mode) & 0o077:
            raise ReceiptStorageError('database parent must be private and owner-controlled')

    def _check_path(self) -> None:
        self._check_directory()
        info = os.lstat(self._path)
        if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077):
            raise ReceiptStorageError('database must be a private owner-controlled regular file')
        identity = (info.st_dev, info.st_ino)
        if self._identity is not None and identity != self._identity:
            raise ReceiptStorageError('database file was replaced')
        self._identity = identity

    @contextmanager
    def _transaction(self, *, write: bool):
        conn = None
        failure = None
        try:
            self._check_path()
            conn = sqlite3.connect(str(self._path), timeout=1.0, isolation_level=None, uri=False)
            conn.execute('PRAGMA synchronous=FULL')
            conn.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            try:
                yield conn
                conn.commit()
            except BaseException as exc:
                if conn.in_transaction:
                    try:
                        conn.rollback()
                    except sqlite3.Error:
                        exc.add_note('receipt rollback failed; inspect retained state before reuse')
                raise
        except (sqlite3.Error, OSError) as exc:
            failure = ReceiptStorageError('receipt database operation failed')
            raise failure from exc
        except BaseException as exc:
            failure = exc
            raise
        finally:
            if conn is not None:
                try:
                    conn.close()
                except sqlite3.Error as exc:
                    if failure is None:
                        raise ReceiptStorageError('cannot close receipt database') from exc
                    failure.add_note('receipt database close also failed')

    def _key(self, request_id: str) -> tuple:
        scope = self._scope
        return (scope.principal, scope.project_id, scope.recipient, _text(request_id))

    def _read(self, conn, request_id: str) -> DurableReceipt | None:
        row = conn.execute('SELECT ' + _COLUMNS + ' FROM durable_handoff_receipts WHERE ' + _KEY,
                           self._key(request_id)).fetchone()
        if row is None:
            return None
        receipt = DurableReceipt(*row)
        if receipt.sender != self._scope.sender:
            raise ReceiptScopeError('retained receipt mapping differs')
        return receipt

    def record(self, request_store: BlobStore, request_sha256: str, *,
               payload_store: BlobStore, bindings: dict[str, PayloadBinding],
               now: datetime) -> DurableReceipt:
        """Fresh bound load on BOTH creation and replay, then atomic dedup.

        request_sha256 identifies the original verified envelope bytes. Payload
        bytes are verified by the real loader then discarded, never persisted.
        A duplicate returns the current durable unresolved revision/state.
        """
        stamp = _clock(now)
        if type(request_sha256) is not str or re.fullmatch('[a-f0-9]{64}', request_sha256) is None:
            raise ValueError('invalid receipt request digest')
        request, payload = load_bound_handoff_request(
            request_store, request_sha256, payload_store=payload_store, bindings=bindings, now=now)
        del payload
        scope = self._scope
        if (request['project_id'], request['sender'], request['recipient']) != (
                scope.project_id, scope.sender, scope.recipient):
            raise ReceiptScopeError('request does not match trusted scope')
        for key in ('request_id', 'message_id'):
            _text(request[key])
        if _revision(request['expected_revision']) != 0:
            raise ReceiptRevisionError('only initial revision zero can be recorded')
        with self._transaction(write=True) as conn:
            current = self._read(conn, request['request_id'])
            if current is not None:
                if current.request_sha256 != request_sha256:
                    raise ReceiptConflict('request key already binds different bytes')
                return current
            collision = conn.execute(
                'SELECT 1 FROM durable_handoff_receipts WHERE principal=? AND project_id=? '
                'AND recipient=? AND message_id=?',
                (scope.principal, scope.project_id, scope.recipient, request['message_id'])).fetchone()
            if collision is not None:
                raise ReceiptConflict('message key already binds another request')
            receipt = DurableReceipt(
                scope.principal, scope.project_id, scope.recipient, request['request_id'],
                scope.sender, request['message_id'], request_sha256, request['payload']['sha256'],
                1, 'recorded', stamp, stamp)
            conn.execute('INSERT INTO durable_handoff_receipts (' + _COLUMNS +
                         ') VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
                         tuple(getattr(receipt, name.strip()) for name in _COLUMNS.split(',')))
            return receipt

    def inspect(self, request_id: str) -> DurableReceipt | None:
        """Local retained metadata only; no blob access or continuing authority."""
        _text(request_id)
        with self._transaction(write=False) as conn:
            return self._read(conn, request_id)

    def require_reconciliation(self, request_id: str, *, expected_revision: int,
                               now: datetime) -> DurableReceipt:
        """Receiver-local CAS: recorded -> reconciliation_required, once only.

        No access to blobs is implied. Neither state permits work, settlement,
        retry, cancellation, completion or reservation/budget changes.
        """
        _text(request_id)
        revision = _revision(expected_revision)
        stamp = _clock(now)
        if revision == _MAX_INT:
            raise ReceiptRevisionError('receipt revision would overflow')
        with self._transaction(write=True) as conn:
            current = self._read(conn, request_id)
            if current is None or current.revision != revision:
                raise ReceiptRevisionError('stale receipt revision')
            if current.state != 'recorded':
                raise InvalidReceiptTransition('receipt already requires reconciliation')
            if stamp < current.updated_at:
                raise ValueError('receipt clock moved backward')
            changed = conn.execute(
                'UPDATE durable_handoff_receipts SET revision=revision+1, '
                "state='reconciliation_required', updated_at=? WHERE " + _KEY +
                " AND revision=? AND state='recorded'",
                (stamp, *self._key(request_id), revision))
            if changed.rowcount != 1:
                raise ReceiptRevisionError('stale receipt revision')
            return self._read(conn, request_id)
