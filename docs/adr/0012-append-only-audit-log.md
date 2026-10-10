# 0012. The audit log is append-only in the database

<p>
  <a href="../README.md#decisions"><img alt="docs: Decisions" src="https://img.shields.io/badge/docs-Decisions-555555?logo=readthedocs&logoColor=white"></a>
  <img alt="status: accepted" src="https://img.shields.io/badge/status-accepted-3fcf8e">
  <a href="../../backend/app/services/audit/service.py"><img alt="source: audit/service.py" src="https://img.shields.io/badge/source-audit%2Fservice.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 3 min" src="https://img.shields.io/badge/read-3%20min-555555">
</p>

[Docs](../README.md) › [Decisions](../README.md#decisions) › **0012. The audit log is append-only in the database** · page 48 of 50

**Status** Accepted

## Context

- **An audit log that application code can rewrite is not an audit log.** It is a table of events that happens to be mostly accurate
- **The adversary that matters is not an outsider:** it is a compromised administrator, or application code with a bug, modifying history after the fact
- **Both have the application's database credentials**, so an application-level rule ("we never UPDATE audit_log") is a convention, not a guarantee

## Decision

**Two mechanisms.**

### 1. A trigger makes it append-only at the database level

```sql
CREATE TRIGGER serpflow_audit_no_update
  BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION serpflow_audit_append_only();
```

- **`UPDATE` is refused unconditionally**
- **`DELETE` is refused** unless the transaction explicitly set `app.audit_purge`

### 2. A hash chain makes tampering detectable

- **Each entry carries `prev_hash` and `entry_hash`**, chained per organization
- **`GET /v1/audit/verify`** walks the chain and reports the first break by sequence number
  - removing or altering an entry breaks every hash after it
- **`entry_hash` is computed in the application** before the INSERT, with an explicit `created_at`, not by a trigger
  - a trigger that mutated the row would have to run `BEFORE INSERT`, placing it inside the very surface the chain protects

## The exception, and why it exists

- **The original trigger refused every `UPDATE` and `DELETE`**, which broke two legitimate operations:
  - deleting an organization, which owners are entitled to do
  - `make seed --reset`
- **Both fail on a cascade**, not an explicit delete, so neither could be special-cased in application code
- **Migration `0002_audit_purge` narrows the guard:**

```sql
IF TG_OP = 'DELETE'
   AND coalesce(current_setting('app.audit_purge', true), '') = 'on' THEN
    RETURN OLD;
END IF;
RAISE EXCEPTION 'audit_log is append-only; % is not permitted', TG_OP;
```

- **`UPDATE` is still refused unconditionally**
- **The setting is transaction-scoped**, and set in exactly one function: [`AuditService.allow_purge`](../../backend/app/services/audit/service.py)
- So the guarantee survives, and the legitimate path works
- **An honest hole, deliberately sized:** anyone with database access can set the variable, but the hash chain makes the resulting gap **visible**

## Alternatives rejected

| Alternative | Why it lost |
| --- | --- |
| **Application-level discipline only** | A convention, bypassable by any code path and by anyone with the database credentials |
| **Write-once external storage** | Stronger, but puts the audit log outside the transaction that produced the change, so a write can succeed while its audit entry does not |
| **No deletion path at all** | Makes organization deletion impossible, conflicting with the deletion rights the product grants. Refusing to delete personal data on principle is not as safe as it sounds |

## Cost

- **A cascade that touches `audit_log` fails** unless it goes through the purge path: surprising the first time, and called out in [troubleshooting](../operations/troubleshooting.md#audit_log-is-append-only-delete-is-not-permitted)
- **Verification is O(n)** over an organization's entries, so `GET /v1/audit/verify` is an **operator** endpoint, not something to poll
- **The limit, stated plainly:** against an adversary with database access **and** the ability to recompute the chain, tampering is detectable but not preventable. That boundary is in [the threat model](../security/threat-model.md#out-of-scope)

## See also

- [Migrations](../database/migrations.md)
- [Row-level security](../database/rls.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [ADR 0011: Tenant isolation enforced twice](../adr/0011-rls-plus-application-guards.md) | [Docs index](../README.md) | [ADR 0013: Run uvicorn through an explicit loop fac…](../adr/0013-explicit-event-loop-factory.md) |
