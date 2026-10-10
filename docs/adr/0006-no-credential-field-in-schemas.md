# 0006. The credential field is absent from schemas, not excluded

<p>
  <a href="../README.md#decisions"><img alt="docs: Decisions" src="https://img.shields.io/badge/docs-Decisions-555555?logo=readthedocs&logoColor=white"></a>
  <img alt="status: accepted" src="https://img.shields.io/badge/status-accepted-3fcf8e">
  <img alt="read: 2 min" src="https://img.shields.io/badge/read-2%20min-555555">
</p>

[Docs](../README.md) › [Decisions](../README.md#decisions) › **0006. The credential field is absent from schemas, not excluded** · page 42 of 50

**Status** Accepted

## Context

- **The upstream SerpApi credential must never appear in an API response**
- **The usual Pydantic approach keeps the field and suppresses it:**

```python
api_key: str = Field(exclude=True)
# or
api_key: SecretStr
```

- **Both are serialization settings, and settings get overridden:**
  - `model_dump(exclude=None)` in a debugging helper
  - a subclass that redeclares the field without the setting
  - a custom serializer added for an unrelated reason
  - `SecretStr` that somebody calls `.get_secret_value()` on while building a response
- **Every one is a plausible one-line change** by someone who does not know the rule, and none looks dangerous in review

## Decision

**The field does not exist.**

```python
class CredentialResponse(APIModel):
    id: str
    name: str
    provider: str
    fingerprint: str      # sha256(secret)[:8]
    display: str          # ...a3f9
    kek_id: str
    algo: str
    validation_status: str
    ...
```

- **No `api_key`, no `secret`, no `ciphertext`**
- A field that does not exist cannot be serialized **by any means, by any future change, in any code path**
- **What the UI needs instead:** the fingerprint and the last four characters. Enough to tell two credentials apart, and not reversible
- **Enforced by tests that walk the response models**, not by reading the class:

```
tests/unit/test_security.py::test_credential_response_schema_has_no_secret_field
tests/unit/test_security.py::test_no_response_schema_anywhere_exposes_a_credential
```

- **The second is the important one:** it checks **every** response schema in `app/schemas`, so a new model that adds such a field fails the suite wherever it was added

## Alternatives rejected

| Alternative | Why it lost |
| --- | --- |
| **`exclude=True`** | A setting. The leak path is someone changing it without understanding why it was there |
| **`SecretStr`** | Protects against accidental `repr` and logging, which is useful, but the value is still present and retrievable. Leaking takes one extra method call instead of being impossible |
| **A response middleware that strips sensitive keys** | Works on a dictionary by key name, so it depends on naming, and fails open on anything it does not recognise |

## Cost

- **Slightly more code:** the three functions that genuinely need the plaintext (each about to make an upstream call with it) read the model directly, not through a response schema
- **That friction is the point:** code paths that touch a plaintext credential **should look different** from the ones that do not

## See also

- [Upstream credentials](../security/credentials.md)
- [Threat model](../security/threat-model.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [ADR 0005: Envelope encryption for upstream credent…](../adr/0005-envelope-encryption.md) | [Docs index](../README.md) | [ADR 0007: Interactive search does not go through K…](../adr/0007-interactive-search-bypasses-kafka.md) |
