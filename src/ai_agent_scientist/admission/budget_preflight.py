# Pure arithmetic worker-budget preflight (see docs/17-budget-preflight.md).
#
# Internal helper only. It is NOT admission, authorization, reservation,
# ledger validation, a runner or a verification receipt. It performs no I/O,
# reads no clock or environment, and changes no state.

from dataclasses import dataclass
from typing import Optional

OUTCOME_FITS_ARITHMETIC = 'fits_arithmetic'
OUTCOME_EXCEEDS_CAP = 'exceeds_cap'
OUTCOME_INVALID_INPUT = 'invalid_input'

REASON_NOT_INTEGER = 'not_integer'
REASON_BELOW_MINIMUM = 'below_minimum'

# (field name, minimum) in the deterministic validation order P, R, S, E, T.
_FIELDS = (
    ('planned_attempts', 1),
    ('max_retries', 0),
    ('per_attempt_seconds', 1),
    ('evaluation_cleanup_seconds', 0),
    ('total_worker_seconds', 1),
)


@dataclass(frozen=True)
class BudgetPreflightResult:
    outcome: str
    required_worker_seconds: Optional[int]
    cap_worker_seconds: Optional[int]
    shortfall_worker_seconds: Optional[int]
    invalid_field: Optional[str]
    invalid_reason: Optional[str]


def _domain_reason(value, minimum):
    # Exact built-in int only: bool, subclasses, floats, strings and None are
    # rejected without any coercion.
    if type(value) is not int:
        return REASON_NOT_INTEGER
    if value < minimum:
        return REASON_BELOW_MINIMUM
    return None


def check_uniform_worker_budget(
    *,
    planned_attempts,
    max_retries,
    per_attempt_seconds,
    evaluation_cleanup_seconds,
    total_worker_seconds,
):
    # required = (P + R) * S + E ; shortfall = max(required - T, 0).
    values = (
        planned_attempts,
        max_retries,
        per_attempt_seconds,
        evaluation_cleanup_seconds,
        total_worker_seconds,
    )

    # Every field is checked against its own domain, including T even when an
    # earlier field is already invalid.
    first_field = None
    first_reason = None
    for (name, minimum), value in zip(_FIELDS, values):
        reason = _domain_reason(value, minimum)
        if reason is not None and first_field is None:
            first_field = name
            first_reason = reason

    cap_minimum = _FIELDS[4][1]
    if _domain_reason(total_worker_seconds, cap_minimum) is None:
        cap = total_worker_seconds
    else:
        cap = None

    if first_field is not None:
        return BudgetPreflightResult(
            outcome=OUTCOME_INVALID_INPUT,
            required_worker_seconds=None,
            cap_worker_seconds=cap,
            shortfall_worker_seconds=None,
            invalid_field=first_field,
            invalid_reason=first_reason,
        )

    required = (planned_attempts + max_retries) * per_attempt_seconds + evaluation_cleanup_seconds
    shortfall = max(required - total_worker_seconds, 0)
    if required <= total_worker_seconds:
        outcome = OUTCOME_FITS_ARITHMETIC
    else:
        outcome = OUTCOME_EXCEEDS_CAP
    return BudgetPreflightResult(
        outcome=outcome,
        required_worker_seconds=required,
        cap_worker_seconds=total_worker_seconds,
        shortfall_worker_seconds=shortfall,
        invalid_field=None,
        invalid_reason=None,
    )
