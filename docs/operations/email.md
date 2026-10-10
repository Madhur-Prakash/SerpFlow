# Email

<p>
  <a href="../README.md#operations"><img alt="docs: Operations" src="https://img.shields.io/badge/docs-Operations-E6522C?logo=readthedocs&logoColor=white"></a>
  <img alt="Gmail: API" src="https://img.shields.io/badge/Gmail-API-EA4335?logo=gmail&logoColor=white">
  <a href="../../backend/app/services/email/service.py"><img alt="source: email/service.py" src="https://img.shields.io/badge/source-email%2Fservice.py-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 5 min" src="https://img.shields.io/badge/read-5%20min-555555">
</p>

[Docs](../README.md) › [Operations](../README.md#operations) › **Email** · page 31 of 50

**Three environment variables are all it takes to send for real.** With none set, mail goes to the log instead, which keeps `make dev` working with no keys at all.

```bash
GMAIL_CREDENTIALS_B64=   # minted by scripts/mint_gmail_token.py
GMAIL_SENDER=            # the mailbox that consented
EMAIL_FROM_NAME=SerpFlow
```

Implementation: [`app/services/email/service.py`](../../backend/app/services/email/service.py) · templates in [`app/templates/email/`](../../backend/app/templates/email)

## What gets sent

| Trigger | Template | Carries |
| --- | --- | --- |
| `POST /v1/auth/register` | `verify_email` | a single-use verification link |
| `POST /v1/auth/forgot-password` | `password_reset` | a single-use reset link, valid 1 hour |
| An alert routed to an `email` notification channel | `notification` | title, message, detail rows |

- **That is the whole list.** There is no invitation email: members are added in the console
- **Without Gmail configured, nothing is delivered**, and the links are **not** recoverable from the log (see [console](#console))
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

- **Records that a message would have been sent**
- The log line carries the **template, subject and recipient**
- **Never the body**, because the body holds a single-use token

## Setting up Gmail

1. **Create an OAuth client.** In a Google Cloud project with the **Gmail API enabled**, create an OAuth client ID of type **Desktop app**, and download its JSON
   - a *service account* key will not work: sending as a user needs that user's consent
2. **Install the dev dependency.** Only the minting script runs a consent flow, so it stays out of the runtime set and the container image:

   ```bash
   cd backend
   uv pip install --python .venv -e ".[dev]"
   ```

3. **Mint the token.** Sign in as the mailbox that should **send**:

   ```bash
   python scripts/mint_gmail_token.py path/to/credentials.json
   ```

   - it prints one line, ready to paste into `.env`
4. **Set `GMAIL_SENDER`** to the mailbox you consented as, then **restart**
   - settings are read once at startup, so a running server keeps the old value

- **`GMAIL_CREDENTIALS_B64` is a live credential.** Treat it like any other secret: never commit it, never paste it into an issue. See [secrets](../security/secrets.md)

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
  - 429 and 5xx are Google saying "not now"
  - every other 4xx, and any `RefreshError`, is "not ever": a dead credential fails on the **first** attempt, not after six seconds
- **The error says which kind it was**, so a dead credential is not mistaken for a network wobble

## Delivery failure does not fail the request

```python
except EmailSendError as exc:
    log.warning("email delivery failed", extra={...})
```

- **An account that was created successfully should not come back as a 500** because Gmail was unreachable
- **More importantly:** `forgot-password` returns the same response whether or not the address exists
  - raising on a send failure would turn a delivery problem into an **account-enumeration oracle**
- The failure is logged **with its cause**. The bodies, which carry single-use tokens, are not

## Rendering

- **Jinja2, autoescaped, with `StrictUndefined`:** a template referencing a variable nobody passed fails in a test, instead of rendering a blank gap in somebody's inbox
- **Every email is `multipart/alternative`**, with both a text and an HTML body
- **The HTML is table-based with inline styles**: what mail clients actually render

```
base.html              the shell: header, action button, detail rows, footer
verify_email.*         confirm an address
password_reset.*       choose a new password
notification.*         an alert, with detail rows
```

- **Interpolated values are escaped.** A display name is user-supplied, and `tests/unit/test_email.py` asserts that `<script>` in one does not become markup

## Testing

```python
from app.services.email import set_email_backend

class Capture:
    def __init__(self): self.sent = []
    async def send(self, message): self.sent.append(message)

set_email_backend(Capture())
```

- **21 tests** cover rendering, escaping, transport selection, MIME structure, failure classification, and the rule that bodies never reach a log

## Related

- [Secrets](../security/secrets.md)
- [API keys](../security/api-keys.md)
- [Observability](observability.md)
- [Deployment guide](../deployment/deployment-guide.md)

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Startup bootstrap](../operations/bootstrap.md) | [Docs index](../README.md) | [Observability](../operations/observability.md) |
