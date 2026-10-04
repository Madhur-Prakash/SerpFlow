# Bring your own key

SerpFlow is the control plane. The upstream accounts are yours.

Every upstream call SerpFlow makes on your behalf is authenticated with a key
**your organization supplied**, stored encrypted, and used for nothing else. The
deployment holds no key that your work could quietly fall back to. This is not a
policy applied at the edges — it is what the code does, and the sections below
say exactly where.

- [What you bring](#what-you-bring)
- [What happens without each key](#what-happens-without-each-key)
- [Where the keys live](#where-the-keys-live)
- [How a key is chosen for a request](#how-a-key-is-chosen-for-a-request)
- [The self-hosting exception](#the-self-hosting-exception)
- [Adding a key](#adding-a-key)

## What you bring

| Service | What it does in SerpFlow | Required | Where to get one |
|---|---|---|---|
| **SerpApi** | Runs the searches. Every credit SerpFlow reports as spent is spent on your account. | Yes, to execute live | [serpapi.com/manage-api-key](https://serpapi.com/manage-api-key) |
| **Groq** | Chooses which engines answer an intent (stage B of planning). | No | [console.groq.com/keys](https://console.groq.com/keys) |

Both are stored the same way, through the same vault, with the same
guarantees. Adding a third provider means adding one entry to
[`providers.py`](../../backend/app/services/credentials/providers.py) — no new
table, no schema change, and no frontend change, because the console builds its
credential screen from `GET /v1/credentials/providers`.

## What happens without each key

Neither key is required to *use* SerpFlow, and neither failure mode is a crash.

**No SerpApi key.** Live execution returns `NO_UPSTREAM_CREDENTIAL` before
anything is spent, rather than failing halfway through a run. Planning, replay,
and any `test` API key keep working and cost nothing.

**No Groq key.** Planning uses the deterministic selector. This is not a
degraded mode in the sense of returning worse data — it is a real lexical and
capability scoring pass over the retrieved shortlist, it returns the same plan
for the same intent every time, and it is what the published benchmark numbers
were produced with. It costs nothing and makes no network call.

Which one answered is recorded in plan provenance, so a plan always states
whether a model chose its engines or the deterministic rules did. Do not infer
it from configuration — read it from the plan.

## Where the keys live

One envelope per credential:

```
   your key ──► AES-256-GCM ──► ciphertext
                    ▲
                   DEK (random, per credential)
                    │
                 wrapped by KEK (CREDENTIAL_KEK)
```

Stored columns are `ciphertext`, `encrypted_dek`, `kek_id`, `algo` and
`fingerprint`. There is no column holding a recoverable plaintext key.

The stronger guarantee is structural rather than procedural: **no Pydantic
response model in `app/schemas` has a field that could carry the secret.** Not
excluded — absent. An excluded field leaks through serialisation bugs; a field
that does not exist cannot. `app/schemas/identity.py` says so at the top of the
module, and a test asserts it.

What you can read back is the fingerprint — `sha256(key)[:8]`, non-reversible —
and the validation status. Nothing else, by anyone, including the organization
owner.

See [credentials.md](credentials.md) for rotation, grace windows and the
re-wrap procedure when `CREDENTIAL_KEK` changes.

## How a key is chosen for a request

**SerpApi** resolves through the pointers that have existed since the first
migration:

1. `project.credential_id` — this project's own key
2. `org.default_credential_id` — the organization default
3. refuse with `NO_UPSTREAM_CREDENTIAL`

**Every other provider** resolves by searching the organization's credentials
for that provider, project-scoped rows first, then newest:

1. a credential for that provider scoped to this project
2. a credential for that provider scoped to the whole organization
3. that provider's documented absent behaviour — never an error for an
   optional provider

The two differ deliberately. `project.credential_id` and
`org.default_credential_id` are *SerpApi's* pointers; repurposing them would
let an organization nominate only one default across every service it uses. A
project's upstream credential is validated as a SerpApi key for the same
reason — pointing it at a Groq key would leave the project with no SerpApi
credential while appearing configured.

Decryption happens at the point of use and the plaintext is held for the
lifetime of one request. For SerpApi that is `ExecutorService`; for Groq it is
`resolve_llm`, which hands the key straight to the adapter. Neither writes it
to a column, a log sink or a response.

## The self-hosting exception

Two environment variables remain, and they are the only place a key not
belonging to an organization can enter the system:

```bash
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
```

They are consulted **only when the organization has brought no Groq key of its
own.** They exist so that one person running SerpFlow for themselves does not
have to attach a credential to every organization they create.

> **If other people will use your instance, leave both unset.** Setting them
> means your key answers for every organization that has not supplied one, and
> those organizations have no way to tell from the interface that this is
> happening.

There is no SerpApi equivalent, and deliberately so. A `SERPAPI_API_KEY`
setting existed, was read by nothing, and was removed — a dead variable that
reads as though the platform might spend its own credits is worse than no
variable at all.

## Adding a key

**In the console.** Settings → Credentials. Each provider gets its own card
stating what the key is for, what happens without it, and where to get one.
Keys are validated on arrival with one cheap call that spends nothing — for
SerpApi the account endpoint, for Groq the model list.

**Over the API.**

```bash
curl -X POST https://your-instance/v1/credentials \
  -H "Authorization: Bearer $SERPFLOW_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
        "name": "My Groq account",
        "provider": "groq",
        "api_key": "gsk_...",
        "validate_now": true
      }'
```

`provider` defaults to `serpapi`. Requires `credential:write`, which the owner
and admin roles carry.

To see what this organization still needs to bring:

```bash
curl https://your-instance/v1/credentials/providers \
  -H "Authorization: Bearer $SERPFLOW_API_KEY"
```

Each entry reports `required`, `configured`, and the `absent_behaviour` that
applies while it is not.

---

**Related:** [credentials.md](credentials.md) · [secrets.md](secrets.md) ·
[api-keys.md](api-keys.md) · [threat-model.md](threat-model.md) ·
[execution modes](../product/execution-modes.md)
