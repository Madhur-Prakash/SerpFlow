# Email

Three environment variables are all it takes to send for real. With none of
them set, mail goes to the log instead, which is what keeps `make dev` working
with no keys at all.

```bash
GMAIL_CREDENTIALS_B64=   # minted by scripts/mint_gmail_token.py
GMAIL_SENDER=            # the mailbox that consented
EMAIL_FROM_NAME=SerpFlow
```

Implementation:
[`app/services/email/service.py`](../../backend/app/services/email/service.py),
templates in [`app/templates/email/`](../../backend/app/templates/email).

## What gets sent

| Trigger | Template | Carries |
| --- | --- | --- |
| `POST /v1/auth/register` | `verify_email` | a single-use verification link |
| `POST /v1/auth/forgot-password` | `password_reset` | a single-use reset link, 1 hour |
| An alert routed to an `email` notification channel | `notification` | title, message, detail rows |

Before this existed, `register` minted a verification token and threw the
plaintext away, and `forgot-password` stored a reset hash that nothing ever
mailed. Both flows were unusable end to end. Email channels were created and
then marked `skipped` by the webhook worker.

## Transports

There are two, and **no setting selects between them**. Configuring a
credential *is* the instruction to send for real:

```python
_backend = GmailEmailBackend(settings) if settings.email_configured else ConsoleEmailBackend()
```

### Gmail API

Google refuses plain passwords. An app password needs 2FA plus a per-account
secret a Workspace admin can switch off. A refresh token scoped to
`gmail.send` grants exactly one capability — it **cannot read the mailbox it
sends from**, so a leak costs spam rather than the contents of an inbox.

`google-api-python-client` owns the send and `google-auth` owns the token
lifecycle, so neither is reimplemented. Both are synchronous (httplib2
underneath), so the send leaves the event loop via `anyio.to_thread` or it
stalls every other task for the length of a round trip.

Sending is serialised behind a lock: neither the httplib2 connection inside a
Gmail service object nor a shared `Credentials` is thread-safe, and two threads
refreshing the same token at once is a race on it. Transactional mail is a
handful of messages, so serialising costs nothing measurable.

### Console

Records that a message would have been sent. The log line carries the template,
the subject and the recipient — never the body, because the body holds a
single-use token.

## Setting up Gmail

1. In a Google Cloud project with the **Gmail API enabled**, create an OAuth
   client ID of type **Desktop app** and download its JSON. A *service account*
   key will not work: sending as a user needs that user's consent.

2. Install the dev dependency — only the minting script runs a consent flow, so
   it stays out of the runtime set and out of the container image:

   ```bash
   cd backend
   uv pip install --python .venv -e ".[dev]"
   ```

3. Mint the token. Sign in as the mailbox that should **send**:

   ```bash
   python scripts/mint_gmail_token.py path/to/credentials.json
   ```

   It prints one line, ready to paste into `.env`.

4. Set `GMAIL_SENDER` to the mailbox you consented as, and restart. Settings
   are read once at startup, so a running server keeps the old value.

## invalid_grant

A send failing with `invalid_grant` means Google has rejected the refresh token
itself, not that anything is misconfigured. The only fix is a new token.

The error says nothing useful, so the service substitutes its own message. The
most likely cause is invisible from Google's wording: **while the OAuth consent
screen is in Testing, Google expires every refresh token it issues after seven
days.** Publish the app (Google Auth Platform → Audience → Publish app) before
minting a token you intend to keep.

Other causes, in order: access was revoked, the account password changed, or
the OAuth client was deleted.

## Retries

```
attempts   3
waits      1s, 2s
```

Deliberately short: a send is awaited inside the request or job that triggered
it. Only **transient** failures are retried at all — 429 and 5xx are Google
saying "not now"; every other 4xx, and any `RefreshError`, is "not ever", so a
dead credential fails on the first attempt rather than after six seconds of
waiting.

The error says which kind it was, so a dead credential is not mistaken for a
network wobble.

## Delivery failure does not fail the request

```python
except EmailSendError as exc:
    log.warning("email delivery failed", extra={...})
```

An account that was created successfully should not come back as a 500 because
Gmail was unreachable. More importantly, `forgot-password` deliberately returns
the same response whether or not the address exists — raising on a send failure
would turn a delivery problem into an **account-enumeration oracle**.

The failure is logged with its cause. The bodies, which carry single-use
tokens, are not.

## Rendering

Jinja2, autoescaped, with `StrictUndefined`: a template referencing a variable
nobody passed fails in a test rather than rendering a blank gap in somebody's
inbox.

Every email is sent as `multipart/alternative` with both a text and an HTML
body. The HTML is table-based with inline styles, which is what mail clients
actually render.

```
base.html              the shell: header, action button, detail rows, footer
verify_email.*         confirm an address
password_reset.*       choose a new password
notification.*         an alert, with detail rows
```

Interpolated values are escaped. A display name is user-supplied, and
`tests/unit/test_email.py` asserts that `<script>` in one does not become
markup.

## Testing

```python
from app.services.email import set_email_backend

class Capture:
    def __init__(self): self.sent = []
    async def send(self, message): self.sent.append(message)

set_email_backend(Capture())
```

21 tests cover rendering, escaping, transport selection, MIME structure, the
failure classification and the rule that bodies never reach a log.

## Related

- [API keys](../security/api-keys.md)
- [Secrets](../security/secrets.md)
- [Observability](observability.md)
