# Bring your own key

<p>
  <a href="../security/README.md"><img alt="docs: Security" src="https://img.shields.io/badge/docs-Security-6E40C9?logo=readthedocs&logoColor=white"></a>
  <img alt="platform keys: none" src="https://img.shields.io/badge/platform%20keys-none-3fcf8e">
  <img alt="SerpApi: 54 engines" src="https://img.shields.io/badge/SerpApi-54%20engines-2F6BFF">
  <img alt="Groq: BYOK" src="https://img.shields.io/badge/Groq-BYOK-F55036">
  <a href="../../backend/app/services/credentials/providers.py"><img alt="source: credentials/providers.py" src="https://img.shields.io/badge/source-credentials%2Fproviders.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 8 min" src="https://img.shields.io/badge/read-8%20min-555555">
</p>

[Docs](../README.md) › [Security](../security/README.md) › **Bring your own key** · page 40 of 50

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
| **Groq** | Chooses which engines answer an intent ([stage B of planning](../architecture/planner.md#stage-b-select)) | No | [console.groq.com/keys](https://console.groq.com/keys) |

- **Both are stored the same way**, through the same vault, with the same guarantees ([upstream credentials](credentials.md))
- **Adding a third provider** means one entry in [`providers.py`](../../backend/app/services/credentials/providers.py)
  - no new table, no schema change: [`upstream_credentials`](../database/schema.md#upstream_credentials) has carried a `provider` column since the first migration
  - no frontend change: the console builds its credential screen from `GET /v1/credentials/providers`
- **What SerpFlow spends is what SerpApi bills**, including a search that finds nothing:
  - SerpApi reports "no results" through its `error` field, but the search was processed and charged
  - SerpFlow records that as a successful, billed live call: it counts against your SerpApi quota, appears as spend in the [ledger](../database/schema.md#budget_ledger) and against your budgets, and the empty payload is cached like any other
  - the console shows SerpApi's message instead of a failed run ([executor: an empty answer is still a billed answer](../architecture/executor.md#an-empty-answer-is-still-a-billed-answer), [`SerpApiResponse.is_empty_result`](../../backend/app/integrations/serpapi/client.py))
- **Cache and archive hits spend nothing on your account**; that is the point of [marginal-cost replanning](../architecture/marginal-replanning.md)

## What happens without each key

**Neither key is required to use SerpFlow, and neither absence is a crash.**

- **No SerpApi key**
  - live execution returns `NO_UPSTREAM_CREDENTIAL` (412) **before anything is spent**, instead of failing halfway through a run: the credential is resolved after planning and before the executor starts ([`plan_and_execute`](../../backend/app/services/runs.py), [troubleshooting](../operations/troubleshooting.md#no_upstream_credential))
  - planning, replay and any `test` API key keep working, and cost nothing ([execution modes](../product/execution-modes.md))
- **No Groq key**
  - planning uses the **deterministic selector**
  - not "degraded" in the sense of worse data: it is a real lexical and capability scoring pass over the retrieved shortlist
  - same plan for the same intent, every time
  - it produced the published [benchmark](../product/benchmark.md#results) numbers
  - it costs nothing and makes no network call
- **Which one answered is recorded in plan provenance**
  - a plan's `stage_trace` states the provider and model that chose its engines ([planner: which adapter plans](../architecture/planner.md#which-adapter-plans))
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
  - `CredentialResponse` in [`app/schemas/identity.py`](../../backend/app/schemas/identity.py) says so in its docstring, and a test walks every response model to assert it
- **What you can read back:** nothing derived from the key except its fingerprint (`sha256(key)[:8]`, non-reversible). The rest of a credential's response is metadata: name, provider, scope, `kek_id`, `algo`, validation status, SerpApi's quota readout and timestamps. That holds for everyone, including the organization owner
- Rotation, grace windows and the re-wrap procedure when `CREDENTIAL_KEK` changes: [credentials](credentials.md#validation-and-revocation), [secrets: KEK](secrets.md#kek)

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

**Revoked credentials are skipped**, except a rotated one still inside its grace window, which keeps resolving so in-flight runs finish ([`_usable`](../../backend/app/services/credentials/service.py)).

**Decryption happens at the point of use**, and the plaintext lives for one request ([credentials: where it is decrypted](credentials.md#where-it-is-decrypted)):

- for SerpApi: `ExecutorService`, in `live` and `record` mode only ([executor: the credential boundary](../architecture/executor.md#the-credential-boundary))
- for Groq: [`resolve_llm`](../../backend/app/services/credentials/llm.py), which hands the key straight to the adapter, and falls back to the deterministic selector if the key cannot be decrypted
- neither writes it to a column, a log sink or a response

## The self-hosting exception

Two environment variables remain, and they are the **only** place a key not belonging to an organization can enter the system:

```bash
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
```

- **Consulted only when the organization has brought no Groq key of its own** ([`get_llm`](../../backend/app/integrations/llm/__init__.py), [secrets: inventory](secrets.md#inventory))
- They exist so one person running SerpFlow for themselves need not attach a credential to every organization they create
- `GROQ_BASE_URL`, `GROQ_MODEL` and `GROQ_TIMEOUT_SECONDS` are transport settings, not keys: they apply to every Groq call, including those made with an organization's own key

> **If other people will use your instance, leave both unset.** Otherwise your
> key answers for every organization that has not supplied one, and those
> organizations cannot tell from the interface that this is happening.

- **There is no SerpApi equivalent, deliberately**
  - a `SERPAPI_API_KEY` setting once existed, was read by nothing, and was removed
  - a dead variable that reads as though the platform might spend its own credits is worse than no variable at all
  - a leftover `SERPAPI_API_KEY` line in an old `.env` is simply ignored ([troubleshooting](../operations/troubleshooting.md#a-serpapi_api_key-in-env-does-nothing))
  - `SERPAPI_BASE_URL` and `SERPAPI_TIMEOUT_SECONDS` remain, as transport settings

## Adding a key

**In the console:** Settings → Credentials.

- each provider gets its own card: what the key is for, what happens without it, and where to get one
- **keys are validated on arrival** with one cheap call that spends nothing: the account endpoint for SerpApi, the model list for Groq
- **a key the provider rejects is not stored:** the request fails with `CREDENTIAL_VALIDATION_FAILED` and nothing is written ([credentials: validation and revocation](credentials.md#validation-and-revocation))

**Over the API**, as an owner or admin. The seeded API keys are `developer` and `service` keys, which lack `credential:write` and get a `403`, so sign in for an access token ([local development](../deployment/local.md#using-real-keys)):

```bash
TOKEN=$(curl -s -X POST https://your-instance/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "owner@example.com", "password": "..."}' \
  | python -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

curl -X POST https://your-instance/v1/credentials \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
        "name": "My Groq account",
        "provider": "groq",
        "api_key": "gsk_...",
        "validate_now": true
      }'
```

- `provider` defaults to `serpapi`
- **`project_id`** scopes the key to one project; for SerpApi it also sets that project's `credential_id`
- **`set_as_org_default`** (SerpApi only) makes it the organization default. The first SerpApi key an organization attaches becomes the default without it
- **`validate_now: false`** skips the probe call and leaves `validation_status` at `pending`
- **Requires `credential:write`**, which the owner and admin roles carry ([API keys: roles](api-keys.md#roles))

**To see what this organization still needs to bring:**

```bash
curl https://your-instance/v1/credentials/providers \
  -H "Authorization: Bearer $SERPFLOW_API_KEY"
```

- Each entry reports `required`, `configured`, and the `absent_behaviour` that applies until it is
- `configured` counts only credentials that are not revoked
- **Needs only `credential:read`**, which `developer` keys carry, so a seeded key in [`SERPFLOW_API_KEY`](secrets.md#cli-sdk-and-mcp-read-from-the-shell) works here

## Related

- [Upstream credentials](credentials.md): envelope encryption, rotation and revocation of the keys you bring
- [Secrets](secrets.md): the deployment's own secrets, which are not your upstream keys
- [API keys](api-keys.md): the key you use to call SerpFlow, as opposed to the keys SerpFlow uses for you
- [Threat model](threat-model.md#credential-theft-from-the-database): what protects a stored key
- [Planner: which adapter plans](../architecture/planner.md#which-adapter-plans): what a Groq key changes in planning
- [Executor: an empty answer is still a billed answer](../architecture/executor.md#an-empty-answer-is-still-a-billed-answer): why a no-results search still costs a credit
- [Execution modes](../product/execution-modes.md): which modes need a SerpApi key at all
- [Troubleshooting: `NO_UPSTREAM_CREDENTIAL`](../operations/troubleshooting.md#no_upstream_credential): a live search with no key attached

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Threat model](../security/threat-model.md) | [Docs index](../README.md) · [Security index](../security/README.md) | [Upstream credentials](../security/credentials.md) |
