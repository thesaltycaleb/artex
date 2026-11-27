---
name: financial-integrity-lab
description: Authorized, non-destructive assessment of financial-record integrity controls in an isolated lab using synthetic accounts, loans, payments, and ledger entries. Use for transaction consistency, database authorization, audit evidence, and backup/recovery validation.
---

# Financial Integrity Lab

## Purpose and operating boundary

Use this skill only for an isolated environment owned by the operator or explicitly authorized for testing. The default test data must be synthetic. This playbook validates defensive controls; it is not a procedure for changing real customer records or bypassing financial controls.

Before any test:

1. Confirm the exact lab application, database, and network scope with the operator.
2. Confirm the target is a disposable local/test instance (for example, a dedicated Docker network and test database). Do not infer authorization from a hostname, a repository, or access to a system.
3. Use synthetic customers, accounts, loan agreements, payments, and ledger entries only. Never import production data, credentials, tokens, or personal information.
4. Prefer read-only inspection. Any test requiring writes must use disposable fixtures and an isolated test database, with explicit operator approval and a documented reset path.
5. Do not disable scope checks, approval gates, logging, backups, authentication, or egress restrictions. Do not attempt persistence, exfiltration, destructive changes, or access to external financial institutions.
6. If the target or authorization is ambiguous, stop and ask the operator.

## Suggested synthetic model

Use a small fixture set with clearly fictional identifiers, for example:

- Customers: `TEST-CUST-001`, `TEST-CUST-002`
- Accounts: `TEST-ACCT-001`, `TEST-ACCT-002`
- Loans: `TEST-LOAN-001`, `TEST-LOAN-002`
- Payments and ledger entries linked only to those test records

Represent money as integer minor units (such as cents) or an exact decimal type, never binary floating point. Keep currency explicit. Give each loan a stable identifier and version. Preserve the original agreement terms and record subsequent changes as separately authorized, attributable events rather than silently overwriting history.

## Assessment workflow

### 1. Establish a baseline

Record the test environment identifier, application version/commit, database engine/version, schema version, fixture identifiers, time window, and the operator-approved scope. Capture a baseline export or deterministic summary of the synthetic records. Redact secrets from all evidence.

### 2. Transaction and ledger consistency

Use read-only queries or application-provided reports to verify:

- Every posted payment has exactly one corresponding, correctly linked ledger effect under the application's documented accounting model.
- Debits and credits balance for each posted journal transaction.
- Account balances reconcile to the sum of posted ledger entries, accounting for documented opening balances and reversals.
- Pending, failed, voided, and reversed transactions are not counted as posted.
- Currency, sign, precision, and rounding rules are consistent.
- Duplicate idempotency keys do not create duplicate postings.
- A retry after a simulated timeout does not create a second financial effect.
- Concurrent test transactions preserve invariants and do not produce lost updates.

Do not invent accounting rules. Obtain the application's documented posting model and report any assumptions.

### 3. Authorization and separation of duties

Inspect database grants and application authorization configuration without attempting to evade them. Verify that:

- The application runtime role has only the privileges it needs.
- Read-only/reporting roles cannot write financial tables.
- Migration/administrative roles are not used by normal application requests.
- A user cannot approve their own high-risk change where dual control is required by the documented policy.
- Tenant/customer ownership checks are enforced server-side, not only in the UI.
- Access denials are logged without exposing secrets or sensitive record contents.

Report excessive grants and missing controls; do not use them to modify records.

### 4. Loan-term and account-change history

For synthetic records, verify that changes to principal, rate, maturity, payment schedule, status, or ownership:

- Have an authenticated actor and timestamp.
- Include a reason or change ticket reference where policy requires it.
- Preserve prior values or an immutable version reference.
- Record approval evidence and the effective date.
- Can be reconciled to the current state.

Use only approved application workflows in a disposable test database to create sample changes. Do not directly rewrite balances or loan obligations.

### 5. Audit-log integrity

Check whether audit events are append-only to the application role, whether event identifiers and timestamps are present, and whether sensitive fields are appropriately redacted. Where the lab implements hash chaining or signed checkpoints, independently recompute and compare the chain/checkpoint using the documented format.

A passing result means the tested evidence is internally consistent; it does not prove that a privileged administrator could never alter it. Identify trust assumptions, privileged actors, external log sinks, and retention gaps explicitly.

### 6. Backup and recovery validation

Use a disposable database and an operator-approved backup. Verify:

- Backup completion and non-zero, plausible output.
- Checksum or signature verification where configured.
- Encryption and key availability without printing or exporting key material.
- Restore into a separate isolated database, never over the source.
- Restored record counts, schema version, and synthetic ledger totals match the baseline.
- The documented recovery point and recovery time objectives are measured and reported.

Never delete or overwrite the only copy of a backup or the source database.

### 7. Evidence and reporting

For every check, record:

- Control and invariant being tested.
- Exact lab scope and synthetic fixture IDs.
- Read-only query or approved test action.
- Expected and observed result.
- Evidence reference and timestamp.
- Severity, impact, confidence, and remediation.
- Any limitation or unverified assumption.

Do not include credentials, connection strings, personal data, or full financial records in evidence. Prefer aggregate values and synthetic identifiers.

## Stop conditions

Stop immediately if a test would reach a non-lab host, touch real customer data, require disabling a safety control, alter a non-disposable database, erase or conceal audit evidence, or exceed the approved scope. Explain the blocker and request explicit direction rather than finding another route.

## Expected deliverable

Produce a concise control-assessment report with:

1. Scope and environment.
2. Controls checked and results (Pass / Fail / Not tested).
3. Evidence references.
4. Findings ranked by severity and confidence.
5. Concrete defensive remediation.
6. Recovery/retest steps and residual limitations.
