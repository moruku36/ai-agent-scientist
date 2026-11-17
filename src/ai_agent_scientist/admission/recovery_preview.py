'''PRIVATE local reconciliation PREVIEW artifact. Authored NOT EXECUTED.

Trusted in-process caller and receiver only. Joins ONE real selected recovery
detail (render_recovery_detail) to a reviewable description of the action
mark_reconciliation_required. It NEVER executes that action and adds no
receiver construction, write, clock, IO, process, network or tool use. The
artifact hash covers the exact preview bytes only; it is not a CAS token, not
authentic human confirmation and not authority. See docs/32-recovery-preview.md.
'''
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from ai_agent_scientist.admission.durable_handoff import DurableHandoffReceipts
from ai_agent_scientist.admission.recovery_console import MAX_CONSOLE_BYTES
from ai_agent_scientist.admission.recovery_operator import render_recovery_detail

__all__ = ['ReconciliationPreview', 'RecoveryPreviewRefused',
           'RecoveryPreviewTooLarge', 'build_reconciliation_preview']

_VERSION = 'recovery-reconciliation-preview/1'
_ACTION = 'mark_reconciliation_required'
_LIMITS = ('PRIVATE LOCAL PREVIEW ONLY. Not authority. Not executed. Does not stop, '
           'release, settle, authorize, dispatch or complete anything. The hash '
           'identifies these bytes, not a CAS token or human confirmation. A future '
           'application must re-read and compare before the receipt CAS; snapshot '
           'races remain.')


class RecoveryPreviewRefused(ValueError):
    '''Value-free refusal; the request is not in state recorded.'''


class RecoveryPreviewTooLarge(ValueError):
    '''Value-free refusal; whole artifact exceeds the byte cap.'''


@dataclass(frozen=True, slots=True)
class ReconciliationPreview:
    '''Immutable private bytes. sha256 is of data, never authorization.'''

    data: bytes
    sha256: str
    request_id: str
    request_sha256: str
    expected_revision: int


def build_reconciliation_preview(receiver: DurableHandoffReceipts, request_id: str, *,
                                 max_output_bytes: int = 65536
                                 ) -> ReconciliationPreview | None:
    '''Build a preview from ONE render_recovery_detail call, or None.

    None means missing or receipt-only. Cap is validated before any read.
    Writes nothing; the action is described, never performed.
    '''
    if type(max_output_bytes) is not int or not 1 <= max_output_bytes <= MAX_CONSOLE_BYTES:
        raise ValueError('max_output_bytes must be an exact integer in 1..1048576')
    detail = render_recovery_detail(receiver, request_id, max_output_bytes=MAX_CONSOLE_BYTES)
    if detail is None:
        return None
    if detail.state != 'recorded':
        raise RecoveryPreviewRefused('recovery preview refused') from None
    body = {
        'version': _VERSION,
        'action': _ACTION,
        'request_id': detail.request_id,
        'request_sha256': detail.request_sha256,
        'expected_revision': detail.revision,
        'source_detail_sha256': hashlib.sha256(detail.text.encode('ascii')).hexdigest(),
        'source_detail_text': detail.text,
        'limitations': _LIMITS,
    }
    text = json.dumps(body, sort_keys=True, ensure_ascii=True, separators=(',', ':'))
    data = text.replace('\x7f', '\\u007f').encode('ascii')
    if len(data) > max_output_bytes:
        raise RecoveryPreviewTooLarge('recovery preview exceeds byte limit') from None
    return ReconciliationPreview(data, hashlib.sha256(data).hexdigest(), detail.request_id,
                                 detail.request_sha256, detail.revision)
