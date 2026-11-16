# Ten fixed vectors B01-B10 for the pure budget preflight (docs/17-budget-preflight.md).
# Run: PYTHONPATH=src python3 -m unittest discover -s tests/contracts -p test_budget_preflight.py -v

import unittest

from ai_agent_scientist.admission.budget_preflight import (
    BudgetPreflightResult,
    check_uniform_worker_budget,
)


class BudgetPreflightContract(unittest.TestCase):
    def assert_result(self, result, outcome, required, cap, shortfall, field, reason):
        self.assertIsInstance(result, BudgetPreflightResult)
        self.assertEqual(result.outcome, outcome)
        self.assertEqual(result.required_worker_seconds, required)
        self.assertEqual(result.cap_worker_seconds, cap)
        self.assertEqual(result.shortfall_worker_seconds, shortfall)
        self.assertEqual(result.invalid_field, field)
        self.assertEqual(result.invalid_reason, reason)

    def test_b01_sci05_arithmetic(self):
        result = check_uniform_worker_budget(
            planned_attempts=72,
            max_retries=0,
            per_attempt_seconds=600,
            evaluation_cleanup_seconds=0,
            total_worker_seconds=1800,
        )
        self.assert_result(result, 'exceeds_cap', 43200, 1800, 41400, None, None)
        # Structural immutability check only; no additional helper call.
        self.assertTrue(BudgetPreflightResult.__dataclass_params__.frozen)

    def test_b02_exact_boundary(self):
        result = check_uniform_worker_budget(
            planned_attempts=2,
            max_retries=0,
            per_attempt_seconds=600,
            evaluation_cleanup_seconds=600,
            total_worker_seconds=1800,
        )
        self.assert_result(result, 'fits_arithmetic', 1800, 1800, 0, None, None)

    def test_b03_global_retry_allowance(self):
        result = check_uniform_worker_budget(
            planned_attempts=2,
            max_retries=1,
            per_attempt_seconds=400,
            evaluation_cleanup_seconds=100,
            total_worker_seconds=1300,
        )
        self.assert_result(result, 'fits_arithmetic', 1300, 1300, 0, None, None)

    def test_b04_cleanup_one_too_much(self):
        result = check_uniform_worker_budget(
            planned_attempts=2,
            max_retries=1,
            per_attempt_seconds=400,
            evaluation_cleanup_seconds=101,
            total_worker_seconds=1300,
        )
        self.assert_result(result, 'exceeds_cap', 1301, 1300, 1, None, None)

    def test_b05_retry_changes_decision(self):
        result = check_uniform_worker_budget(
            planned_attempts=2,
            max_retries=1,
            per_attempt_seconds=600,
            evaluation_cleanup_seconds=0,
            total_worker_seconds=1200,
        )
        self.assert_result(result, 'exceeds_cap', 1800, 1200, 600, None, None)

    def test_b06_no_attempts(self):
        result = check_uniform_worker_budget(
            planned_attempts=0,
            max_retries=0,
            per_attempt_seconds=1,
            evaluation_cleanup_seconds=0,
            total_worker_seconds=1,
        )
        self.assert_result(
            result, 'invalid_input', None, 1, None, 'planned_attempts', 'below_minimum'
        )

    def test_b07_bool_is_not_integer(self):
        result = check_uniform_worker_budget(
            planned_attempts=True,
            max_retries=0,
            per_attempt_seconds=1,
            evaluation_cleanup_seconds=0,
            total_worker_seconds=1,
        )
        self.assert_result(
            result, 'invalid_input', None, 1, None, 'planned_attempts', 'not_integer'
        )

    def test_b08_unknown_cost(self):
        result = check_uniform_worker_budget(
            planned_attempts=1,
            max_retries=0,
            per_attempt_seconds=1,
            evaluation_cleanup_seconds=None,
            total_worker_seconds=10,
        )
        self.assert_result(
            result, 'invalid_input', None, 10, None, 'evaluation_cleanup_seconds', 'not_integer'
        )

    def test_b09_no_coercion(self):
        result = check_uniform_worker_budget(
            planned_attempts=1,
            max_retries=0,
            per_attempt_seconds=1.5,
            evaluation_cleanup_seconds=0,
            total_worker_seconds=10,
        )
        self.assert_result(
            result, 'invalid_input', None, 10, None, 'per_attempt_seconds', 'not_integer'
        )

    def test_b10_exact_large_integer(self):
        result = check_uniform_worker_budget(
            planned_attempts=9007199254740993,
            max_retries=0,
            per_attempt_seconds=1,
            evaluation_cleanup_seconds=0,
            total_worker_seconds=9007199254740992,
        )
        self.assert_result(
            result,
            'exceeds_cap',
            9007199254740993,
            9007199254740992,
            1,
            None,
            None,
        )


if __name__ == '__main__':
    unittest.main()
