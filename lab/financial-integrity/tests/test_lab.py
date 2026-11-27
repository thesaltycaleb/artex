import sqlite3
import tempfile
import unittest
from pathlib import Path

import app


class FinancialIntegrityLabTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "test.sqlite3"
        app.initialize(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_seed_contains_only_synthetic_fixture_ids(self):
        with app.connect(self.db) as db:
            ids = [r[0] for r in db.execute("SELECT id FROM accounts ORDER BY id")]
        self.assertEqual(ids, ["TEST-ACCT-001", "TEST-ACCT-002"])

    def test_payment_posts_balanced_journal_and_reduces_principal(self):
        result = app.post_payment(self.db, "TEST-ACCT-001", 10000, "case-001")
        self.assertFalse(result["duplicate"])
        with app.connect(self.db) as db:
            principal = db.execute(
                "SELECT principal_cents FROM loans WHERE id='TEST-LOAN-001'"
            ).fetchone()[0]
            totals = db.execute(
                "SELECT SUM(debit_cents), SUM(credit_cents) FROM journal_lines"
            ).fetchone()
        self.assertEqual(principal, 40000)
        self.assertEqual(totals[0], totals[1])
        self.assertEqual(totals[0], 10000)

    def test_idempotent_retry_has_one_financial_effect(self):
        first = app.post_payment(self.db, "TEST-ACCT-001", 5000, "retry-001")
        second = app.post_payment(self.db, "TEST-ACCT-001", 5000, "retry-001")
        self.assertFalse(first["duplicate"])
        self.assertTrue(second["duplicate"])
        with app.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM payments").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM journal_entries").fetchone()[0], 1)

    def test_idempotency_key_cannot_be_reused_for_different_payment(self):
        app.post_payment(self.db, "TEST-ACCT-001", 5000, "retry-002")
        with self.assertRaisesRegex(ValueError, "different payment details"):
            app.post_payment(self.db, "TEST-ACCT-001", 6000, "retry-002")

    def test_non_synthetic_account_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "synthetic lab accounts"):
            app.post_payment(self.db, "REAL-ACCOUNT-123", 100, "case-003")

    def test_overpayment_is_rejected_without_partial_write(self):
        with self.assertRaisesRegex(ValueError, "exceeds outstanding"):
            app.post_payment(self.db, "TEST-ACCT-001", 50001, "case-004")
        with app.connect(self.db) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM payments").fetchone()[0], 0)
            self.assertEqual(
                db.execute("SELECT principal_cents FROM loans WHERE id='TEST-LOAN-001'").fetchone()[0],
                50000,
            )

    def test_audit_events_reject_update_and_delete(self):
        with app.connect(self.db) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE audit_events SET detail='tampered' WHERE id=1")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("DELETE FROM audit_events WHERE id=1")

    def test_payment_creates_audit_event(self):
        app.post_payment(self.db, "TEST-ACCT-001", 2500, "case-005")
        with app.connect(self.db) as db:
            event = db.execute(
                "SELECT event_type, entity_id FROM audit_events WHERE event_type='payment.posted'"
            ).fetchone()
        self.assertEqual(event["event_type"], "payment.posted")
        self.assertTrue(event["entity_id"].startswith("TEST-PAY-"))


if __name__ == "__main__":
    unittest.main()
