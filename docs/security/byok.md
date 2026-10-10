# Bring your own key

<p>
  <a href="../README.md#security"><img alt="docs: Security" src="https://img.shields.io/badge/docs-Security-6E40C9?logo=readthedocs&logoColor=white"></a>
  <img alt="platform keys: none" src="https://img.shields.io/badge/platform%20keys-none-3fcf8e">
  <img alt="SerpApi: 54 engines" src="https://img.shields.io/badge/SerpApi-54%20engines-2F6BFF">
  <img alt="Groq: BYOK" src="https://img.shields.io/badge/Groq-BYOK-F55036">
  <a href="../../backend/app/services/credentials/providers.py"><img alt="source: credentials/providers.py" src="https://img.shields.io/badge/source-credentials%2Fproviders.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 5 min" src="https://img.shields.io/badge/read-5%20min-555555">
</p>

[Docs](../README.md) › [Security](../README.md#security) › **Bring your own key** · page 26 of 50

> **SerpFlow is the control plane. The upstream accounts are yours.**

- **Every upstream call** SerpFlow makes for you is authenticated with a key **your organization supplied**
- That key is **stored encrypted**, and used for nothing else
- **The deployment holds no key** your work could quietly fall back to
- This is not a policy applied at the edges. It is what the code does, and the sections below say exactly where

**On this page:** [what you bring](#what-you-bring) · [without each key](#what-happens-without-each-key) · [where keys live](#where-the-keys-live) · [how a key is chosen](#how-a-key-is-chosen-for-a-request) · [self-hosting exception](#the-self-hosting-exception) · [adding a key](#adding-a-key)

## What you bring

| Service | What it does in SerpFlow | Required | Where to get one |
|---|---|---|---|
| **SerpApi** | Runs the searches. Every credit SerpFlow reports as spent is spent on your account | Yes, to execute live | [serpapi.com/manage-api-key](https://serpapi.com/manage-api-key) |
| **Groq** | Chooses which engines answer an intent (stage B of planning) | No | [console.groq.com/keys](https://console.groq.com/keys) |

- **Both are stored the same way**, through the same vault, with the same guarantees
- **Adding a third provider** means one entry in [`providers.py`](../../backend/app/services/credentials/providers.py)
  - no new table, no schema change
  - no frontend change: the console builds its credential screen from `GET /v1/credentials/providers`

## What happens without each key

**Neither key is required to use SerpFlow, and neither absence is a crash.**

- **No SerpApi key**
  - live execution returns `NO_UPSTREAM_CREDENTIAL` **before anything is spent**, instead of failing halfway through a run
  - planning, replay and any `test` API key keep working, and cost nothing
- **No Groq key**
  - planning uses the **deterministic selector**
  - not "degraded" in the sense of worse data: it is a real lexical and capability scoring pass over the retrieved shortlist
  - same plan for the same intent, every time
  - it produced the published benchmark numbers
  - it costs nothing and makes no network call
- **Which one answered is recorded in plan provenance**
  - a plan always states whether a model or the deterministic rules chose its engines
  - read it from the plan; do not infer it from configuration

## Where the keys live

One envelope per credential:

```
   your key ──► AES-256-GCM ──► ciphertext
                    ▲
                   DEK (random, per credential)
                    │
                 wrapped by KEK (CREDENTIAL_KEK)
```

- **Stored columns:** `ciphertext`, `encrypted_dek`, `kek_id`, `algo`, `fingerprint`
- **There is no column holding a recoverable plaintext key**
- **The stronger guarantee is structural:** no Pydantic response model in `app/schemas` has a field that could carry the secret
  - not excluded: **absent**. An excluded field leaks through serialisation bugs; a field that does not exist cannot
  - `app/schemas/identity.py` says so at the top of the module, and a test asserts it
- **What you can read back:** the fingerprint (`sha256(key)[:8]`, non-reversible) and the validation status. Nothing else, by anyone, including the organization owner
- Rotation, grace windows and the re-wrap procedure when `CREDENTIAL_KEK` changes: [credentials](credentials.md)

## How a key is chosen for a request

**SerpApi** resolves through the pointers that have existed since the first migration:

1. `project.credential_id`: this project's own key
2. `org.default_credential_id`: the organization default
3. refuse with `NO_UPSTREAM_CREDENTIAL`

**Every other provider** resolves by searching the organization's credentials for that provider, project-scoped rows first, then newest:

1. a credential for that provider, scoped to this project
2. a credential for that provider, scoped to the whole organization
3. that provider's documented absent behaviour: **never an error** for an optional provider

**The two differ deliberately:**

- `project.credential_id` and `org.default_credential_id` are **SerpApi's** pointers
- repurposing them would let an organization nominate only one default across every service it uses
- a project's upstream credential is validated **as a SerpApi key** for the same reason: pointing it at a Groq key would leave the project with no SerpApi credential while looking configured

**Decryption happens at the point of use**, and the plaintext lives for one request:

- for SerpApi: `ExecutorService`
- for Groq: `resolve_llm`, which hands the key straight to the adapter
- neither writes it to a column, a log sink or a response

## The self-hosting exception

Two environment variables remain, and they are the **only** place a key not belonging to an organization can enter the system:

```bash
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
```

- **Consulted only when the organization has brought no Groq key of its own**
- They exist so one person running SerpFlow for themselves need not attach a credential to every organization they create

> **If other people will use your instance, leave both unset.** Otherwise your
> key answers for every organization that has not supplied one, and those
> organizations cannot tell from the interface that this is happening.

- **There is no SerpApi equivalent, deliberately**
  - a `SERPAPI_API_KEY` setting once existed, was read by nothing, and was removed
  - a dead variable that reads as though the platform might spend its own credits is worse than no variable at all
  - a leftover `SERPAPI_API_KEY` line in an old `.env` is simply ignored

## Adding a key

**In the console:** Settings → Credentials.

- each provider gets its own card: what the key is for, what happens without it, and where to get one
- **keys are validated on arrival** with one cheap call that spends nothing: the account endpoint for SerpApi, the model list for Groq

**Over the API:**

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

- `provider` defaults to `serpapi`
- **Requires `credential:write`**, which the owner and admin roles carry

**To see what this organization still needs to bring:**

```bash
curl https://your-instance/v1/credentials/providers \
  -H "Authorization: Bearer $SERPFLOW_API_KEY"
```

- Each entry reports `required`, `configured`, and the `absent_behaviour` that applies until it is

## Related

- [Upstream credentials](credentials.md)
- [Secrets](secrets.md)
- [API keys](api-keys.md)
- [Threat model](threat-model.md)
- [Execution modes](../product/execution-modes.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Threat model](../security/threat-model.md) | [Docs index](../README.md) | [Upstream credentials](../security/credentials.md) |
