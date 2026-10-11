# Security

<p>
  <a href="../README.md#security"><img alt="docs: Security" src="https://img.shields.io/badge/docs-Security-6E40C9?logo=readthedocs&logoColor=white"></a>
  <img alt="pages: 5" src="https://img.shields.io/badge/pages-5-6E40C9">
  <img alt="read: 8 min" src="https://img.shields.io/badge/read-8%20min-555555">
</p>

[Docs](../README.md) › [Security](../README.md#security) › **Security** · page 38 of 57

**What SerpFlow holds that is worth stealing, how each of those secrets is protected, and what is deliberately left undefended.**

- **Read it to** judge whether an instance is safe to open to other people, rotate a secret without surprises, and follow a key from creation to revocation
- **For operators and reviewers:** anyone running an instance that other organizations use, or auditing one
- **New here? Start with the [threat model](threat-model.md#assets).** It names each asset and links the page that protects it
- **Found a security problem? Open a public GitHub issue**, with no real keys or secrets in it: [SECURITY.md: reporting a vulnerability](../../SECURITY.md#reporting-a-vulnerability). SerpFlow is self-hosted, so an open report lets every operator see the problem and its fix at the same time

## Pages

| # | Page | Read it to |
| --- | --- | --- |
| 1 | [Threat model](threat-model.md) | learn what is defended, by what, and what is out of scope |
| 2 | [Bring your own key](byok.md) | see whose upstream keys SerpFlow holds, how one is chosen for a request, and what happens without one |
| 3 | [Upstream credentials](credentials.md) | follow a stored SerpApi or Groq key through encryption, decryption, rotation and revocation |
| 4 | [API keys](api-keys.md) | understand the key that calls SerpFlow: format, hashing, roles, rotation and service sessions |
| 5 | [Secrets](secrets.md) | find every deployment secret, what a leak of each costs, how to rotate it, and what to check before going live |

## Questions this section answers

| If you want to know | Go to |
| --- | --- |
| How is one organization kept out of another's data? | [Threat model: cross-tenant data access](threat-model.md#cross-tenant-data-access) |
| What does an attacker get from a database dump? | [Threat model: credential theft from the database](threat-model.md#credential-theft-from-the-database) |
| What stops a leaked key or a looping agent from burning the SerpApi quota? | [Threat model: spend abuse](threat-model.md#spend-abuse) |
| What does SerpFlow deliberately not defend against? | [Threat model: out of scope](threat-model.md#out-of-scope) |
| What works with no SerpApi key, or no Groq key? | [Bring your own key: what happens without each key](byok.md#what-happens-without-each-key) |
| Does a request use the project's key or the organization default? | [Bring your own key: how a key is chosen](byok.md#how-a-key-is-chosen-for-a-request) |
| Can the instance spend on a key no organization brought? | [Bring your own key: the self-hosting exception](byok.md#the-self-hosting-exception) |
| Where is a stored upstream key decrypted? | [Upstream credentials: where it is decrypted](credentials.md#where-it-is-decrypted) |
| Can any endpoint return a key I stored? | [Upstream credentials: never in a response](credentials.md#never-in-a-response) |
| How are keys kept out of the logs? | [Upstream credentials: never in a log](credentials.md#never-in-a-log) |
| What happens to the old credential after a rotation? | [Upstream credentials: validation and revocation](credentials.md#validation-and-revocation) |
| Why are API keys HMAC-hashed rather than Argon2-hashed? | [API keys: hashing](api-keys.md#hashing-hmac-sha256-not-argon2) |
| Which role can do what, and can I define my own? | [API keys: roles](api-keys.md#roles) |
| How is an MCP agent's spend capped? | [API keys: service principal sessions](api-keys.md#service-principal-sessions) |
| What breaks when I rotate the pepper, the KEK or the JWT secret? | [Secrets: rotation](secrets.md#rotation) |
| What must change before a deployment goes live? | [Secrets: production checklist](secrets.md#production-checklist) |

### Known gaps

**Residual risks the pages state plainly**, each with its workaround where it is documented:

- **The cache does not separate modes:** a mock or replayed payload can be served to a `live` run in the same partition, and the response still says `LIVE`. Keep `test` keys in their own project: [threat model: replay or mock data mistaken for live](threat-model.md#replay-or-mock-data-mistaken-for-live)
- **`/metrics` is unauthenticated**, and its labels name organizations, projects and per-engine spend. Block it at the edge: [threat model: exposed surfaces](threat-model.md#exposed-surfaces)
- **Recorded client addresses can be spoofed** with `TRUSTED_PROXY_HOPS=0`, or a header shorter than the configured hops. Treat them as hints, not evidence: [threat model: exposed surfaces](threat-model.md#exposed-surfaces)
- **Rotating an API key never revokes the old one:** it keeps authenticating after the grace window until it is deleted: [API keys: rotation](api-keys.md#rotation)
- **A superuser or the tables' owner bypasses row-level security**, which is the local default: [threat model: cross-tenant data access](threat-model.md#cross-tenant-data-access), [secrets: production checklist](secrets.md#production-checklist)
- **The session cap is checked only when `SERPFLOW_MCP_SESSION` is set**; without it the key's budget is the only cumulative limit: [API keys: service principal sessions](api-keys.md#service-principal-sessions)
- **The high-PII retention deadline is recorded, not enforced:** nothing deletes a run when it passes: [threat model: personal data in cached payloads](threat-model.md#personal-data-in-cached-payloads)

## Where this section meets the others

| Section | The connection |
| --- | --- |
| [Product](../product/README.md) | a `test` key's absolute precedence over the mode is a security rule as much as a product one: [execution modes: who chooses](../product/execution-modes.md#who-chooses-and-precedence); choosing a billable mode per request needs its own [permission](../product/execution-modes.md#permission) |
| [Deployment](../deployment/README.md) | the hardening these pages assume: [generate secrets](../deployment/deployment-guide.md#3-generate-secrets), [make row-level security bind](../deployment/deployment-guide.md#8-make-row-level-security-bind), [keep `/metrics` off the public origin](../deployment/deployment-guide.md#9-put-tls-in-front), and [production: before anything else](../deployment/production.md#before-anything-else) |
| [Architecture](../architecture/README.md) | the executor is where a search decrypts its SerpApi key and checks every budget: [the credential boundary](../architecture/executor.md#the-credential-boundary), [budget enforcement](../architecture/executor.md#budget-enforcement); the cache key ignores mode: [execution mode is not part of the key](../architecture/caching.md#execution-mode-is-not-part-of-the-key) |
| [API](../api/README.md) | how a request presents a key or a token: [authentication](../api/overview.md#authentication); the key, member, role and credential endpoints: [identity and access](../api/overview.md#identity-and-access); why the stream takes `?access_token=`: [streaming: authentication](../api/streaming.md#authentication) |
| [SDKs](../sdks/README.md) | the MCP server runs inside the trust boundary and needs the deployment's secrets: [MCP: how it runs](../sdks/mcp.md#how-it-runs), [configuration](../sdks/mcp.md#configuration); its session cap: [sessions and budgets](../sdks/mcp.md#sessions-and-budgets) |
| [Database](../database/README.md) | the database half of tenant isolation and the append-only audit log: [row-level security](../database/rls.md#how-it-works), [the audit log](../database/rls.md#the-audit-log); the rows these pages protect: [`upstream_credentials`](../database/schema.md#upstream_credentials), [`api_keys`](../database/schema.md#api_keys) |
| [Operations](../operations/README.md) | the redaction filter on every log handler: [observability: logging](../operations/observability.md#logging); why the demo seed is refused in production: [bootstrap: an environment refusal](../operations/bootstrap.md#3-an-environment-refusal); rate limiting failing open: [Redis: why none of it is authoritative](../operations/redis.md#why-none-of-it-is-authoritative); key and credential failures: [troubleshooting: authentication](../operations/troubleshooting.md#authentication) |
| [Decisions](../adr/README.md) | [ADR 0003](../adr/0003-envelope-encryption.md) and [ADR 0006](../adr/0006-rls-plus-application-guards.md) are this section's own, and the threat model leans on [ADR 0002](../adr/0002-deterministic-semantic-guard.md) and [ADR 0005](../adr/0005-test-key-mode-precedence.md): [how they fit together](../adr/README.md#how-they-fit-together) |

## Decisions behind it

- [ADR 0002](../adr/0002-deterministic-semantic-guard.md): a deterministic entity and numeral guard, independent of the cosine score, so a near neighbour is not served as the answer
- [ADR 0003](../adr/0003-envelope-encryption.md): a per-credential AES-256-GCM data key wrapped by a KEK, so rotating the KEK re-wraps keys, not data
- [ADR 0005](../adr/0005-test-key-mode-precedence.md): a `test` key always means mock data, whatever the configuration says
- [ADR 0006](../adr/0006-rls-plus-application-guards.md): tenant isolation enforced twice, in the application and in PostgreSQL

## Related

- [Docs index](../README.md): every section, and the end-to-end reading order
- [Glossary](../product/glossary.md): every term in these pages, defined
- [Database](../database/README.md): the previous section, where row-level security and the audit log live
- [Operations](../operations/README.md): the next section, running the instance these pages secure
- [Security policy](../../SECURITY.md): who maintains SerpFlow, how to report a problem, and which versions get fixes
- [Troubleshooting: authentication](../operations/troubleshooting.md#authentication): `INVALID_API_KEY`, a revoked key that still works, `NO_UPSTREAM_CREDENTIAL`
- [Deployment guide: pre-launch checklist](../deployment/deployment-guide.md#pre-launch-checklist): every hardening step, in one list

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [Row-level security](../database/rls.md) | [Docs index](../README.md) | [Threat model](../security/threat-model.md) |
