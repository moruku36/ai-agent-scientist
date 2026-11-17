'''PRIVATE local reconciliation preview APPLICATION. Authored NOT EXECUTED.

Trusted in-process caller and receiver only. EXPLICIT action: re-verifies a
ReconciliationPreview against a fresh rebuild, then delegates ONCE to the
existing mark_recovery_for_reconciliation (inspect + receipt CAS). Adds no
store, receiver construction, clock, IO, process, network, tool use, retry or
authority, and does not authenticate human intent. See docs/33-recovery-apply.md.
'''
from __future__ import annotations

from ai_agent_scientist.admission.durable_handoff import DurableHandoffReceipts, DurableReceipt
from ai_agent_scientist.admission.recovery_operator import mark_recovery_for_reconciliation
from ai_agent_scientist.admission.recovery_preview import (
    ReconciliationPreview, RecoveryPreviewRefused, build_reconciliation_preview)

import hashlib

__all__ = ['RecoveryApplyRefused', 'apply_reconciliation_preview']

_MAX = 1048576
_HEX = '0123456789abcdef'


class RecoveryApplyRefused(ValueError):
    '''Value-free refusal; nothing was written.'''


def _refuse():
    raise RecoveryApplyRefused('recovery apply refused') from None


def _hex64(v):
    return type(v) is str and len(v) == 64 and all(c in _HEX for c in v)


def _check_shape(p):
    if type(p) is not ReconciliationPreview:
        _refuse()
    d = p.data
    if type(d) is not bytes or not 1 <= len(d) <= _MAX:
        _refuse()
    if not _hex64(p.sha256) or p.sha256 != hashlib.sha256(d).hexdigest():
        _refuse()
    if type(p.request_id) is not str or not 1 <= len(p.request_id) <= 1024:
        _refuse()
    if not _hex64(p.request_sha256):
        _refuse()
    if type(p.expected_revision) is not int or p.expected_revision < 1:
        _refuse()


def apply_reconciliation_preview(receiver: DurableHandoffReceipts,
                                 preview: ReconciliationPreview, *, now) -> DurableReceipt:
    '''EXPLICIT trusted-caller action: apply a previously built preview.

    Shape and hash are validated before any read. The preview is rebuilt ONCE
    from a fresh read; None, a state refusal or any difference from the
    supplied preview refuses before writing. Then exactly ONE delegation to
    mark_recovery_for_reconciliation (its own inspection and receipt CAS).
    The reads and CAS are separate snapshots: equality detects changes
    completed before the fresh rebuild, but a competing acknowledgment after
    the rebuild is NOT fenced (the CAS fences only the receipt revision).
    Already marked requests refuse. Other errors propagate; no retries.
    '''
    _check_shape(preview)
    try:
        rebuilt = build_reconciliation_preview(
            receiver, preview.request_id, max_output_bytes=_MAX)
    except RecoveryPreviewRefused:
        _refuse()
    if rebuilt is None or rebuilt != preview:
        _refuse()
    return mark_recovery_for_reconciliation(
        receiver, request_id=preview.request_id,
        expected_request_sha256=preview.request_sha256,
        expected_revision=preview.expected_revision, now=now)
