'''Offline NEW REQUEST preflight for harness-handoff/1.

Narrow, fixed-profile structural check of the REQUEST subset only. It is not
a schema engine, not admission, and not authorization: the synthetic flag is
structurally accepted in both values and grants nothing. Callers must still
authenticate the sender, resolve current authorization/reservation and payload
permissions, enforce idempotency/revisions and budget, and only then dispatch.

The UTC timestamp profile (YYYY-MM-DDTHH:MM:SS[.1-6 digits]Z) is deliberately
narrower than the generic schema date-time format; the profile can drift from
the authoritative schema, which is unchanged. Exception tracebacks may still
reference frames holding untrusted data and must be treated as sensitive.
'''
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import NoReturn

from ai_agent_scientist.evidence.json_blob import load_json_blob

__all__ = ['InvalidHandoffRequest', 'validate_handoff_request', 'load_handoff_request']


class InvalidHandoffRequest(ValueError):
    '''Fixed, payload-free rejection of an untrusted handoff request.'''


_MSG = 'invalid handoff request'
_TOP = frozenset((
    'schema_version', 'synthetic', 'message_id', 'request_id', 'attempt_id',
    'replicate_id', 'project_id', 'sender', 'recipient', 'kind', 'in_reply_to',
    'expected_revision', 'authorization_ref', 'budget_reservation_ref',
    'payload', 'created_at', 'expires_at'))
_PAYLOAD = frozenset(('id', 'sha256', 'media_type', 'classification'))
_ROLES = ('scientist', 'ctf', 'sleep', 'evaluator')
_CLASSES = ('synthetic', 'private', 'reviewed_export')
_DIGEST = re.compile('[a-f0-9]{64}')
_TS = re.compile('([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})(?:[.]([0-9]{1,6}))?Z')


def _bad() -> NoReturn:
    raise InvalidHandoffRequest(_MSG) from None


def _s(v: object) -> str:
    if type(v) is not str or not v:
        _bad()
    return v


def _enum(v: object, allowed: tuple) -> str:
    # Exact-type guard first: never run untrusted __eq__ via membership.
    if type(v) is not str or v not in allowed:
        _bad()
    return v


def _ts(v: object) -> datetime:
    m = _TS.fullmatch(v) if type(v) is str else None
    if m is None:
        _bad()
    y, mo, d, h, mi, s, f = m.groups()
    try:
        return datetime(int(y), int(mo), int(d), int(h), int(mi), int(s),
                        int((f or '').ljust(6, '0')), tzinfo=timezone.utc)
    except ValueError:
        _bad()


def _exact_dict(v: object, keys: frozenset) -> dict:
    if type(v) is not dict or any(type(k) is not str for k in v) or set(v) != keys:
        _bad()
    return v


def validate_handoff_request(value: object, *, now: datetime) -> dict:
    '''Return a detached ordinary-dict copy of a structurally valid request.'''
    if type(now) is not datetime or now.tzinfo is not timezone.utc:
        raise TypeError('now must be a UTC-aware datetime')
    v = _exact_dict(value, _TOP)
    sv = v['schema_version']
    if type(sv) is not str or sv != 'harness-handoff/1':
        _bad()
    if type(v['synthetic']) is not bool:
        _bad()
    if _enum(v['kind'], ('request', 'status', 'result', 'cancel')) != 'request':
        _bad()
    if v['attempt_id'] is not None or v['in_reply_to'] is not None:
        _bad()
    rep = v['replicate_id']
    if rep is not None:
        _s(rep)
    rev = v['expected_revision']
    if type(rev) is not int or rev < 0:
        _bad()
    p = _exact_dict(v['payload'], _PAYLOAD)
    if type(p['sha256']) is not str or _DIGEST.fullmatch(p['sha256']) is None:
        _bad()
    _enum(p['classification'], _CLASSES)
    created = _ts(v['created_at'])
    expires = _ts(v['expires_at'])
    if not (created < expires and created <= now < expires):
        _bad()
    return {
        'schema_version': 'harness-handoff/1',
        'synthetic': v['synthetic'],
        'message_id': _s(v['message_id']),
        'request_id': _s(v['request_id']),
        'attempt_id': None,
        'replicate_id': rep,
        'project_id': _s(v['project_id']),
        'sender': _enum(v['sender'], _ROLES),
        'recipient': _enum(v['recipient'], _ROLES),
        'kind': 'request',
        'in_reply_to': None,
        'expected_revision': rev,
        'authorization_ref': _s(v['authorization_ref']),
        'budget_reservation_ref': _s(v['budget_reservation_ref']),
        'payload': {
            'id': _s(p['id']),
            'sha256': p['sha256'],
            'media_type': _s(p['media_type']),
            'classification': p['classification'],
        },
        'created_at': v['created_at'],
        'expires_at': v['expires_at'],
    }


def load_handoff_request(store: object, sha256: str, *, now: datetime) -> dict:
    '''Load a verified strict-JSON blob once, then validate it as a request.

    Storage and strict-JSON errors propagate unchanged (fail closed, evidence
    preserved); validation is not reached when loading fails.
    '''
    return validate_handoff_request(load_json_blob(store, sha256), now=now)
