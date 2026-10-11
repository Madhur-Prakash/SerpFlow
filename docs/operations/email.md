# Email

<p>
  <a href="../operations/README.md"><img alt="docs: Operations" src="https://img.shields.io/badge/docs-Operations-E6522C?logo=readthedocs&logoColor=white"></a>
  <img alt="Gmail: API" src="https://img.shields.io/badge/Gmail-API-EA4335?logo=gmail&logoColor=white">
  <a href="../../backend/app/core/config.py"><img alt="source: core/config.py" src="https://img.shields.io/badge/source-core%2Fconfig.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 9 min" src="https://img.shields.io/badge/read-9%20min-555555">
</p>

[Docs](../README.md) › [Operations](../operations/README.md) › **Email** · page 46 of 50

**Three [environment variables](../security/secrets.md#inventory) are all it takes to send for real.** With none set, mail goes to the log instead, which keeps [`make dev`](../deployment/local.md#everyday-targets) working with no keys at all.

```bash
GMAIL_CREDENTIALS_B64=   # minted by backend/scripts/mint_gmail_token.py
GMAIL_SENDER=            # the mailbox that consented
EMAIL_FROM_NAME=SerpFlow
```

- **The `From` header is `EMAIL_FROM_NAME <GMAIL_SENDER>`**, or `EMAIL_FROM_NAME <no-reply@serpflow.local>` with no sender set (`Settings.email_sender` in [`app/core/config.py`](../../backend/app/core/config.py))
- **`FRONTEND_URL` is the base of every link in every email.** Its default is `http://localhost:5173`, so a deployment that leaves it unset mails links nobody outside the server can open ([deployment guide, step 4](../deployment/deployment-guide.md#4-configure-the-environment))

Implementation: [`app/services/email/service.py`](../../backend/app/services/email/service.py) · templates in [`app/templates/email/`](../../backend/app/templates/email) · audiences in [`app/services/notifications/audiences.py`](../../backend/app/services/notifications/audiences.py)

## What gets sent

| Trigger | Template | Carries |
| --- | --- | --- |
| [`POST /v1/auth/register`](../api/overview.md#identity-and-access) | `verify_email` | a single-use link to `/verify-email?token=...` |
| `POST /v1/auth/forgot-password` | `password_reset` | a single-use link to `/reset-password?token=...`, valid 1 hour (`PASSWORD_RESET_TTL_SECONDS`) |
| A message for an `email` [notification channel](#audiences) | `notification` | title, message, detail rows, a link into the console |

- **That is the whole list.** There is no invitation email: members are added in the console
- **The reset expiry is enforced; the verification expiry is not.** The verification email says the link expires in 24 hours (`EMAIL_VERIFICATION_TTL_SECONDS`), but `users` has no expiry column for that token and `POST /v1/auth/verify-email` only checks the hash ([`app/api/v1/auth.py`](../../backend/app/api/v1/auth.py)). It is single-use, not time-limited
- **Notification email is sent by a Kafka consumer**, the `serpflow.webhooks` handler, for each enabled channel of kind `email` whose `events` filter matches ([`app/workers/consumers/handlers.py`](../../backend/app/workers/consumers/handlers.py)). Each attempt is a row in [`webhook_deliveries`](../database/schema.md#governance)
  - at HEAD that topic is fed only by the `serpflow.alerts` consumer, and nothing in the request path publishes alerts, so in-app budget alerts are recorded but not mailed. See [Kafka: what goes through it](kafka.md#what-goes-through-it-and-what-does-not)
- **Without Gmail configured, nothing is delivered**, and the links are **not** recoverable from the log or from the API response (see [console](#console))
  - so a production instance needs Gmail for **password resets** to work at all
- **History:** before this existed, `register` minted a verification token and threw the plaintext away, and `forgot-password` stored a reset hash that nothing ever mailed. Both flows were unusable end to end

## Transports

There are two, and **no setting selects between them.** Configuring a credential **is** the instruction to send for real:

```python
_backend = GmailEmailBackend(settings) if settings.email_configured else ConsoleEmailBackend()
```

### Gmail API

- **Why a refresh token, not a password:**
  - Google refuses plain passwords
  - an app password needs 2FA, plus a per-account secret a Workspace admin can switch off
  - a refresh token scoped to `gmail.send` grants **exactly one capability**: it **cannot read the mailbox it sends from**, so a leak costs spam, not an inbox
- **Nothing is reimplemented:** `google-api-python-client` owns the send, `google-auth` owns the token lifecycle
- **Both are synchronous** (httplib2 underneath), so the send leaves the event loop via `anyio.to_thread`. Otherwise it would stall every other task for a round trip
- **Sending is serialised behind a lock**
  - neither the httplib2 connection in a Gmail service object nor a shared `Credentials` is thread-safe
  - two threads refreshing the same token at once is a race
  - transactional mail is a handful of messages, so serialising costs nothing measurable

### Console

- **Records that a message would have been sent**: an `email.sent` event with `"backend": "console"`
- The log line carries the **subject and recipient**
- **Never the body**, because the body holds a single-use token. The body is never handed to the logger at all, so this does not rest on the [redaction filter](observability.md#logging)
- The class docstring says the link is "available from the API response in development"; it is not. `register` returns only session tokens

## Setting up Gmail

1. **Create an OAuth client.** In a Google Cloud project with the **Gmail API enabled**, create an OAuth client ID of type **Desktop app**, and download its JSON
   - a *service account* key will not work: sending as a user needs that user's consent
2. **Install the dev dependency.** Only the minting script runs a consent flow, so it stays out of the runtime set and the container image:

   ```bash
   cd backend
   uv pip install --python .venv -e ".[dev]"
   ```

3. **Mint the token** with [`backend/scripts/mint_gmail_token.py`](../../backend/scripts/mint_gmail_token.py), still in `backend/`. Sign in as the mailbox that should **send**:

   ```bash
   .venv/bin/python scripts/mint_gmail_token.py path/to/credentials.json   # .venv\Scripts\python.exe on Windows
   ```

   - it prints one line, ready to paste into `.env`
4. **Set `GMAIL_SENDER`** to the mailbox you consented as, then **restart**
   - settings are read once at startup, so a running server keeps the old value

- **`GMAIL_CREDENTIALS_B64` is a live credential.** Treat it like any other secret: never commit it, never paste it into an issue. See [secrets](../security/secrets.md)
- **It is a base64 pickle, unpickled without validation.** That is safe only because it comes from the operator's own environment; it must never be sourced from the database, an upload or a request ([`_gmail_service`](../../backend/app/services/email/service.py))
- **No refresh token, no credential:** the script asks for `access_type=offline` with `prompt=consent`, and exits non-zero if Google still returns no refresh token. Revoke the app at myaccount.google.com/permissions and run it again ([`backend/scripts/mint_gmail_token.py`](../../backend/scripts/mint_gmail_token.py))

## invalid_grant

- **A send failing with `invalid_grant` means Google rejected the refresh token itself**, not that anything is misconfigured. The only fix is a new token
- The error says nothing useful, so the service substitutes its own message
- **The most likely cause is invisible from Google's wording:** while the OAuth consent screen is in **Testing**, Google expires every refresh token after **seven days**
  - publish the app (Google Auth Platform → Audience → Publish app) **before** minting a token you intend to keep
- **Other causes, in order:** access was revoked, the account password changed, or the OAuth client was deleted

## Retries

```
attempts   3
waits      1s, 2s
```

- **Deliberately short:** a send is awaited inside the request or job that triggered it
- **Only transient failures are retried**
  - 429 and 5xx are Google saying "not now"; transport, `OSError` and timeout failures are retried too
  - every other 4xx, and any `RefreshError`, is "not ever": a dead credential fails on the **first** attempt, not after three attempts and three seconds of waiting
- **Each retry logs `email.retry`** with the attempt number and the cause
- **The error says which kind it was**, so a dead credential is not mistaken for a network wobble

## Delivery failure does not fail the request

```python
except EmailSendError as exc:
    log.warning("email delivery failed", extra={...})
```

- **An account that was created successfully should not come back as a 500** because Gmail was unreachable
- **More importantly:** `forgot-password` returns the same response whether or not the address exists
  - raising on a send failure would turn a delivery problem into an **account-enumeration oracle**
- The failure is logged **with its cause** as `email.failed`, with the context (`verification`, `password reset`), recipient and template. The bodies, which carry single-use tokens, are not
- **A notification email that fails** marks its `webhook_deliveries` row `failed` with the error, bumps the channel's `failure_count` and sets `last_delivery_status` to `email_failed`. The consumer carries on

## Audiences

**A notification channel's name is not decoration: it picks how the email reads.** The facts are the same in every variant; only the framing changes.

| Label | Subject prefix | Detail rows | Reads as |
| --- | --- | --- | --- |
| On-call | `[ALERT] ` | yes | urgent, "This needs attention now." |
| Engineering | none | yes | technical, no urgency |
| Billing | none | yes | spend; reminds that the ledger and the upstream account are two numbers |
| Security | `[SECURITY] ` | yes | says the audit log is hash-chained and can be verified |
| Leadership | none | **no** | plain summary, no identifiers or engine names |
| anything else | none | yes | generic, states the facts |

- **Matching is on a slug**, so "On-call", "on call" and "ON-CALL" are one preset, while "on-call vendors" is not: no substring guessing
- **The detail rows** are severity, project id, engine, limit and current usage, taken from the event payload when present
- **No model writes any of it.** Every variant is a fixed template, so the same alert to the same label renders byte-identically, and event data cannot become instructions
- The presets are what `GET /v1/notification-channels/labels` returns ([governance endpoints](../api/overview.md#governance)); 20 tests in `tests/unit/test_channel_labels.py` pin them

## Rendering

- **Jinja2, autoescaped, with `StrictUndefined`:** a template referencing a variable nobody passed fails in a test, instead of rendering a blank gap in somebody's inbox
- **Every email is `multipart/alternative`**, with both a text and an HTML body
- **The HTML is table-based with inline styles**: what mail clients actually render

```
base.html              the shell: header, action button, detail rows, footer
verify_email.*         confirm an address
password_reset.*       choose a new password
notification.*         an alert, with detail rows and the audience's opening and closing
```

- **Each email is two files**, `.html` and `.txt`; only `base.html` has no text twin
- **Notification emails link to `/app/settings` in the footer** to manage email notifications, and the button goes where the alert kind points (budgets, cache, credentials or runs; `/app` for a kind not in `_ALERT_LABELS`)
- **Interpolated values are escaped.** A display name is user-supplied, and `tests/unit/test_email.py` asserts that `<script>` in one does not become markup

## Testing

```python
from app.services.email import set_email_backend

class Capture:
    def __init__(self): self.sent = []
    async def send(self, message): self.sent.append(message)

set_email_backend(Capture())
```

- **21 tests** in [`tests/unit/test_email.py`](../../backend/tests/unit/test_email.py) cover rendering, escaping, transport selection, MIME structure, failure classification, and the rule that bodies never reach a log

## Related

- [Secrets](../security/secrets.md#inventory): `GMAIL_CREDENTIALS_B64` and the other email variables
- [Deployment guide](../deployment/deployment-guide.md#4-configure-the-environment): setting `FRONTEND_URL` and Gmail on a server
- [Kafka](kafka.md#topics): the `serpflow.webhooks` consumer that sends notification email
- [Threat model](../security/threat-model.md#threats-and-responses): the threats around accounts and sign-in that email takes part in
- [API keys](../security/api-keys.md): the other half of account access, for machines rather than people
- [Observability](observability.md#logging): where `email.sent`, `email.retry` and `email.failed` land
- [Troubleshooting](troubleshooting.md#password-reset-or-verification-email-never-arrives): the email that never arrives

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Startup bootstrap](../operations/bootstrap.md) | [Docs index](../README.md) · [Operations index](../operations/README.md) | [Observability](../operations/observability.md) |
