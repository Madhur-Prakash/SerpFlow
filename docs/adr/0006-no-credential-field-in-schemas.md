# 0006. The credential field is absent from schemas, not excluded

**Status** Accepted

## Context

The upstream SerpApi credential must never appear in an API response. The usual
way to express that in Pydantic is to keep the field and suppress it:

```python
api_key: str = Field(exclude=True)
# or
api_key: SecretStr
```

Both are serialization **settings**. Settings have a way of being overridden.

- `model_dump(exclude=None)` in a debugging helper.
- A subclass that redeclares the field without the setting.
- A custom serializer added for an unrelated reason.
- `SecretStr` that somebody calls `.get_secret_value()` on while building a
  response.

Every one of those is a plausible single-line change by someone who does not
know the rule, and none of them looks dangerous in review.

## Decision

The field does not exist.

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

There is no `api_key`, no `secret`, no `ciphertext`. A field that does not
exist cannot be serialized by any means, by any future change, in any code
path.

What the UI needs instead is the fingerprint and the last four characters,
which are enough to tell two credentials apart and are not reversible.

This is enforced by tests that walk the response models rather than by reading
the class:

```
tests/unit/test_security.py::test_credential_response_schema_has_no_secret_field
tests/unit/test_security.py::test_no_response_schema_anywhere_exposes_a_credential
```

The second is the important one. It checks **every** response schema in
`app/schemas`, so a new model that adds such a field fails the suite regardless
of where it was added.

## Alternatives rejected

**`exclude=True`.** Covered above. It is a setting, and the leak path is
someone changing the setting without understanding why it was there.

**`SecretStr`.** Protects against accidental `repr` and logging, which is
useful, but the value is still present and still retrievable. It makes leaking
require one extra method call rather than making it impossible.

**A response middleware that strips sensitive keys.** Operates on a dictionary
by key name, so it depends on naming and fails open on anything it does not
recognise.

## Cost

Slightly more code. The three functions that genuinely need the plaintext — all
of which immediately make an upstream call with it — read the model directly
rather than going through a response schema.

That friction is the point. The code paths that touch a plaintext credential
should look different from the code paths that do not.

## See also

- [Upstream credentials](../security/credentials.md)
- [Threat model](../security/threat-model.md)
