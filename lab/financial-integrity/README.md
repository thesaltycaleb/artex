# Financial Integrity Lab (synthetic/local only)

A deliberately small companion service for ARTEX skill development. It uses Python's standard
library and SQLite; it does not connect to external systems, contain real customer data, or expose
a network listener beyond loopback.

## Safety properties

- Binds to `127.0.0.1:8765` only (the bind address is fixed in source).
- Uses clearly synthetic customer, account, and loan IDs.
- Exposes read-only account, loan, ledger, and audit views.
- The only write operation is a bounded synthetic payment workflow with positive integer cents,
  an idempotency key, transaction rollback, and a balanced journal entry.
- Rejects account IDs outside the `TEST-ACCT-` namespace.
- Audit rows are append-only at the SQLite schema level (update/delete triggers).
- No admin endpoint, arbitrary SQL endpoint, loan-term mutation endpoint, or external callback.
- No third-party packages or dependencies.

This is a training fixture, not a production banking implementation or a complete accounting
system. SQLite triggers protect against ordinary application-level edits, not a privileged operator
who can replace the database file or schema.

## Run

From this directory:

```bash
python3 app.py
```

Open `http://127.0.0.1:8765/health`. The first run creates
`financial-lab.sqlite3` with synthetic fixture data. To use a different local database file:

```bash
FINLAB_DB=/absolute/path/to/lab.sqlite3 python3 app.py
```

The server remains bound to loopback regardless of the database path.

## API

- `GET /health`
- `GET /api/accounts`
- `GET /api/loans`
- `GET /api/ledger`
- `GET /api/audit`
- `POST /api/payments` with JSON `{"account_id":"TEST-ACCT-001","amount_cents":1000}`
  and an `Idempotency-Key` header.

Example:

```bash
curl http://127.0.0.1:8765/api/accounts
curl -X POST http://127.0.0.1:8765/api/payments \
  -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: demo-payment-001' \
  -d '{"account_id":"TEST-ACCT-001","amount_cents":1000}'
curl http://127.0.0.1:8765/api/ledger
curl http://127.0.0.1:8765/api/audit
```

## Tests

No server is required. Tests use a fresh temporary database per test:

```bash
python3 -m unittest discover -s tests -v
```

The suite covers synthetic fixture IDs, balanced journal posting, idempotent retries, rejection of
non-lab account IDs, overpayment rollback, append-only audit enforcement, and audit event creation.

## Using with ARTEX

Create a dedicated ARTEX task whose scope contains only `127.0.0.1:8765`. Use the
`financial-integrity-lab` skill from the sibling `skills/` directory. Keep target approval and
tool interception enabled. Begin with GET-only inventory and reconciliation; approve the single
synthetic payment test only when needed. Do not add public, LAN, cloud, or production targets to
this lab scope.

To reset the fixture, stop the service and remove only this lab's `financial-lab.sqlite3` file.
The next start seeds a fresh synthetic database. Never point `FINLAB_DB` at ARTEX's own database.
