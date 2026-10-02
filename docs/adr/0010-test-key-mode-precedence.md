# 0010. A test key overrides the execution mode, absolutely

**Status** Accepted

## Context

There are four execution modes, and they interact with the credential the
caller presents:

```
live     normal billable execution against SerpApi
record   execute live and persist cassettes
replay   serve from cassettes, never the network
mock     deterministic generated results
```

`SERPFLOW_MODE` is an environment variable. API keys carry an environment
segment, `sf_live_...` or `sf_test_...`. Two inputs, one outcome, and the
question is which wins.

Getting this wrong costs money in the most embarrassing way available: a test
suite that spends real credits because `SERPFLOW_MODE` happened to be `live` in
that shell.

## Decision

A `test` API key routes to the deterministic mock **regardless** of
`SERPFLOW_MODE`. The precedence is absolute and is not overridable by any
configuration.

```python
@property
def is_test(self) -> bool:
    return self.environment == "test"
```

The environment segment is readable from the key structure **before** any
database lookup, so the decision is made at the earliest possible point rather
than deep inside the executor where a code path might miss it.

The corollary, equally absolute: **replay never silently accesses the
network.** A cassette miss raises `REPLAY_CASSETTE_MISS` and fails the request.
It does not fall back to a live call.

Every response carries `X-SerpFlow-Mode`, always present, so mocked or replayed
data is never presented as live.

## Alternatives rejected

**`SERPFLOW_MODE` wins.** Means a developer with a live-configured environment
cannot safely run tests, and the failure is silent and billable.

**A per-request mode parameter.** Another input to get wrong, and it moves the
decision to the caller — including a caller that has been compromised.

**Replay falls back to live on a miss.** Superficially convenient: the test
passes instead of failing. It is the worst option on the list, because the
whole point of replay is a guarantee that no network access occurs, and a
fallback converts that guarantee into a hope. A missing cassette should be
loud.

## Cost

A `live` key is required to spend real credits, which means a developer
deliberately testing live behaviour has to use the right key rather than
flipping an environment variable. That friction is intentional.

And `REPLAY_CASSETTE_MISS` will be hit, regularly, during development. It is a
real error that stops work until a cassette is recorded or a `test` key is
used. The alternative is a quiet charge, which is worse.

## See also

- [API keys](../security/api-keys.md)
- [Local development](../deployment/local.md)
- [Executor architecture](../architecture/executor.md)
