# Releasing the SDKs

<p>
  <a href="../README.md#sdks"><img alt="docs: SDKs" src="https://img.shields.io/badge/docs-SDKs-8250DF?logo=readthedocs&logoColor=white"></a>
  <img alt="registries: npm · PyPI" src="https://img.shields.io/badge/registries-npm%20%C2%B7%20PyPI-8250DF">
  <img alt="TypeScript: 5.9" src="https://img.shields.io/badge/TypeScript-5.9-3178C6?logo=typescript&logoColor=white">
  <img alt="Python: 3.13" src="https://img.shields.io/badge/Python-3.13-3776AB?logo=python&logoColor=white">
  <a href="../../sdk/typescript/package.json"><img alt="source: typescript/package.json" src="https://img.shields.io/badge/source-typescript%2Fpackage.json-3fcf8e?logo=github&logoColor=white"></a>
  <img alt="read: 12 min" src="https://img.shields.io/badge/read-12%20min-555555">
</p>

[Docs](../README.md) › [SDKs](../README.md#sdks) › **Releasing the SDKs** · page 28 of 57

- **Two artifacts, two registries:** the TypeScript SDK goes to **npm** as `@serpflow/sdk`, and the Python SDK goes to **PyPI** as `serpflow`
- **Neither has been published yet.** On 2026-10-11 both names were unclaimed: `registry.npmjs.org/@serpflow%2fsdk` and `pypi.org/pypi/serpflow/json` both answered 404
- **Each needs a few one-time fixes before its first release.** They are listed below, and every fix was tried on a scratch copy of the repository first, so they are known to work
- After that, every release is the same [checklist](#every-release), and it can be [automated](#automating-it-with-github-actions)

**On this page:** [first, who runs the server](#first-who-runs-the-server) · [what ships where](#what-ships-where) · [versioning](#versioning) · [first TypeScript release](#before-the-first-typescript-release) · [first Python release](#before-the-first-python-release) · [every release](#every-release) · [automation](#automating-it-with-github-actions) · [pre-releases](#pre-releases) · [a bad release](#fixing-a-bad-release)

## First, who runs the server

**Both SDKs are thin HTTP clients.** A published SDK is only useful to someone who has a SerpFlow API to point it at. Decide which of these you are offering before the first release, because the answer changes the packages.

| | Self-hosted | Hosted by you |
| --- | --- | --- |
| **Who runs the API** | each user, from this repository ([Docker](../deployment/docker.md), [deployment guide](../deployment/deployment-guide.md)) | you, at one public URL |
| **What you operate** | nothing | the API, PostgreSQL, Redis, Kafka, TLS, backups, sign-ups, uptime and abuse handling |
| **Upstream cost** | none to you | still none: SerpApi and Groq keys are [bring-your-own](../security/byok.md), per organization |
| **SDK default `baseUrl`** | `http://localhost:8000`, as today | **change it to your URL before the first release.** Changing a default later is a major version |
| **`serpflow-mcp`** | works: the user owns the database it connects to | **does not work for your users.** It needs your database and your `API_KEY_PEPPER`. Offer them a remote MCP endpoint you host, or rewrite it as an HTTP client of the API |
| **CLI** | works | works for the HTTP commands; `catalog` and `benchmark` run locally anyway |

- **Self-hosted is what the code is built for today**, and it needs no infrastructure from you. The SDKs are then client libraries for software people run themselves
- **Publishing the SDKs commits you to neither.** But a hosted offering needs its URL baked into the defaults first, and its own [production deployment](../deployment/production.md)

## What ships where

| Artifact | Registry | Name | Built from | Version set in | Git tag |
| --- | --- | --- | --- | --- | --- |
| TypeScript SDK | npm | `@serpflow/sdk` | [`sdk/typescript/`](../../sdk/typescript/package.json) | `version` in `package.json` | `sdk-typescript-vX.Y.Z` |
| Python SDK, CLI, MCP server | PyPI | `serpflow` | [`backend/`](../../backend/pyproject.toml) | `version` in `pyproject.toml` **and** `__version__` in [`app/__init__.py`](../../backend/app/__init__.py) | `vX.Y.Z`, the existing platform tags |

- **The tags already in use are `v0.1.0` and `v1.0.0`**, on the whole platform. The Python distribution is the backend package, so it shares them
- **The TypeScript SDK versions on its own**, so it gets a prefixed tag that cannot be mistaken for a platform release
- **If you split the Python SDK out** ([option B](#option-b-recommended-a-standalone-sdk-package)), give it its own prefix too: `sdk-python-vX.Y.Z`

## Versioning

**[Semantic Versioning](https://semver.org/), per artifact.** What counts as what, for an SDK:

| Bump | When | Examples |
| --- | --- | --- |
| **Major** | code that worked stops working | a method, field, export or option removed or renamed; a default changed (base URL, timeout); a higher minimum runtime |
| **Minor** | new things, nothing broken | a new method, a new optional field on `PlanView`, a new option |
| **Patch** | fixes only | stream parsing, an error mapped wrongly, documentation in the package |

- **Every SDK release targets `/v1` of the API.** A server release that only adds response fields needs no SDK release: both SDKs keep the whole payload in `raw`
- **When an SDK release needs a new server feature, release the server first**, and say which server version it needs in the changelog
- **A version number can never be reused** on either registry, even after a deletion. Getting it wrong costs a number, so check before publishing

## Before the first TypeScript release

**1. Own the scope.** `@serpflow/sdk` can only be published by a member of an npm organization called `serpflow`.

- Create it at npmjs.com → **Add organization**. Public packages are free
- **Or publish under a scope you already own**, such as your user name, and change `name` in `package.json`. Decide before the first publish: a rename later is a new package, and users must change their imports

**2. Build before packing.** Today `npm publish` would ship a package with no code in it.

- **`dist/` is not committed** (`.gitignore` excludes it), and nothing builds it on publish
- **Proof:** `npm pack --dry-run` in `sdk/typescript` today lists two files, `README.md` and `package.json`
- **Fix:** a `prepack` script. It runs before both `npm pack` and `npm publish`

**3. Add the metadata a public package needs.** The whole change to [`package.json`](../../sdk/typescript/package.json):

```jsonc
{
  "scripts": {
    "build": "tsc -p tsconfig.json",
    "typecheck": "tsc --noEmit",
    "prepack": "npm run build"                       // new: dist/ is built on pack and publish
  },
  "repository": {                                    // new: npm provenance checks this matches the repo
    "type": "git",
    "url": "git+https://github.com/Madhur-Prakash/SerpFlow.git",
    "directory": "sdk/typescript"
  },
  "homepage": "https://github.com/Madhur-Prakash/SerpFlow/tree/main/sdk/typescript#readme",
  "bugs": { "url": "https://github.com/Madhur-Prakash/SerpFlow/issues" },
  "engines": { "node": ">=18" },                     // new: what the README already promises
  "sideEffects": false,                              // new: lets bundlers tree-shake it
  "publishConfig": { "access": "public" }            // new: scoped packages are private by default
}
```

**4. Ship the licence.** Copy the root `LICENSE` into `sdk/typescript/`. npm always includes a `LICENSE` file at the package root.

**5. Commit a lockfile.** Run `npm install` in `sdk/typescript` and commit the `package-lock.json` it writes, so CI can use `npm ci` and builds with the same compiler every time.

**6. Check the tarball.** With the changes above, on a scratch copy:

```
$ npm pack --dry-run
npm notice Tarball Contents
npm notice 11.6kB LICENSE
npm notice 4.0kB README.md
npm notice 4.6kB dist/index.d.ts
npm notice 10.1kB dist/index.js
npm notice 1.1kB package.json
npm notice package size: 9.7 kB
npm notice total files: 5
```

- **That tarball was then installed into an empty ESM project and exercised:** the named and default exports, the missing-key error, a custom `fetch`, and the error mapping with `code`, `status`, `requestId` and `remedy` all behaved as [documented](typescript.md). `require()` fails with `ERR_PACKAGE_PATH_NOT_EXPORTED`, also as documented
- **The README is already npm-ready.** npmjs.com shows [`sdk/typescript/README.md`](../../sdk/typescript/README.md), so its links are absolute GitHub URLs; relative ones would break there

## Before the first Python release

**First, one decision: what `pip install serpflow` should give people.** The SDK module needs only `httpx`. The package it lives in today needs much more.

### Option A: publish the backend package as it is

`pip install serpflow` would install the SDK, the `serpflow` CLI and `serpflow-mcp` together.

**One fix is required.** The wheel does not contain `serpflow.py`, so `from serpflow import SerpFlow` fails after a normal install.

- **Proof:** `uv build` in `backend/` today produces a 126-file wheel with `app/` and no `serpflow.py`. The editable install only works because it puts `backend/` itself on `sys.path`
- **Fix**, in [`backend/pyproject.toml`](../../backend/pyproject.toml). Tried on a scratch copy: the rebuilt wheel contains `serpflow.py`

```toml
[tool.hatch.build.targets.wheel.force-include]
"serpflow.py" = "serpflow.py"
```

**What option A costs the people who install it:**

- **34 direct runtime dependencies** for an HTTP client: FastAPI, SQLAlchemy, psycopg, aiokafka, boto3, NumPy, the Google API client, OpenTelemetry and the rest
- **Python 3.13 or later**, the backend's floor
- **A top-level package called `app`** in their `site-packages`. Any other distribution, or the user's own project, with a package named `app` collides with it
- **No migrations in the wheel.** `alembic/` is not packaged, so `serpflow-mcp` from PyPI still needs a database migrated from a checkout or the container
- **The PyPI page would show [`backend/README.md`](../../backend/README.md)**, whose relative links break on pypi.org

### Option B, recommended: a standalone SDK package

**Move the SDK into its own distribution called `serpflow`**, beside the TypeScript one. The module imports only the standard library and `httpx`, so this is a file move, not a rewrite.

```
sdk/python/
├── LICENSE              copy of the root LICENSE
├── README.md            npm-style: absolute links only
├── pyproject.toml       below
└── src/serpflow/
    ├── __init__.py      moved from backend/app/sdk/__init__.py, unchanged
    └── py.typed         empty: tells type checkers the package is typed
```

```toml
[project]
name = "serpflow"
version = "1.0.0"
description = "Python SDK for SerpFlow, a search control plane for SerpApi"
readme = "README.md"
requires-python = ">=3.10"                 # dataclass(slots=True) is 3.10+
license = "Apache-2.0"
license-files = ["LICENSE"]
authors = [{ name = "SerpFlow Contributors" }]
keywords = ["serpapi", "search", "sdk", "cache", "planner"]
classifiers = [
    "Development Status :: 5 - Production/Stable",
    "Intended Audience :: Developers",
    "Programming Language :: Python :: 3",
    "Typing :: Typed",
]
dependencies = ["httpx>=0.28.1"]

[project.urls]
Homepage = "https://github.com/Madhur-Prakash/SerpFlow"
Documentation = "https://github.com/Madhur-Prakash/SerpFlow/blob/main/docs/sdks/python.md"
Issues = "https://github.com/Madhur-Prakash/SerpFlow/issues"

[build-system]
requires = ["hatchling>=1.27"]             # 1.27+ for the SPDX licence string
build-backend = "hatchling.build"
```

- **Tried on a scratch copy:** it builds a wheel and an sdist, and a clean Python 3.13 venv ends up with eight packages in all (`serpflow`, `httpx` and its six dependencies). The import, the missing-key `ValueError` and the error mapping all work. It also imports and runs on Python 3.10
- **Then, in the backend:**
  - rename the backend project, for example to `serpflow-server`, because two distributions cannot both be `serpflow`. Update `test_license_is_apache_2_0` in [`tests/unit/test_surfaces.py`](../../backend/tests/unit/test_surfaces.py), which asserts the name
  - delete [`backend/serpflow.py`](../../backend/serpflow.py), and make [`app/sdk/__init__.py`](../../backend/app/sdk/__init__.py) a one-line re-export of the installed package, so existing `app.sdk` imports keep working
  - add the SDK to the backend's dev install: `uv pip install --python backend/.venv -e sdk/python`, and to `make install-backend`
  - keep the CLI and MCP server where they are. Publish the backend later, if ever, once `app` is renamed to something unique
- **Tag it `sdk-python-vX.Y.Z`**, and version it on its own like the TypeScript SDK

### Either way

- **Create the PyPI account with 2FA**, and a TestPyPI account: they are separate sites with separate logins
- **Prefer [trusted publishing](#automating-it-with-github-actions)** to API tokens. If you use a token for the first upload, scope it to the project afterwards, or delete it

## Every release

**1. Choose the number**, using the [versioning](#versioning) table.

**2. Write the changelog.** In [`CHANGELOG.md`](../../CHANGELOG.md), move the relevant `[Unreleased]` entries under a new heading and add the compare link at the bottom. Name the artifact in the heading when it is not the platform:

```markdown
## [@serpflow/sdk 1.0.1] - 2026-10-20
```

**3. Bump the version.**

```bash
# TypeScript
cd sdk/typescript && npm version 1.0.1 --no-git-tag-version

# Python, option A: both places, or `serpflow version` and /readyz disagree with PyPI
#   backend/pyproject.toml   version = "1.0.1"
#   backend/app/__init__.py  __version__ = "1.0.1"
grep -n '^version' backend/pyproject.toml; grep -n '__version__ =' backend/app/__init__.py
```

**4. Verify.**

```bash
make test-unit                                   # includes the SDK, CLI and MCP surface tests
make docs-check                                  # every link and cited path resolves
(cd sdk/typescript && npm ci && npm run typecheck)
```

**5. Build the artifacts.**

```bash
(cd sdk/typescript && npm pack)                  # prepack builds dist/; writes serpflow-sdk-1.0.1.tgz
(cd backend && uv build --out-dir dist)          # .whl and .tar.gz; option B: in sdk/python
```

- **Look inside them.** `npm pack --dry-run` lists the tarball. For the wheel: `python -m zipfile -l backend/dist/serpflow-1.0.1-py3-none-any.whl`

**6. Smoke-test what you built**, in a clean environment, against a local stack (`make up upgrade seed dev`) and a `sf_test_...` key.

```bash
# Python
uv venv /tmp/sf-smoke --python 3.13
uv pip install --python /tmp/sf-smoke backend/dist/serpflow-1.0.1-py3-none-any.whl
SERPFLOW_API_KEY=sf_test_... /tmp/sf-smoke/bin/python -c \
  "from serpflow import SerpFlow; print(SerpFlow().route('bakeries in Koramangala').engines)"

# TypeScript
mkdir /tmp/sf-ts && cd /tmp/sf-ts && npm init -y && npm pkg set type=module
npm install /path/to/SerpFlow/sdk/typescript/serpflow-sdk-1.0.1.tgz
SERPFLOW_API_KEY=sf_test_... node --input-type=module -e \
  'import { SerpFlow } from "@serpflow/sdk";
   const c = new SerpFlow({ apiKey: process.env.SERPFLOW_API_KEY });
   console.log((await c.route("bakeries in Koramangala")).engines);'
```

- On Windows, the venv's interpreter is `\tmp\sf-smoke\Scripts\python.exe`

**7. Commit and tag.** The existing convention is `chore(release): ...`.

```bash
git add -A && git commit -m "chore(release): @serpflow/sdk 1.0.1"
git tag -a sdk-typescript-v1.0.1 -m "@serpflow/sdk 1.0.1"
git push origin main --follow-tags
```

**8. Publish**, by hand or from [CI](#automating-it-with-github-actions).

```bash
# npm: prompts for your 2FA code
npm login
cd sdk/typescript && npm publish                 # prepack builds; publishConfig makes it public

# PyPI: TestPyPI first. Tokens from the environment, never on the command line
UV_PUBLISH_TOKEN=pypi-... uv publish --publish-url https://test.pypi.org/legacy/ backend/dist/*
python -m pip install --index-url https://test.pypi.org/simple/ \
  --extra-index-url https://pypi.org/simple/ "serpflow==1.0.1"
UV_PUBLISH_TOKEN=pypi-... uv publish backend/dist/*
```

- **Install from TestPyPI with pip, as above, not uv.** pip merges the two indexes; uv prefers the first index that has a package, and TestPyPI carries stray copies of common dependencies

**9. Make a GitHub release** from the tag, with the changelog entry as its notes. Attaching the built files is optional.

```bash
gh release create sdk-typescript-v1.0.1 sdk/typescript/serpflow-sdk-1.0.1.tgz \
  --title "@serpflow/sdk 1.0.1" --notes "..."
```

**10. Check it landed.**

```bash
npm view @serpflow/sdk version dist-tags
curl -s https://pypi.org/pypi/serpflow/json | python -c "import json,sys; print(json.load(sys.stdin)['info']['version'])"
```

- **Then install from the registry** in a clean environment, and repeat step 6 against it

**After the very first release**, update the install sections that say the SDKs are not published yet: [SDKs and tools](overview.md), [Python SDK](python.md#install), [TypeScript SDK](typescript.md#install) and [`sdk/README.md`](../../sdk/README.md).

## Automating it with GitHub Actions

- **The repository has no workflows yet.** These two publish on a tag push, with **trusted publishing**: the registry trusts this repository's workflow through OpenID Connect, so no long-lived token is stored anywhere
- **Pin each action to its current major version** when you add them

**Set up the trust once:**

- **PyPI:** your account → **Publishing** → add a **pending publisher**: owner `Madhur-Prakash`, repository `SerpFlow`, workflow `release-python.yml`, environment `pypi`. A pending publisher works before the project exists, so even the first release can come from CI
- **npm:** the package's **Settings** → **Trusted publishing** → GitHub Actions, with the same owner, repository and workflow file `release-typescript.yml`. It needs npm 11.5.1 or later in the job. **npm attaches it to an existing package**, so do the first publish by hand with step 8
- **On GitHub:** create the environments `pypi` and `npm` under **Settings → Environments**, and add yourself as a required reviewer, so a pushed tag waits for your approval before anything is published

**`.github/workflows/release-typescript.yml`**

```yaml
name: release-typescript
on:
  push:
    tags: ["sdk-typescript-v*"]

permissions:
  contents: read
  id-token: write                # OIDC: trusted publishing, and provenance

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: npm
    defaults:
      run:
        working-directory: sdk/typescript
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          registry-url: https://registry.npmjs.org
      - run: npm install -g npm@latest          # trusted publishing needs 11.5.1+
      - name: The tag matches package.json
        run: test "sdk-typescript-v$(node -p 'require("./package.json").version')" = "$GITHUB_REF_NAME"
      - run: npm ci
      - run: npm run typecheck
      - run: npm publish                        # prepack builds; provenance is automatic
```

**`.github/workflows/release-python.yml`** (option A; for option B, point `working-directory` and the artifact path at the SDK's own directory, and use the tag `sdk-python-v*`)

```yaml
name: release-python
on:
  push:
    tags: ["v*"]

permissions:
  contents: read

jobs:
  build:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - name: The tag matches pyproject.toml and __version__
        run: |
          v=$(grep -m1 '^version' pyproject.toml | cut -d'"' -f2)
          test "v$v" = "$GITHUB_REF_NAME"
          grep -q "__version__ = \"$v\"" app/__init__.py
      - run: uv build --out-dir dist
      - uses: actions/upload-artifact@v4
        with:
          name: dist
          path: backend/dist/

  publish:
    needs: build
    runs-on: ubuntu-latest
    environment: pypi
    permissions:
      id-token: write            # OIDC: trusted publishing
    steps:
      - uses: actions/download-artifact@v4
        with:
          name: dist
          path: dist/
      - uses: pypa/gh-action-pypi-publish@release/v1
```

- **Building and publishing are separate jobs** on purpose: the job that holds the publishing identity runs no project code
- **Run the test suite in your normal CI before tagging.** These workflows only check the version and build

## Pre-releases

| | npm | PyPI |
| --- | --- | --- |
| Version | `1.1.0-rc.1` | `1.1.0rc1` ([PEP 440](https://peps.python.org/pep-0440/)) |
| Publish | `npm publish --tag next`, **never** onto `latest` | as usual |
| Installed by default | no: only with `@next` or the exact version | no: only with `--pre` or the exact version |
| Tag | `sdk-typescript-v1.1.0-rc.1` | `v1.1.0rc1` |

## Fixing a bad release

**Publish a fixed patch release.** Then, so nobody new picks up the broken one:

| | npm | PyPI |
| --- | --- | --- |
| Hide it from new installs | `npm deprecate @serpflow/sdk@1.0.1 "Broken stream parsing. Use 1.0.2."` | **yank it**: project → **Manage** → **Releases** → **Options** → **Yank**. Pinned installs still work |
| Move the default back | `npm dist-tag add @serpflow/sdk@1.0.0 latest` | not needed: a yanked release is skipped |
| Delete it | `npm unpublish @serpflow/sdk@1.0.1`, only within 72 hours of publishing | possible, but prefer a yank |
| Reuse the number | **never** | **never** |

- **Say what happened** in the changelog entry of the fix, and on the GitHub release of the bad version

## Related

- [SDKs and tools](overview.md): what each surface is, and which version each is at
- [Python SDK](python.md#install): installing it today, before it is on PyPI
- [TypeScript SDK](typescript.md#building-from-source): building and packing it from source
- [Changelog](../../CHANGELOG.md): where every release is recorded
- [Contributing](../../CONTRIBUTING.md): the bar a change has to meet before it ships

---

| ← Previous | Index | Next → |
| :--- | :---: | ---: |
| [MCP server](../sdks/mcp.md) | [Docs index](../README.md) | [Database schema](../database/schema.md) |
