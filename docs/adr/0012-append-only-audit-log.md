# 0012. The audit log is append-only in the database

**Status** Accepted

## Context

An audit log that application code can rewrite is not an audit log. It is a
table of events that happens to be mostly accurate.

The adversary that matters here is not an outsider — it is a compromised
administrator, or application code with a bug, modifying history after the
fact. Both have the application's database credentials, so an application-level
rule ("we never UPDATE audit_log") is a convention, not a guarantee.

## Decision

Two mechanisms.

**A trigger makes it append-only at the database level.**

```sql
CREATE TRIGGER serpflow_audit_no_update
  BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION serpflow_audit_append_only();
```

`UPDATE` is refused unconditionally. `DELETE` is refused unless the transaction
has explicitly set `app.audit_purge`.

**A hash chain makes tampering detectable.** Each entry carries `prev_hash` and
`entry_hash`, chained per organization. `GET /v1/audit/verify` walks the chain
and reports the first break by sequence number, so removing or altering an
entry breaks every hash after it.

`entry_hash` is computed in the application before the INSERT, with an explicit
`created_at`, rather than by a trigger — a trigger that mutated the row would
have to run `BEFORE INSERT`, placing it inside the surface the chain is meant
to protect.

## The exception, and why it exists

The original trigger refused every `UPDATE` and `DELETE`. That broke two
legitimate operations: deleting an organization, which owners are entitled to
do, and `make seed --reset`. Both fail on a **cascade**, not on an explicit
delete, so neither could be special-cased in application code.

Migration `0002_audit_purge` narrows the guard:

```sql
IF TG_OP = 'DELETE'
   AND coalesce(current_setting('app.audit_purge', true), '') = 'on' THEN
    RETURN OLD;
END IF;
RAISE EXCEPTION 'audit_log is append-only; % is not permitted', TG_OP;
```

`UPDATE` is still refused unconditionally. The setting is transaction-scoped
and is set in exactly one function,
[`AuditService.allow_purge`](../../backend/app/services/audit/service.py), so
the guarantee survives while the legitimate path works.

This is an honest hole, deliberately sized. Anyone with database access can set
the variable — but the hash chain makes the resulting gap visible.

## Alternatives rejected

**Application-level discipline only.** A convention, bypassable by any code
path and by anyone with the database credentials.

**Write-once external storage.** Stronger, and it puts the audit log outside
the transaction that produced the change, so a write can succeed while its
audit entry does not.

**No deletion path at all.** Then organization deletion is impossible, which
conflicts with the deletion rights the product grants. Refusing to delete
personal data on principle is not the safer option it sounds like.

## Cost

A cascade that touches `audit_log` fails unless it goes through the purge path,
which is surprising the first time and is called out in
[troubleshooting](../operations/troubleshooting.md).

Verification is O(n) over an organization's entries, so `GET /v1/audit/verify`
is an operator endpoint rather than something to poll.

And the limit, stated plainly: against an adversary with database access *and*
the ability to recompute the chain, tampering is detectable but not
preventable. That boundary is in [the threat model](../security/threat-model.md).

## See also

- [Migrations](../database/migrations.md)
- [Row-level security](../database/rls.md)
