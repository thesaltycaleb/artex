#!/usr/bin/env python3
"""Local-only synthetic financial ledger lab. Python standard library only."""

from __future__ import annotations

import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("FINLAB_DB", HERE / "financial-lab.sqlite3"))
HOST = "127.0.0.1"
PORT = 8765
MAX_BODY = 16 * 1024


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def initialize(db_path: Path = DB_PATH) -> None:
    with connect(db_path) as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS customers (
            id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY,
            customer_id TEXT NOT NULL REFERENCES customers(id),
            currency TEXT NOT NULL CHECK(length(currency) = 3),
            balance_cents INTEGER NOT NULL CHECK(balance_cents >= 0)
        );
        CREATE TABLE IF NOT EXISTS loans (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL REFERENCES accounts(id),
            principal_cents INTEGER NOT NULL CHECK(principal_cents >= 0),
            version INTEGER NOT NULL DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS payments (
            id TEXT PRIMARY KEY,
            idempotency_key TEXT NOT NULL UNIQUE,
            account_id TEXT NOT NULL REFERENCES accounts(id),
            amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS journal_entries (
            id TEXT PRIMARY KEY,
            payment_id TEXT NOT NULL UNIQUE REFERENCES payments(id),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS journal_lines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entry_id TEXT NOT NULL REFERENCES journal_entries(id),
            account_code TEXT NOT NULL,
            debit_cents INTEGER NOT NULL DEFAULT 0 CHECK(debit_cents >= 0),
            credit_cents INTEGER NOT NULL DEFAULT 0 CHECK(credit_cents >= 0),
            CHECK ((debit_cents = 0) != (credit_cents = 0))
        );
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            detail TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TRIGGER IF NOT EXISTS audit_no_update
        BEFORE UPDATE ON audit_events BEGIN
            SELECT RAISE(ABORT, 'audit events are append-only');
        END;
        CREATE TRIGGER IF NOT EXISTS audit_no_delete
        BEFORE DELETE ON audit_events BEGIN
            SELECT RAISE(ABORT, 'audit events are append-only');
        END;
        """)

        count = db.execute("SELECT COUNT(*) FROM customers").fetchone()[0]
        if count == 0:
            db.executemany(
                "INSERT INTO customers(id, display_name) VALUES (?, ?)",
                [("TEST-CUST-001", "Sample Customer One"),
                 ("TEST-CUST-002", "Sample Customer Two")],
            )
            db.executemany(
                "INSERT INTO accounts(id, customer_id, currency, balance_cents) VALUES (?, ?, 'USD', ?)",
                [("TEST-ACCT-001", "TEST-CUST-001", 50000),
                 ("TEST-ACCT-002", "TEST-CUST-002", 125000)],
            )
            db.executemany(
                "INSERT INTO loans(id, account_id, principal_cents) VALUES (?, ?, ?)",
                [("TEST-LOAN-001", "TEST-ACCT-001", 50000),
                 ("TEST-LOAN-002", "TEST-ACCT-002", 125000)],
            )
            db.execute(
                "INSERT INTO audit_events(event_type, entity_id, detail) VALUES (?, ?, ?)",
                ("lab.seed", "TEST-ACCT-001,TEST-ACCT-002", "Synthetic fixture set initialized"),
            )


def rows(db: sqlite3.Connection, query: str, params: tuple = ()) -> list[dict]:
    return [dict(row) for row in db.execute(query, params).fetchall()]


def post_payment(db_path: Path, account_id: str, amount_cents: int, idempotency_key: str) -> dict:
    if not isinstance(account_id, str) or not account_id.startswith("TEST-ACCT-"):
        raise ValueError("only synthetic lab accounts are accepted")
    if not isinstance(amount_cents, int) or isinstance(amount_cents, bool) or amount_cents <= 0:
        raise ValueError("amount_cents must be a positive integer")
    if not isinstance(idempotency_key, str) or not (1 <= len(idempotency_key) <= 100):
        raise ValueError("a 1-100 character Idempotency-Key is required")

    with connect(db_path) as db:
        existing = db.execute(
            "SELECT id, account_id, amount_cents FROM payments WHERE idempotency_key = ?",
            (idempotency_key,),
        ).fetchone()
        if existing:
            if existing["account_id"] != account_id or existing["amount_cents"] != amount_cents:
                raise ValueError("idempotency key was already used with different payment details")
            return {"payment_id": existing["id"], "duplicate": True}

        loan = db.execute(
            "SELECT l.id, l.principal_cents FROM loans l JOIN accounts a ON a.id = l.account_id "
            "WHERE l.account_id = ?",
            (account_id,),
        ).fetchone()
        if not loan:
            raise ValueError("synthetic account not found")
        if amount_cents > loan["principal_cents"]:
            raise ValueError("payment exceeds outstanding synthetic principal")

        payment_id = "TEST-PAY-" + idempotency_key.replace("-", "")[:24]
        entry_id = "TEST-JE-" + idempotency_key.replace("-", "")[:24]
        db.execute(
            "INSERT INTO payments(id, idempotency_key, account_id, amount_cents) VALUES (?, ?, ?, ?)",
            (payment_id, idempotency_key, account_id, amount_cents),
        )
        db.execute(
            "UPDATE loans SET principal_cents = principal_cents - ?, version = version + 1 WHERE id = ?",
            (amount_cents, loan["id"]),
        )
        db.execute("INSERT INTO journal_entries(id, payment_id) VALUES (?, ?)", (entry_id, payment_id))
        db.executemany(
            "INSERT INTO journal_lines(entry_id, account_code, debit_cents, credit_cents) VALUES (?, ?, ?, ?)",
            [(entry_id, "CASH_CLEARING", amount_cents, 0),
             (entry_id, "LOAN_RECEIVABLE", 0, amount_cents)],
        )
        db.execute(
            "INSERT INTO audit_events(event_type, entity_id, detail) VALUES (?, ?, ?)",
            ("payment.posted", payment_id, json.dumps({
                "account_id": account_id, "amount_cents": amount_cents,
                "journal_entry_id": entry_id,
            }, sort_keys=True)),
        )
        return {"payment_id": payment_id, "duplicate": False}


class Handler(BaseHTTPRequestHandler):
    server_version = "FinancialIntegrityLab/1.0"

    def _json(self, status: int, payload: dict | list) -> None:
        body = json.dumps(payload, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        initialize()
        with connect() as db:
            if path == "/health":
                return self._json(200, {"status": "ok", "mode": "synthetic-local-lab"})
            if path == "/api/accounts":
                return self._json(200, rows(db, "SELECT id, customer_id, currency, balance_cents FROM accounts ORDER BY id"))
            if path == "/api/loans":
                return self._json(200, rows(db, "SELECT id, account_id, principal_cents, version FROM loans ORDER BY id"))
            if path == "/api/ledger":
                return self._json(200, rows(db, """
                    SELECT e.id AS entry_id, e.payment_id, l.account_code, l.debit_cents, l.credit_cents
                    FROM journal_entries e JOIN journal_lines l ON l.entry_id = e.id
                    ORDER BY e.created_at, l.id
                """))
            if path == "/api/audit":
                return self._json(200, rows(db, "SELECT id, event_type, entity_id, detail, created_at FROM audit_events ORDER BY id"))
        return self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if urlparse(self.path).path != "/api/payments":
            return self._json(404, {"error": "not found"})
        raw_length = self.headers.get("Content-Length", "")
        if not raw_length.isdigit() or int(raw_length) > MAX_BODY:
            return self._json(413, {"error": "invalid or oversized request body"})
        try:
            payload = json.loads(self.rfile.read(int(raw_length)))
            if not isinstance(payload, dict):
                raise ValueError("JSON object required")
            initialize()
            result = post_payment(
                DB_PATH,
                payload.get("account_id"),
                payload.get("amount_cents"),
                self.headers.get("Idempotency-Key", ""),
            )
            return self._json(200, result)
        except (ValueError, TypeError, json.JSONDecodeError, sqlite3.IntegrityError) as exc:
            return self._json(400, {"error": str(exc)})

    def log_message(self, fmt: str, *args) -> None:
        print("lab-http:", fmt % args)


def main() -> None:
    initialize()
    print(f"Financial Integrity Lab listening at http://{HOST}:{PORT}")
    print(f"Synthetic database: {DB_PATH}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
