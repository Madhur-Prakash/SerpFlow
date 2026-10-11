# Python SDK

<p>
  <a href="../README.md#sdks"><img alt="docs: SDKs" src="https://img.shields.io/badge/docs-SDKs-8250DF?logo=readthedocs&logoColor=white"></a>
  <img alt="runtime deps: httpx" src="https://img.shields.io/badge/runtime%20deps-httpx-3fcf8e">
  <img alt="Python: 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
  <a href="../../backend/app/sdk/__init__.py"><img alt="source: sdk/__init__.py" src="https://img.shields.io/badge/source-sdk%2F____init____.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 8 min" src="https://img.shields.io/badge/read-8%20min-555555">
</p>

[Docs](../README.md) › [SDKs](../README.md#sdks) › **Python SDK** · page 24 of 57

- **A sync client, an async client and a SerpApi drop-in**, in one module: [`app/sdk/__init__.py`](../../backend/app/sdk/__init__.py)
- **One runtime dependency, `httpx`.** The module imports nothing else from the backend, so it can be lifted out into its own distribution unchanged
- **Imported as `serpflow`** through [`backend/serpflow.py`](../../backend/serpflow.py), a re-export shim

**On this page:** [install](#install) · [configure](#configure) · [quick start](#quick-start) · [methods](#methods) · [result types](#result-types) · [streaming](#streaming) · [errors](#errors) · [async](#async) · [recipes](#recipes) · [SerpApi drop-in](#the-serpapi-drop-in) · [limitations](#known-limitations)

## Install

**Today, from a checkout.** The SDK is not on PyPI yet.

```bash
make install-backend                  # uv venv on 3.13 + editable install of backend/
source backend/.venv/bin/activate     # Windows: backend\.venv\Scripts\activate
python -c "from serpflow import SerpFlow; print(SerpFlow)"
```

- **Use an editable install** (`uv pip install -e backend`). It puts `backend/` itself on `sys.path`, which is what makes `import serpflow` resolve
- **A non-editable install does not ship `serpflow.py`.** `pip install "git+https://github.com/Madhur-Prakash/SerpFlow#subdirectory=backend"` installs the `app` package only, so import from there:

```python
from app.sdk import SerpFlow   # works from any install
from serpflow import SerpFlow  # editable installs only, until the packaging fix in "Releasing"
```

- **Python 3.13 or later**, because that is what the backend package requires. The SDK code itself runs on 3.10+
- **After the first release:** `pip install serpflow`. What has to change first: [releasing](releasing.md#before-the-first-python-release)

## Configure

```python
SerpFlow(api_key=None, *, base_url=None, project_id=None, timeout=120.0)
```

| Argument | Default | What it does |
| --- | --- | --- |
| `api_key` | `SERPFLOW_API_KEY` | Sent as `X-API-Key` on every request. **Neither set raises `ValueError`** at construction |
| `base_url` | `SERPFLOW_BASE_URL`, else `http://localhost:8000` | A trailing `/` is stripped |
| `project_id` | the key's project | Sent as the `X-SerpFlow-Project` header **and** as `project_id` in plan and search bodies |
| `timeout` | `120.0` seconds | Passed to `httpx.Client`. A plan that calls a language model can take tens of seconds |

- **`SERPFLOW_BASE_URL` is read once, when the module is imported.** Setting it afterwards has no effect; pass `base_url=` instead
- **The client holds a connection pool.** Use it as a context manager, or call `close()`

```python
with SerpFlow() as client:          # SERPFLOW_API_KEY from the environment
    ...
```

## Quick start

```python
from serpflow import SerpFlow

with SerpFlow(api_key="sf_test_...") as client:
    # Plan only. Calls a language model, not SerpApi: zero credits.
    plan = client.route("review rings among Koramangala cafes", budget=20)
    print(" -> ".join(plan.engines), plan.naive_cost, "->", plan.marginal_cost)
    if plan.marginal_replan_changed_selection:
        print(plan.replan_explanation)

    # Plan with cache-aware replanning, then execute.
    result = client.search("recent reviews for Ichiran in Seoul", budget=20)
    print(result.mode, result.credits_spent, "spent,", result.credits_saved, "saved")
    for item in result.items:
        print(" ", item.get("title"))

    # Why did that plan win?
    why = client.explain(result.run_id)
    for candidate in why["candidates"]:
        print(candidate)
```

## Methods

**`SerpFlow`, the sync client.** Every method raises [`SerpFlowError`](#errors) on a 4xx or 5xx.

| Method | Request | Returns |
| --- | --- | --- |
| `route(intent, *, budget=None)` | `POST /v1/plan` | [`PlanView`](#planview). **Spends zero credits** |
| `plan(...)` | alias of `route` | |
| `search(intent, *, budget=None)` | `POST /v1/search` | [`SearchResult`](#searchresult) |
| `run(...)` | alias of `search` (**not** `POST /v1/run`) | |
| `stream(intent, *, budget=None)` | `POST /v1/search` with `stream: true`, then `GET /v1/runs/{id}/stream` | iterator of [`RunEvent`](#runevent) |
| `get_run(run_id)` | `GET /v1/runs/{id}` | `dict`: the Run Inspector payload |
| `explain(run_id)` | `GET /v1/runs/{id}`, reshaped | `dict`: `run_id`, `intent`, `selected`, `naive_cost`, `marginal_cost`, `changed_selection`, `explanation`, `candidates`, `rejected_alternatives` |
| `replay(run_id)` | `POST /v1/runs/{id}/replay` | `SearchResult` against **today's** cache state |
| `runs(limit=25, **filters)` | `GET /v1/runs` | `list[dict]`, the `items` of one page |
| `catalog(engine=None)` | `GET /v1/catalog`, or `/v1/catalog/engines/{engine}` | `dict` |
| `budgets()` | `GET /v1/budgets` | `dict` |
| `health()` | `GET /readyz` | `dict`: `status`, `version`, `mode`, `catalog_version`, `checks` |
| `close()` | | closes the connection pool |

- **`intent`** is 3 to 2,000 characters
- **`budget`** is a credit cap for this call, 1 to 100,000. Leave it out to use the project's budget. Outside that range the API answers `VALIDATION_ERROR`
- **`runs` filters** are passed straight through as query parameters: `status`, `engine`, `changed_selection`, `project_id`. A filter set to `None` is dropped

```python
failed = client.runs(limit=50, status="failed")
thesis = client.runs(changed_selection=True)
```

## Result types

All three are `dataclass(slots=True)`. **Each keeps the untouched JSON in `raw`**, so a field the server adds later is reachable before the SDK names it.

### PlanView

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | `str` | plan id |
| `intent` | `str` | the intent as planned |
| `engines` | `list[str]` | the selected plan's engines, in step order |
| `naive_cost` | `int` | credits if every step ran cold |
| `marginal_cost` | `int` | credits given what is already warm |
| `savings` | `int` | `naive_cost - marginal_cost` |
| `candidate_count` | `int` | plans considered |
| `confidence` | `float` | the planner's confidence |
| `catalog_version` | `str` | e.g. `v1.0.0` |
| `warm_steps` | `list[dict]` | which steps the cache already satisfies |
| `marginal_replan_changed_selection` | `bool` | **the thesis:** did cache state change which plan won? |
| `replan_explanation` | `str` or `None` | why, in a sentence |
| `rejected_alternatives` | `list[dict]` | every loser, with its costs, coverage and reason |
| `budget_reduction` | `dict` or `None` | fan-outs cut to fit the budget, with an impact note per step |
| `projected_full_scale_cost` | `int` or `None` | a projection only; never executed live |
| `raw` | `dict` | the full plan JSON, including `steps` and their `cache_state` |

### SearchResult

| Field | Type | Meaning |
| --- | --- | --- |
| `run_id` | `str` | the run, for `explain`, `replay` and the Run Inspector |
| `status` | `str` | `succeeded`, `failed`, ... |
| `mode` | `str` | `LIVE`, `MOCK`, `REPLAY` or `RECORD`. **Always present:** mocked or replayed data is never presented as live |
| `credits_spent` | `int` | what this run actually cost |
| `credits_saved` | `int` | what the cache and routing saved |
| `plan` | `PlanView` | the plan that ran |
| `results` | `dict` | the results payload |
| `items` | `list[dict]` | property: `results["summary"]["items"]`, or `[]` |
| `raw` | `dict` | the full response |

### RunEvent

| Field | Type | Meaning |
| --- | --- | --- |
| `stage` | `str` | `queued`, `analyzing_intent`, ..., `complete` |
| `status` | `str` | `running`, `complete`, `step_complete`, ... |
| `elapsed_ms` | `float` | since the run started |
| `detail` | `dict` | stage-specific data |
| `type` | `str` | `stage`, `complete` or `error` |

- The stage list and frame contract: [streaming](../api/streaming.md)

## Streaming

```python
for event in client.stream("cafes in Koramangala with outdoor seating", budget=20):
    print(f"{event.stage:<24} {event.status:<14} {event.elapsed_ms:7.1f} ms")
    if event.type == "error":
        print("failed:", event.detail["code"], event.detail["message"])
```

- **One frame per real backend stage transition.** No timer anywhere in this path
- **Heartbeats are filtered out** for you
- **The iterator ends by itself** after the `complete` frame, or the `error` frame whose `detail` carries `code` and `message`
- **A failed run arrives as an `error` frame, not an exception.** Only a failure to start the run raises `SerpFlowError`
- **`RunEvent` does not carry the run id**, although every frame on the wire has `run_id` and `sequence`. When you need the run afterwards, call `search()` instead, or take the newest of `client.runs(limit=1)`

## Errors

```python
from serpflow import SerpFlow, SerpFlowError

try:
    client.search("flights from Hyderabad to Da Nang in late November", budget=5)
except SerpFlowError as error:
    print(error.code)        # "BUDGET_EXHAUSTED"
    print(error.message)     # human-readable, safe to show
    print(error.status)      # 402
    print(error.request_id)  # quote it when reporting a problem
    print(error)             # "BUDGET_EXHAUSTED: ... (request 8a9e...)"
```

| Raised | When |
| --- | --- |
| `SerpFlowError` | the API answered 4xx or 5xx. `code` is the stable machine code; a non-JSON body becomes `HTTP_<status>` |
| `ValueError` | no API key at construction |
| `httpx.HTTPError` subclasses | the API could not be reached, or timed out. **These are not wrapped** |

- **Branch on `code`, never on `message`.** The full list, with what to do about each: [API errors](../api/overview.md#errors)
- **`BUDGET_EXHAUSTED` is your SerpFlow cap. `UPSTREAM_QUOTA_EXHAUSTED` is SerpApi's.** They are never conflated
- **There is no `remedy` property in Python.** The TypeScript SDK has one; the table in the API overview is the same advice

## Async

```python
import asyncio
from serpflow import AsyncSerpFlow

async def main() -> None:
    async with AsyncSerpFlow(api_key="sf_test_...") as client:
        plan, result = await asyncio.gather(
            client.route("review rings among Koramangala cafes", budget=20),
            client.search("flights from Hyderabad to Da Nang in late November"),
        )
        async for event in client.stream("bakeries in Koramangala"):
            print(event.stage, event.status)

asyncio.run(main())
```

- **Same constructor, same result types**
- **Methods:** `route` / `plan`, `search` / `run`, `stream`, `aclose`. **Nothing else**: `get_run`, `explain`, `replay`, `runs`, `catalog`, `budgets` and `health` are sync-only for now
- **Close it:** `async with`, or `await client.aclose()`

## Recipes

**Point at another deployment**

```python
client = SerpFlow(base_url="https://serpflow.example.com", api_key=os.environ["SERPFLOW_API_KEY"])
```

**Work in a second project**

```python
market = SerpFlow(project_id="prj_01M3...")   # must belong to the key's organization
```

- A project in another organization is answered with `NOT_FOUND`, deliberately: confirming that an id exists elsewhere would itself leak

**Plan first, execute only if it is cheap**

```python
plan = client.route(intent, budget=50)
if plan.marginal_cost <= 10:
    result = client.search(intent, budget=50)
```

- **The search re-plans.** Cache state can change between the two calls, so the executed plan can differ from the one you checked

**Report a bad semantic cache hit.** Not wrapped yet; call the endpoint:

```python
import httpx
httpx.post(
    f"{client.base_url}/v1/runs/{run_id}/report-false-hit",
    headers={"X-API-Key": client.api_key},
    json={"note": "different neighbourhood", "invalidate_entry": True},
)
```

**In tests.** Use a `sf_test_...` key against a local stack: deterministic results, zero credits. See [local development](../deployment/local.md).

## The SerpApi drop-in

```python
from serpflow import SerpApiCompat

search = SerpApiCompat({
    "engine": "google_maps",
    "q": "cafes in Koramangala",
    "api_key": "sf_test_...",
})
results = search.get_dict()          # get_json() returns the same as a string

print(results["search_metadata"]["serpflow_mode"])
print(results["search_metadata"]["serpflow_credits_saved"])
```

```python
SerpApiCompat(params, *, base_url=None)
```

- **The call keeps SerpApi's shape:** a params dict in, `get_dict()` / `get_json()` out, `search_metadata` and `search_parameters` in the result
- **What it actually sends:** `q` (or `query`) becomes the intent of a `POST /v1/search`. **SerpFlow's planner then picks the engines**
- **`engine` and every other parameter are not forwarded.** They are echoed back in `search_parameters` and `search_metadata.engine`, so code that reads them keeps working, but they do not constrain the plan
- **`api_key`** is taken out of `params`; `SERPFLOW_API_KEY` is the fallback
- **`search_metadata` gains** `serpflow_mode`, `serpflow_credits_spent` and `serpflow_credits_saved`. `status` is `Success` when the run succeeded, `Error` otherwise
- **What you gain:** caching, budget enforcement and provenance on code you have not rewritten

## Known limitations

- **`AsyncSerpFlow` lacks the inspection methods** listed under [async](#async)
- **`stream()` does not raise if the stream request itself fails.** The `POST` is checked; a 4xx on `GET /v1/runs/{id}/stream` ends the iterator with no frames
- **`RunEvent` drops `run_id` and `sequence`** from each frame
- **No automatic retries.** Retry `RATE_LIMITED` and network errors yourself, with backoff
- **`explain()` reshapes `get_run()` on the client.** Its keys are the SDK's, not an API contract
- **The drop-in ignores `engine`** and the other SerpApi parameters, as described [above](#the-serpapi-drop-in)

## Related

- [SDKs and tools](overview.md#what-each-can-do): how the Python clients compare with the other surfaces
- [TypeScript SDK](typescript.md): the same API, for JavaScript runtimes
- [API overview](../api/overview.md#errors): every error code `SerpFlowError.code` can carry
- [Streaming](../api/streaming.md): the frame contract behind `stream()`
- [Execution modes](../product/execution-modes.md): what `result.mode` means, and how to get `LIVE`
- [Releasing](releasing.md#before-the-first-python-release): what has to change before `pip install serpflow` works

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [SDKs and tools](../sdks/overview.md) | [Docs index](../README.md) | [TypeScript SDK](../sdks/typescript.md) |
