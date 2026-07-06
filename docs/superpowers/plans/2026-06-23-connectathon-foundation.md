# Connectathon-Ready Foundation + Use Case 1 Graph Engine — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a working, demoable SMART on FHIR app — EHR/standalone launch, BFF auth, enroll a patient into a `ResearchStudy`, and resolve/track that subject's schedule against the Vulcan SoA V2 `soaTimepoint`/`soaTransition` graph at Use Case 1 complexity (linear progression + early-termination branch) — against Aidbox R6 ballot, ready to run against either the local dev instance or the HL7 connectathon's public instance by switching one env file.

**Architecture:** React/Vite SPA → FastAPI backend-for-frontend (the SMART confidential client, holds tokens server-side keyed to an opaque session cookie) → Aidbox (FHIR R6 ballot). The SoA graph engine (`soa_engine`) is a pure, FHIR-server-agnostic module: PlanDefinition JSON in, computed schedule-state out. Subject progress is derived on every read from existing `Encounter` instances tagged back to their originating `PlanDefinition.action.id` — there is no separate state store.

**Tech Stack:** Python 3.11+, FastAPI, httpx, pydantic-settings, pytest/pytest-asyncio/respx. React 18, Vite, TypeScript, react-router-dom, vitest/@testing-library/react, Playwright. Target FHIR server: Aidbox, FHIR R6 ballot (`6.0.0-ballot3`), raw JSON dicts throughout (no typed FHIR resource models — R6 isn't covered by `fhir.resources`).

## Global Constraints

- Target FHIR server is Aidbox on FHIR R6 ballot (`6.0.0-ballot3`), matching the Vulcan SoA V2 IG exactly. No code branches on which Aidbox instance (local vs connectathon) — only configuration differs.
- All FHIR resources are plain JSON `dict`s. Do not introduce typed FHIR resource model libraries.
- The React SPA never receives or holds a FHIR access token. It talks only to the backend's JSON API via an `HttpOnly` session cookie.
- Target FHIR server base URL and OAuth endpoints/credentials are read from environment/`.env` files only (`FHIR_BASE_URL`, `OAUTH_AUTHORIZE_URL`, `OAUTH_TOKEN_URL`, `SMART_CLIENT_ID`, `SMART_CLIENT_SECRET`, `REDIRECT_URI`) — never hardcoded in `auth` or `fhir_client`.
- Writes that must not duplicate on retry (enrollment) use conditional-create (search-then-create). Updates use `If-Match`/`ETag` for concurrency safety.
- The engine never auto-selects when more than one outgoing transition is valid with no automatic signal — this is always surfaced as an ambiguous/decision-support result, never resolved silently.
- Condition evaluation errors or unrecognized condition keys fail closed (treated as not-satisfied) and are logged — never raise and never silently pass.
- Use Case 2 (branching arms), Use Case 3 (treatment cycles), FHIRPath `applicability` conditions, and unscheduled-visit insertion are explicitly out of scope for this plan (Plan 2+).
- Protocol-graph validation diagnostics (dangling `soaTargetId`, missing `soaTimepoint`, unreachable/cyclic-without-exit nodes) are deferred to Plan 2+: `parse_protocol_graph` (Task 6) assumes a well-formed input graph. This plan's only graph is the IG's own Use Case 1 fixture, manually confirmed loadable in Task 5's spike — acceptable for a connectathon-timeline V1, not for arbitrary future protocols.
- Friendly "this subject changed, please refresh" messaging on a concurrent-edit conflict is deferred to Plan 2+: writes already send `If-Match` (Task 4, Task 11) so a stale write fails closed via `httpx.HTTPStatusError` rather than silently overwriting, but no route or view yet translates that into the spec's specific friendly copy.

---

## File Structure

**Backend** (`backend/`):

```
backend/
  pyproject.toml
  .env.local.example
  .env.connectathon.example
  src/vulcan_soa/
    __init__.py
    config.py              # Settings (pydantic-settings)
    store.py                # InMemoryStore[T] generic
    fhir_client.py           # FhirClient: read/search/create/update/conditional_create/put_by_id
    auth.py                  # Session, PendingLaunch, PKCE, authorize-URL builder, token exchange, fhirContext parsing
    soa_engine/
      __init__.py
      graph.py               # parse_protocol_graph -> ProtocolGraph
      conditions.py           # evaluate_condition (text/x-soa-expressionplain interpreter)
      engine.py               # resolve_schedule_state
    scheduling.py             # tag_for, materialize_visit, load_subject_context
    enrollment.py             # enroll()
    tracking.py               # withdraw_subject(), complete_visit()
    api/
      __init__.py
      models.py               # EnrollRequest, CompleteVisitRequest
      deps.py                  # get_settings, get_session_store, get_pending_launch_store, get_current_session, get_fhir_client
      launch.py                # /launch, /launch/standalone, /callback
      context.py               # /api/context
      research_studies.py      # /api/research-studies, /enroll
      research_subjects.py     # /api/research-subjects/{id}/schedule, /visits/{actionId}/complete, /withdraw
      app.py                   # create_app(), module-level app = create_app()
  scripts/
    load_fixtures.py          # generic directory -> Aidbox loader (used for IG output/ and our own fixtures)
    generate_client_registration.py  # Client + AccessPolicy registration from Settings (print or --apply)
  fixtures/
    research_study_uc1.json    # our own test ResearchStudy pointing at the IG's Use Case 1 PlanDefinition
    patient_demo.json
  tests/
    conftest.py
    fixtures/
      plan_definition_uc1.json # copy of the IG's dynamic-visit-schedule-exit-example-PlanDefinition
    test_config.py
    test_store.py
    test_fhir_client.py
    soa_engine/
      test_graph.py
      test_conditions.py
      test_engine.py
    test_scheduling.py
    test_enrollment.py
    test_tracking.py
    test_auth.py
    api/
      test_launch.py
      test_context.py
      test_research_studies.py
      test_research_subjects.py
    test_golden_path_integration.py   # requires a real local Aidbox
```

**Frontend** (`frontend/`):

```
frontend/
  package.json
  vite.config.ts
  tsconfig.json
  index.html
  playwright.config.ts
  .gitignore
  src/
    main.tsx
    App.tsx
    App.test.tsx
    routes.tsx
    routes.test.tsx
    setupTests.ts
    api/
      client.ts
      types.ts
      client.test.ts
    launch/
      LaunchPending.tsx
      LaunchError.tsx
      LaunchError.test.tsx
    views/
      StudyWorklist/
        StudyWorklist.tsx
        StudyWorklist.test.tsx
      Enroll/
        Enroll.tsx
        Enroll.test.tsx
      SubjectDashboard/
        SubjectDashboard.tsx
        SubjectDashboard.test.tsx
  e2e/
    golden-path.spec.ts
    .auth/                 # gitignored; holds the one-time Playwright login bootstrap (Task 24)
```

---

## Task 1: Backend project scaffold

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/src/vulcan_soa/__init__.py`
- Test: `backend/tests/test_smoke.py`

**Interfaces:**
- Produces: an importable `vulcan_soa` package and a working `pytest` setup for every later backend task.

- [ ] **Step 1: Create the package files**

`backend/src/vulcan_soa/__init__.py`:
```python
```

(empty file — just marks the package)

- [ ] **Step 2: Create `pyproject.toml`**

`backend/pyproject.toml`:
```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "vulcan-soa"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "httpx>=0.27",
  "pydantic-settings>=2.5",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3",
  "pytest-asyncio>=0.24",
  "respx>=0.21",
]

[tool.hatch.build.targets.wheel]
packages = ["src/vulcan_soa"]

[tool.pytest.ini_options]
pythonpath = ["src"]
asyncio_mode = "auto"
```

- [ ] **Step 3: Write the smoke test**

`backend/tests/test_smoke.py`:
```python
import vulcan_soa


def test_package_importable():
    assert vulcan_soa is not None
```

- [ ] **Step 4: Install and run**

Run:
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest tests/test_smoke.py -v
```
Expected: `1 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/src/vulcan_soa/__init__.py backend/tests/test_smoke.py
git commit -m "Scaffold backend Python package"
```

---

## Task 2: Configuration module

**Files:**
- Create: `backend/src/vulcan_soa/config.py`
- Create: `backend/.env.local.example`
- Create: `backend/.env.connectathon.example`
- Test: `backend/tests/test_config.py`

**Interfaces:**
- Produces: `Settings` (pydantic-settings `BaseSettings` subclass) with fields `fhir_base_url`, `oauth_authorize_url`, `oauth_token_url`, `smart_client_id`, `smart_client_secret`, `redirect_uri`, `frontend_url`. Every later task that needs config calls `Settings()`.

- [ ] **Step 1: Write the failing test**

`backend/tests/test_config.py`:
```python
import os

import pytest


@pytest.fixture
def env_file(tmp_path, monkeypatch):
    path = tmp_path / ".env.test"
    path.write_text(
        "FHIR_BASE_URL=http://localhost:8888/fhir\n"
        "OAUTH_AUTHORIZE_URL=http://localhost:8888/auth/authorize\n"
        "OAUTH_TOKEN_URL=http://localhost:8888/auth/token\n"
        "SMART_CLIENT_ID=test-client\n"
        "SMART_CLIENT_SECRET=test-secret\n"
        "REDIRECT_URI=http://localhost:8000/callback\n"
    )
    monkeypatch.setenv("ENV_FILE", str(path))
    return path


def test_settings_load_from_env_file(env_file):
    # Re-import after setting ENV_FILE so the module-level default re-evaluates.
    import importlib

    import vulcan_soa.config as config_module

    importlib.reload(config_module)
    settings = config_module.Settings()

    assert settings.fhir_base_url == "http://localhost:8888/fhir"
    assert settings.smart_client_id == "test-client"
    assert settings.frontend_url == "http://localhost:5173"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vulcan_soa.config'`

- [ ] **Step 3: Write the implementation**

`backend/src/vulcan_soa/config.py`:
```python
import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.environ.get("ENV_FILE", ".env.local"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    fhir_base_url: str
    oauth_authorize_url: str
    oauth_token_url: str
    smart_client_id: str
    smart_client_secret: str
    redirect_uri: str
    frontend_url: str = "http://localhost:5173"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_config.py -v`
Expected: `1 passed`

- [ ] **Step 5: Create the example env files**

`backend/.env.local.example`:
```
FHIR_BASE_URL=http://localhost:8888/fhir
OAUTH_AUTHORIZE_URL=http://localhost:8888/auth/authorize
OAUTH_TOKEN_URL=http://localhost:8888/auth/token
SMART_CLIENT_ID=vulcan-soa-bff
SMART_CLIENT_SECRET=change-me
REDIRECT_URI=http://localhost:8000/callback
FRONTEND_URL=http://localhost:5173
```

`backend/.env.connectathon.example`:
```
FHIR_BASE_URL=https://xfztpxesfy.edge.aidbox.app/fhir
OAUTH_AUTHORIZE_URL=https://xfztpxesfy.edge.aidbox.app/auth/authorize
OAUTH_TOKEN_URL=https://xfztpxesfy.edge.aidbox.app/auth/token
SMART_CLIENT_ID=vulcan-soa-bff
SMART_CLIENT_SECRET=change-me
REDIRECT_URI=http://localhost:8000/callback
FRONTEND_URL=http://localhost:5173
```

Copy each to its real (gitignored) counterpart before running anything: `cp backend/.env.local.example backend/.env.local` (and same for `.env.connectathon`), then fill in real secrets. Add `backend/.env.local` and `backend/.env.connectathon` to `.gitignore` in Task order — see Step 6.

- [ ] **Step 6: Gitignore the real env files**

Add to the project's root `.gitignore` (read it first, then append):
```
backend/.env.local
backend/.env.connectathon
backend/.venv/
```

- [ ] **Step 7: Commit**

```bash
git add backend/src/vulcan_soa/config.py backend/tests/test_config.py backend/.env.local.example backend/.env.connectathon.example .gitignore
git commit -m "Add environment-driven backend configuration"
```

---

## Task 3: In-memory store

**Files:**
- Create: `backend/src/vulcan_soa/store.py`
- Test: `backend/tests/test_store.py`

**Interfaces:**
- Produces: `InMemoryStore[T]` with `.create(item: T) -> str`, `.get(key: str) -> T | None`, `.pop(key: str) -> T | None`. Used by `auth.py` (sessions, pending launches) and `api/app.py` (attached to `app.state`).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_store.py`:
```python
from vulcan_soa.store import InMemoryStore


def test_create_and_get_roundtrip():
    store: InMemoryStore[str] = InMemoryStore()
    key = store.create("hello")
    assert store.get(key) == "hello"


def test_get_missing_key_returns_none():
    store: InMemoryStore[str] = InMemoryStore()
    assert store.get("nonexistent") is None


def test_pop_removes_item():
    store: InMemoryStore[str] = InMemoryStore()
    key = store.create("hello")
    assert store.pop(key) == "hello"
    assert store.get(key) is None


def test_create_generates_unique_keys():
    store: InMemoryStore[str] = InMemoryStore()
    key1 = store.create("a")
    key2 = store.create("b")
    assert key1 != key2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vulcan_soa.store'`

- [ ] **Step 3: Write the implementation**

`backend/src/vulcan_soa/store.py`:
```python
import secrets
from typing import Generic, TypeVar

T = TypeVar("T")


class InMemoryStore(Generic[T]):
    def __init__(self) -> None:
        self._items: dict[str, T] = {}

    def create(self, item: T) -> str:
        key = secrets.token_urlsafe(32)
        self._items[key] = item
        return key

    def get(self, key: str) -> T | None:
        return self._items.get(key)

    def pop(self, key: str) -> T | None:
        return self._items.pop(key, None)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_store.py -v`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/src/vulcan_soa/store.py backend/tests/test_store.py
git commit -m "Add generic in-memory store for sessions and pending launches"
```

---

## Task 4: FHIR client

**Files:**
- Create: `backend/src/vulcan_soa/fhir_client.py`
- Test: `backend/tests/test_fhir_client.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `FhirClient(base_url: str, *, access_token: str | None = None, basic_auth: tuple[str, str] | None = None, http_client: httpx.AsyncClient | None = None)` with async methods `read(resource_type, resource_id) -> dict`, `search(resource_type, params: dict) -> list[dict]`, `create(resource_type, resource: dict) -> dict`, `update(resource_type, resource_id, resource: dict, if_match: str | None = None) -> dict`, `conditional_create(resource_type, resource: dict, search_params: dict) -> dict`, `put_by_id(resource_type, resource_id, resource: dict) -> dict`, `close() -> None`. Every other backend module depends on this.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_fhir_client.py`:
```python
import httpx
import pytest
import respx

from vulcan_soa.fhir_client import FhirClient


def make_client(respx_mock) -> FhirClient:
    transport = httpx.MockTransport(respx_mock.handler) if False else None
    return FhirClient(base_url="http://aidbox.test/fhir", access_token="tok-123")


def test_requires_access_token_or_basic_auth():
    with pytest.raises(ValueError):
        FhirClient(base_url="http://aidbox.test/fhir")


@respx.mock
async def test_read_sends_bearer_and_returns_json():
    route = respx.get("http://aidbox.test/fhir/Patient/p1").mock(
        return_value=httpx.Response(200, json={"resourceType": "Patient", "id": "p1"})
    )
    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok-123")
    result = await client.read("Patient", "p1")
    await client.close()

    assert result == {"resourceType": "Patient", "id": "p1"}
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok-123"


@respx.mock
async def test_search_extracts_bundle_entries():
    respx.get("http://aidbox.test/fhir/Patient").mock(
        return_value=httpx.Response(
            200,
            json={
                "resourceType": "Bundle",
                "entry": [
                    {"resource": {"resourceType": "Patient", "id": "p1"}},
                    {"resource": {"resourceType": "Patient", "id": "p2"}},
                ],
            },
        )
    )
    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok-123")
    results = await client.search("Patient", {"name": "demo"})
    await client.close()

    assert [r["id"] for r in results] == ["p1", "p2"]


@respx.mock
async def test_search_with_no_entries_returns_empty_list():
    respx.get("http://aidbox.test/fhir/Patient").mock(
        return_value=httpx.Response(200, json={"resourceType": "Bundle"})
    )
    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok-123")
    results = await client.search("Patient", {})
    await client.close()

    assert results == []


@respx.mock
async def test_create_posts_resource():
    route = respx.post("http://aidbox.test/fhir/Patient").mock(
        return_value=httpx.Response(201, json={"resourceType": "Patient", "id": "new-1"})
    )
    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok-123")
    result = await client.create("Patient", {"resourceType": "Patient"})
    await client.close()

    assert result["id"] == "new-1"
    assert route.calls.last.request.content


@respx.mock
async def test_update_sends_if_match_header():
    route = respx.put("http://aidbox.test/fhir/Patient/p1").mock(
        return_value=httpx.Response(200, json={"resourceType": "Patient", "id": "p1"})
    )
    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok-123")
    await client.update("Patient", "p1", {"resourceType": "Patient", "id": "p1"}, if_match="W/\"3\"")
    await client.close()

    assert route.calls.last.request.headers["If-Match"] == 'W/"3"'


@respx.mock
async def test_conditional_create_returns_existing_when_found():
    respx.get("http://aidbox.test/fhir/Patient").mock(
        return_value=httpx.Response(
            200,
            json={
                "resourceType": "Bundle",
                "entry": [{"resource": {"resourceType": "Patient", "id": "existing-1"}}],
            },
        )
    )
    create_route = respx.post("http://aidbox.test/fhir/Patient")
    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok-123")
    result = await client.conditional_create(
        "Patient", {"resourceType": "Patient"}, {"identifier": "x"}
    )
    await client.close()

    assert result["id"] == "existing-1"
    assert not create_route.called


@respx.mock
async def test_conditional_create_creates_when_not_found():
    respx.get("http://aidbox.test/fhir/Patient").mock(
        return_value=httpx.Response(200, json={"resourceType": "Bundle"})
    )
    respx.post("http://aidbox.test/fhir/Patient").mock(
        return_value=httpx.Response(201, json={"resourceType": "Patient", "id": "new-1"})
    )
    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok-123")
    result = await client.conditional_create(
        "Patient", {"resourceType": "Patient"}, {"identifier": "x"}
    )
    await client.close()

    assert result["id"] == "new-1"


@respx.mock
async def test_put_by_id_uses_basic_auth_when_configured():
    route = respx.put("http://aidbox.test/fhir/Patient/p1").mock(
        return_value=httpx.Response(200, json={"resourceType": "Patient", "id": "p1"})
    )
    client = FhirClient(
        base_url="http://aidbox.test/fhir", basic_auth=("client-id", "client-secret")
    )
    await client.put_by_id("Patient", "p1", {"resourceType": "Patient", "id": "p1"})
    await client.close()

    auth_header = route.calls.last.request.headers["Authorization"]
    assert auth_header.startswith("Basic ")


@respx.mock
async def test_raises_on_http_error():
    respx.get("http://aidbox.test/fhir/Patient/missing").mock(return_value=httpx.Response(404))
    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok-123")
    with pytest.raises(httpx.HTTPStatusError):
        await client.read("Patient", "missing")
    await client.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pip install -e ".[dev]" && pytest tests/test_fhir_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vulcan_soa.fhir_client'`

- [ ] **Step 3: Write the implementation**

`backend/src/vulcan_soa/fhir_client.py`:
```python
import httpx

FHIR_JSON = "application/fhir+json"


class FhirClient:
    def __init__(
        self,
        base_url: str,
        *,
        access_token: str | None = None,
        basic_auth: tuple[str, str] | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not access_token and not basic_auth:
            raise ValueError("FhirClient requires either access_token or basic_auth")

        self._base_url = base_url.rstrip("/")
        headers = {"Content-Type": FHIR_JSON, "Accept": FHIR_JSON}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        if http_client is not None:
            self._client = http_client
        else:
            auth = httpx.BasicAuth(*basic_auth) if basic_auth else None
            self._client = httpx.AsyncClient(auth=auth, headers=headers)

    async def read(self, resource_type: str, resource_id: str) -> dict:
        response = await self._client.get(f"{self._base_url}/{resource_type}/{resource_id}")
        response.raise_for_status()
        return response.json()

    async def search(self, resource_type: str, params: dict[str, str]) -> list[dict]:
        response = await self._client.get(f"{self._base_url}/{resource_type}", params=params)
        response.raise_for_status()
        bundle = response.json()
        return [entry["resource"] for entry in bundle.get("entry", [])]

    async def create(self, resource_type: str, resource: dict) -> dict:
        response = await self._client.post(f"{self._base_url}/{resource_type}", json=resource)
        response.raise_for_status()
        return response.json()

    async def update(
        self, resource_type: str, resource_id: str, resource: dict, if_match: str | None = None
    ) -> dict:
        headers = {"If-Match": if_match} if if_match else {}
        response = await self._client.put(
            f"{self._base_url}/{resource_type}/{resource_id}", json=resource, headers=headers
        )
        response.raise_for_status()
        return response.json()

    async def conditional_create(
        self, resource_type: str, resource: dict, search_params: dict[str, str]
    ) -> dict:
        existing = await self.search(resource_type, search_params)
        if existing:
            return existing[0]
        return await self.create(resource_type, resource)

    async def put_by_id(self, resource_type: str, resource_id: str, resource: dict) -> dict:
        response = await self._client.put(
            f"{self._base_url}/{resource_type}/{resource_id}", json=resource
        )
        response.raise_for_status()
        return response.json()

    async def close(self) -> None:
        await self._client.aclose()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_fhir_client.py -v`
Expected: `10 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/src/vulcan_soa/fhir_client.py backend/tests/test_fhir_client.py
git commit -m "Add thin Aidbox REST client using raw FHIR JSON dicts"
```

---

## Task 5: Aidbox fixture loader + R6 spike (do this before any deeper engine work)

This is the urgent risk-reduction task called out in the design spec: confirm Aidbox's R6 ballot support actually accepts the resource shapes this app will read and write, against a **real, running local Aidbox**, before investing in the engine. It produces a generic, idempotent loader (any directory of FHIR-resource JSON files → Aidbox), not a hardcoded file list — this lets the same script load the IG's `output/` directory, our own test fixtures, and (later) the fuller LZZT fixture the user provides, with no code changes.

**Files:**
- Create: `backend/scripts/load_fixtures.py`
- Create: `backend/fixtures/research_study_uc1.json`
- Create: `backend/fixtures/patient_demo.json`
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/test_load_fixtures.py`

**Interfaces:**
- Consumes: `FhirClient.put_by_id` (Task 4), `Settings` (Task 2).
- Produces: `load_directory(client: FhirClient, directory: Path) -> list[tuple[Path, str]]` (returns list of `(path, outcome)` where outcome is `"OK"`, `"SKIP: <reason>"`, or `"FAIL: <reason>"`) and a `main()` CLI entrypoint.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_load_fixtures.py`:
```python
import json

import httpx
import respx

from scripts.load_fixtures import load_directory
from vulcan_soa.fhir_client import FhirClient


def write_json(path, data):
    path.write_text(json.dumps(data))


@respx.mock
async def test_loads_valid_resource(tmp_path):
    write_json(tmp_path / "patient.json", {"resourceType": "Patient", "id": "p1"})
    respx.put("http://aidbox.test/fhir/Patient/p1").mock(
        return_value=httpx.Response(200, json={"resourceType": "Patient", "id": "p1"})
    )
    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok")
    results = await load_directory(client, tmp_path)
    await client.close()

    assert results == [(tmp_path / "patient.json", "OK")]


@respx.mock
async def test_skips_non_dict_json(tmp_path):
    write_json(tmp_path / "list.json", ["not", "a", "resource"])
    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok")
    results = await load_directory(client, tmp_path)
    await client.close()

    assert results[0][1].startswith("SKIP")


@respx.mock
async def test_skips_dict_without_resource_type(tmp_path):
    write_json(tmp_path / "manifest.json", {"some": "manifest", "id": "x"})
    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok")
    results = await load_directory(client, tmp_path)
    await client.close()

    assert results[0][1].startswith("SKIP")


@respx.mock
async def test_skips_invalid_json(tmp_path):
    (tmp_path / "broken.json").write_text("{not valid json")
    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok")
    results = await load_directory(client, tmp_path)
    await client.close()

    assert results[0][1].startswith("SKIP")


@respx.mock
async def test_records_failure_without_stopping(tmp_path):
    write_json(tmp_path / "a_bad.json", {"resourceType": "Patient", "id": "bad"})
    write_json(tmp_path / "b_good.json", {"resourceType": "Patient", "id": "good"})
    respx.put("http://aidbox.test/fhir/Patient/bad").mock(return_value=httpx.Response(422))
    respx.put("http://aidbox.test/fhir/Patient/good").mock(
        return_value=httpx.Response(200, json={"resourceType": "Patient", "id": "good"})
    )
    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok")
    results = await load_directory(client, tmp_path)
    await client.close()

    outcomes = dict((p.name, outcome) for p, outcome in results)
    assert outcomes["a_bad.json"].startswith("FAIL")
    assert outcomes["b_good.json"] == "OK"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_load_fixtures.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts'`

- [ ] **Step 3: Write the implementation**

`backend/scripts/__init__.py`:
```python
```

(empty file — marks the package so `tests/test_load_fixtures.py` can `from scripts.load_fixtures import load_directory`)

`backend/tests/conftest.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

`[tool.pytest.ini_options] pythonpath = ["src"]` (Task 1) only puts `backend/src` on `sys.path`, so `vulcan_soa` is importable but `backend/scripts` is not. Plain `pytest` (every "Run:" command in this plan uses bare `pytest`, not `python -m pytest`) does not add the current working directory either. This `conftest.py` is collected before any test module in `backend/tests/` (and its subdirectories, including `backend/tests/api/`), and adds `backend/` itself to `sys.path` so `from scripts.load_fixtures import load_directory` resolves. Without it, `test_load_fixtures.py` below — and the golden-path integration test in Task 17 — fail with `ModuleNotFoundError: No module named 'scripts'` even after `backend/scripts/load_fixtures.py` exists.

`backend/scripts/load_fixtures.py`:
```python
import argparse
import asyncio
import json
from pathlib import Path

from vulcan_soa.config import Settings
from vulcan_soa.fhir_client import FhirClient


async def load_directory(client: FhirClient, directory: Path) -> list[tuple[Path, str]]:
    results: list[tuple[Path, str]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            resource = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            results.append((path, f"SKIP: invalid JSON ({exc})"))
            continue

        if not isinstance(resource, dict):
            results.append((path, f"SKIP: not a single FHIR resource (got {type(resource).__name__})"))
            continue

        resource_type = resource.get("resourceType")
        resource_id = resource.get("id")
        if not resource_type or not resource_id:
            results.append((path, "SKIP: missing resourceType or id"))
            continue

        try:
            await client.put_by_id(resource_type, resource_id, resource)
            results.append((path, "OK"))
        except Exception as exc:  # noqa: BLE001 - intentionally broad: log and continue loading the rest
            results.append((path, f"FAIL: {exc}"))

    return results


async def main() -> None:
    parser = argparse.ArgumentParser(description="Load FHIR resource JSON files into Aidbox")
    parser.add_argument("directory", type=Path, help="Directory of *.json FHIR resource files")
    args = parser.parse_args()

    settings = Settings()
    client = FhirClient(
        base_url=settings.fhir_base_url,
        basic_auth=(settings.smart_client_id, settings.smart_client_secret),
    )
    try:
        results = await load_directory(client, args.directory)
    finally:
        await client.close()

    for path, outcome in results:
        print(f"{outcome:40s} {path.name}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_load_fixtures.py -v`
Expected: `5 passed`

- [ ] **Step 5: Create our own test fixtures**

The IG repo ships a `ResearchStudy` (`H2Q-MC-LZZT-ResearchStudy`) that points at its own complex, release-constrained protocol — not at the Use Case 1 PlanDefinition this plan's engine targets. We need our own small `ResearchStudy` instance pointing at the IG's Use Case 1 PlanDefinition (`dynamic-visit-schedule-exit-example-PlanDefinition`) so enrollment has something realistic to enroll into. This is test/dev instance data, not new SoA authoring.

`backend/fixtures/research_study_uc1.json`:
```json
{
  "resourceType": "ResearchStudy",
  "id": "uc1-demo-research-study",
  "title": "Use Case 1 Demo Study (Exit Example)",
  "status": "active",
  "protocol": [
    {
      "reference": "PlanDefinition/dynamic-visit-schedule-exit-example-PlanDefinition"
    }
  ]
}
```

`backend/fixtures/patient_demo.json`:
```json
{
  "resourceType": "Patient",
  "id": "uc1-demo-patient",
  "name": [
    {
      "family": "Demo",
      "given": ["UC1"]
    }
  ]
}
```

- [ ] **Step 6: Run the loader against a real local Aidbox**

This is the actual R6 spike. With your local Aidbox running and `backend/.env.local` filled in with real values (base URL + a confidential client id/secret that has FHIR API access):

```bash
cd backend
source .venv/bin/activate
export ENV_FILE=.env.local
python scripts/load_fixtures.py /Users/GLW1/Documents/Devel/hl7/Vulcan-schedule-ig/output
python scripts/load_fixtures.py fixtures
```

Expected: every `StructureDefinition-*.json`, `PlanDefinition-*.json`, `ActivityDefinition-*.json`, `ResearchStudy-*.json`, `Practitioner-*.json`, `Organization-*.json`, and `ImplementationGuide-*.json` file prints `OK`; the handful of IG-publisher manifest/QA files (`canonicals.json`, `codesystem-list.json`, `qa.json`, `valueset-*.json`, etc.) print `SKIP` — confirm this by eye, don't just trust a green test run. Both `fixtures/research_study_uc1.json` and `fixtures/patient_demo.json` print `OK`.

If any genuine resource prints `FAIL`, read the error: Aidbox's R6 ballot support is new, and resource shapes in this IG (especially `ResearchStudy`/`PlanDefinition` with the `soaTimepoint`/`soaTransition` extensions) may not validate cleanly on the first try. This is expected risk, not a bug in this script — note in your task notes which resources failed and why; later tasks build directly on `PlanDefinition-dynamic-visit-schedule-exit-example-PlanDefinition` and `ResearchStudy/uc1-demo-research-study` existing in Aidbox, so those two in particular must succeed before continuing.

- [ ] **Step 7: Confirm Encounter and ResearchSubject writes round-trip**

Still against the real local Aidbox, by hand (e.g. via `httpx` in a Python shell, or `curl` with a bearer token from the Aidbox console), attempt to create one `ResearchSubject` shaped like:
```json
{
  "resourceType": "ResearchSubject",
  "subjectState": {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/research-subject-state", "code": "candidate"}]},
  "study": {"reference": "ResearchStudy/uc1-demo-research-study"},
  "subject": {"reference": "Patient/uc1-demo-patient"}
}
```
and one `Encounter` shaped like:
```json
{
  "resourceType": "Encounter",
  "status": "planned",
  "class": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB"}]}],
  "subject": {"reference": "Patient/uc1-demo-patient"},
  "identifier": [{"system": "urn:vulcan-soa:plan-action", "value": "dynamic-visit-schedule-exit-example-PlanDefinition#0700e721-1f12-4998-89b8-6f4e649b62f7"}]
}
```
If Aidbox rejects either shape, adjust the shape used in Tasks 9/11 below to match what Aidbox's R6 StructureDefinitions actually accept, and note the discrepancy — this is the entire point of doing this spike before writing `scheduling.py`/`tracking.py`.

- [ ] **Step 8: Commit**

```bash
git add backend/scripts/__init__.py backend/scripts/load_fixtures.py backend/fixtures/research_study_uc1.json backend/fixtures/patient_demo.json backend/tests/conftest.py backend/tests/test_load_fixtures.py
git commit -m "Add generic Aidbox fixture loader and confirm R6 spike resource shapes"
```

---

## Task 6: SoA graph parser

Parses a `StudyProtocolSoa`-profiled `PlanDefinition` into a plain DAG: one `VisitNode` per `action` (keyed by `action.id`), each carrying its `soaTimepoint` data and its outgoing `Transition`s (from nested `action.action` entries carrying `soaTransition`). This task uses the IG's own real Use Case 1 fixture (`dynamic-visit-schedule-exit-example-PlanDefinition`) as its test data — copied into this repo so tests don't depend on the external IG repo path.

**Files:**
- Create: `backend/src/vulcan_soa/soa_engine/__init__.py`
- Create: `backend/src/vulcan_soa/soa_engine/graph.py`
- Create: `backend/tests/fixtures/plan_definition_uc1.json`
- Test: `backend/tests/soa_engine/test_graph.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class Transition:
      target_id: str
      transition_type: str          # "FS" or "SS"
      condition_language: str | None
      condition_expression: str | None

  @dataclass(frozen=True)
  class VisitNode:
      action_id: str
      title: str
      transitions: tuple[Transition, ...]

  @dataclass(frozen=True)
  class ProtocolGraph:
      plan_definition_id: str
      nodes: dict[str, VisitNode]   # keyed by action_id
      root_ids: tuple[str, ...]      # top-level action ids, in document order

  def parse_protocol_graph(plan_definition: dict) -> ProtocolGraph: ...
  ```
  Tasks 8, 9, 10, 11 all consume `ProtocolGraph`/`VisitNode`/`Transition` exactly as defined here.

- [ ] **Step 1: Copy the real fixture into this repo**

Copy the file (do not retype it by hand — copy it exactly):
```bash
mkdir -p backend/tests/fixtures
cp "/Users/GLW1/Documents/Devel/hl7/Vulcan-schedule-ig/output/PlanDefinition-dynamic-visit-schedule-exit-example-PlanDefinition.json" \
   backend/tests/fixtures/plan_definition_uc1.json
```

This fixture's graph (for reference while writing the test): `Screening` (id `0700e721-...`) → `Treatment Day 1` (id `a1806239-...`) → either `Day 7` (id `349447c3-...`, unconditional) or `End of Study` (id `dbc35dee-...`, condition `{'withdraw':True, 'operation': '=='}`) → `Day 7` also leads to `Day 15` (id `d0dd287a-...`) or `End of Study`; `End of Study` leads to `Follow Up` (id `76fb46ca-...`, no further transitions).

- [ ] **Step 2: Write the failing test**

`backend/src/vulcan_soa/soa_engine/__init__.py`:
```python
```

(empty file)

`backend/tests/soa_engine/__init__.py`:
```python
```

(empty file)

`backend/tests/soa_engine/test_graph.py`:
```python
import json
from pathlib import Path

import pytest

from vulcan_soa.soa_engine.graph import parse_protocol_graph

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "plan_definition_uc1.json"

SCREENING_ID = "0700e721-1f12-4998-89b8-6f4e649b62f7"
TREATMENT_DAY1_ID = "a1806239-54f3-4762-af3f-edb9d80d29dc"
DAY7_ID = "349447c3-8ad4-4034-8c31-c3d96dcc5f9a"
DAY15_ID = "d0dd287a-0a87-439d-95cc-8690e7abf0cb"
EOS_ID = "dbc35dee-a5f2-473f-b9b1-bb14b2a1c9ef"
FOLLOWUP_ID = "76fb46ca-2a08-4421-8ce9-b8d412db2fb5"


@pytest.fixture
def plan_definition():
    return json.loads(FIXTURE_PATH.read_text())


def test_parses_all_six_nodes(plan_definition):
    graph = parse_protocol_graph(plan_definition)
    assert set(graph.nodes) == {
        SCREENING_ID, TREATMENT_DAY1_ID, DAY7_ID, DAY15_ID, EOS_ID, FOLLOWUP_ID,
    }


def test_root_is_screening(plan_definition):
    graph = parse_protocol_graph(plan_definition)
    assert graph.root_ids == (SCREENING_ID,)


def test_node_title(plan_definition):
    graph = parse_protocol_graph(plan_definition)
    assert graph.nodes[TREATMENT_DAY1_ID].title == "Treatment Day 1"


def test_treatment_day1_has_two_transitions(plan_definition):
    graph = parse_protocol_graph(plan_definition)
    targets = {t.target_id for t in graph.nodes[TREATMENT_DAY1_ID].transitions}
    assert targets == {DAY7_ID, EOS_ID}


def test_unconditional_transition_has_no_condition(plan_definition):
    graph = parse_protocol_graph(plan_definition)
    to_day7 = next(
        t for t in graph.nodes[TREATMENT_DAY1_ID].transitions if t.target_id == DAY7_ID
    )
    assert to_day7.transition_type == "SS"
    assert to_day7.condition_expression is None


def test_conditional_transition_carries_expression(plan_definition):
    graph = parse_protocol_graph(plan_definition)
    to_eos = next(
        t for t in graph.nodes[TREATMENT_DAY1_ID].transitions if t.target_id == EOS_ID
    )
    assert to_eos.transition_type == "FS"
    assert to_eos.condition_language == "text/x-soa-expressionplain"
    assert to_eos.condition_expression == "{'withdraw':True, 'operation': '=='}"


def test_terminal_node_has_no_transitions(plan_definition):
    graph = parse_protocol_graph(plan_definition)
    assert graph.nodes[FOLLOWUP_ID].transitions == ()


def test_plan_definition_id_recorded(plan_definition):
    graph = parse_protocol_graph(plan_definition)
    assert graph.plan_definition_id == "dynamic-visit-schedule-exit-example-PlanDefinition"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd backend && pytest tests/soa_engine/test_graph.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vulcan_soa.soa_engine.graph'`

- [ ] **Step 4: Write the implementation**

`backend/src/vulcan_soa/soa_engine/graph.py`:
```python
from dataclasses import dataclass

SOA_TIMEPOINT_URL = "http://hl7.org/fhir/uv/vulcan-schedule/StructureDefinition/soaTimepoint"
SOA_TRANSITION_URL = "http://hl7.org/fhir/uv/vulcan-schedule/StructureDefinition/soaTransition"


@dataclass(frozen=True)
class Transition:
    target_id: str
    transition_type: str
    condition_language: str | None
    condition_expression: str | None


@dataclass(frozen=True)
class VisitNode:
    action_id: str
    title: str
    transitions: tuple[Transition, ...]


@dataclass(frozen=True)
class ProtocolGraph:
    plan_definition_id: str
    nodes: dict[str, VisitNode]
    root_ids: tuple[str, ...]


def _find_extension(extensions: list[dict], url: str) -> dict | None:
    for ext in extensions:
        if ext.get("url") == url:
            return ext
    return None


def _sub_extension_value(extension: dict, sub_url: str) -> object | None:
    for sub in extension.get("extension", []):
        if sub.get("url") == sub_url:
            for key, value in sub.items():
                if key.startswith("value"):
                    return value
    return None


def _parse_transition(transition_action: dict) -> Transition:
    soa_transition = _find_extension(transition_action.get("extension", []), SOA_TRANSITION_URL)
    target_id = _sub_extension_value(soa_transition, "soaTargetId") if soa_transition else None
    transition_type = (
        _sub_extension_value(soa_transition, "soaTransitionType") if soa_transition else None
    )

    condition_language = None
    condition_expression = None
    conditions = transition_action.get("condition", [])
    if conditions:
        expression = conditions[0].get("expression", {})
        condition_language = expression.get("language")
        condition_expression = expression.get("expression")

    return Transition(
        target_id=target_id,
        transition_type=transition_type,
        condition_language=condition_language,
        condition_expression=condition_expression,
    )


def _parse_node(action: dict) -> VisitNode:
    transitions = tuple(_parse_transition(child) for child in action.get("action", []))
    return VisitNode(action_id=action["id"], title=action.get("title", action["id"]), transitions=transitions)


def parse_protocol_graph(plan_definition: dict) -> ProtocolGraph:
    actions = plan_definition.get("action", [])
    nodes = {action["id"]: _parse_node(action) for action in actions}
    root_ids = tuple(action["id"] for action in actions)
    return ProtocolGraph(
        plan_definition_id=plan_definition["id"],
        nodes=nodes,
        root_ids=root_ids,
    )
```

Note: in this IG fixture, every node is a top-level `PlanDefinition.action` (transitions are nested *inside* the source node as child actions, not as separate top-level nodes) — so `root_ids` is simply every top-level action id, in document order, and the first one (`Screening`) is the actual entry point. `parse_protocol_graph` does not need to walk nested transition actions as separate graph nodes; it only reads their `soaTransition`/`condition` data to build `Transition` objects attached to their parent `VisitNode`.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd backend && pytest tests/soa_engine/test_graph.py -v`
Expected: `9 passed`

- [ ] **Step 6: Commit**

```bash
git add backend/src/vulcan_soa/soa_engine/__init__.py backend/src/vulcan_soa/soa_engine/graph.py backend/tests/soa_engine/__init__.py backend/tests/soa_engine/test_graph.py backend/tests/fixtures/plan_definition_uc1.json
git commit -m "Add PlanDefinition -> DAG parser for soaTimepoint/soaTransition"
```

---

## Task 7: Condition evaluator (`text/x-soa-expressionplain`)

Interprets the IG's compact mini-DSL used on transition `condition.expression`. The expressions are valid Python dict literals (e.g. `{'withdraw':True, 'operation': '=='}`), so parsing is `ast.literal_eval` — the work is in mapping recognized keys to subject-context lookups and failing closed on anything unrecognized, per the design's error-handling rule.

**Files:**
- Create: `backend/src/vulcan_soa/soa_engine/conditions.py`
- Test: `backend/tests/soa_engine/test_conditions.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (pure module).
- Produces:
  ```python
  @dataclass(frozen=True)
  class SubjectContext:
      withdrawn: bool
      visited_action_ids: frozenset[str]
      completed_action_ids: frozenset[str]

  def evaluate_condition(language: str, expression: str, context: SubjectContext) -> bool: ...
  ```
  Task 8 (`engine.py`) calls `evaluate_condition` for every transition that has a condition; Tasks 9-11 construct `SubjectContext`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/soa_engine/test_conditions.py`:
```python
from vulcan_soa.soa_engine.conditions import SubjectContext, evaluate_condition


def make_context(withdrawn=False):
    return SubjectContext(
        withdrawn=withdrawn, visited_action_ids=frozenset(), completed_action_ids=frozenset()
    )


def test_withdraw_true_matches_withdrawn_subject():
    context = make_context(withdrawn=True)
    assert evaluate_condition(
        "text/x-soa-expressionplain", "{'withdraw':True, 'operation': '=='}", context
    ) is True


def test_withdraw_true_does_not_match_active_subject():
    context = make_context(withdrawn=False)
    assert evaluate_condition(
        "text/x-soa-expressionplain", "{'withdraw':True, 'operation': '=='}", context
    ) is False


def test_withdrawn_key_synonym_is_supported():
    context = make_context(withdrawn=True)
    assert evaluate_condition("text/x-soa-expressionplain", "{'withdrawn':true}", context) is True


def test_operation_defaults_to_equals():
    context = make_context(withdrawn=True)
    assert evaluate_condition("text/x-soa-expressionplain", "{'withdraw':True}", context) is True


def test_not_equals_operation():
    context = make_context(withdrawn=True)
    assert evaluate_condition(
        "text/x-soa-expressionplain", "{'withdraw':True, 'operation': '!='}", context
    ) is False


def test_unsupported_language_fails_closed():
    context = make_context(withdrawn=True)
    assert evaluate_condition("text/fhirpath", "anything", context) is False


def test_unrecognized_key_fails_closed():
    context = make_context(withdrawn=True)
    assert evaluate_condition("text/x-soa-expressionplain", "{'exists':['V1']}", context) is False


def test_malformed_expression_fails_closed():
    context = make_context(withdrawn=True)
    assert evaluate_condition("text/x-soa-expressionplain", "{not valid python", context) is False
```

Note: `{'withdrawn':true}` (lowercase `true`, as written in the IG's prose examples) is not valid Python/`ast.literal_eval` syntax — only `{'withdrawn':True}` is. The implementation normalizes lowercase JSON-style booleans before parsing so both forms the IG actually uses (`True`/`true`) work.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/soa_engine/test_conditions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vulcan_soa.soa_engine.conditions'`

- [ ] **Step 3: Write the implementation**

`backend/src/vulcan_soa/soa_engine/conditions.py`:
```python
import ast
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_OPERATIONS = {
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


@dataclass(frozen=True)
class SubjectContext:
    withdrawn: bool
    visited_action_ids: frozenset[str]
    completed_action_ids: frozenset[str]


def _normalize_json_booleans(expression: str) -> str:
    return (
        expression.replace("true", "True")
        .replace("false", "False")
        .replace("null", "None")
    )


def evaluate_condition(language: str, expression: str, context: SubjectContext) -> bool:
    if language != "text/x-soa-expressionplain":
        logger.warning("Unsupported condition language %r; failing closed", language)
        return False

    try:
        parsed = ast.literal_eval(_normalize_json_booleans(expression))
    except (ValueError, SyntaxError):
        logger.warning("Unparseable condition expression %r; failing closed", expression)
        return False

    if not isinstance(parsed, dict):
        logger.warning("Condition expression %r is not a dict; failing closed", expression)
        return False

    operation = _OPERATIONS.get(parsed.get("operation", "=="))
    if operation is None:
        logger.warning("Unsupported operation in %r; failing closed", expression)
        return False

    if "withdraw" in parsed or "withdrawn" in parsed:
        expected = parsed.get("withdraw", parsed.get("withdrawn"))
        return operation(context.withdrawn, expected)

    logger.warning("No recognized condition key in %r; failing closed", expression)
    return False
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/soa_engine/test_conditions.py -v`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/src/vulcan_soa/soa_engine/conditions.py backend/tests/soa_engine/test_conditions.py
git commit -m "Add text/x-soa-expressionplain condition evaluator, fail-closed on the unknown"
```

---

## Task 8: Schedule-state resolver

Combines `ProtocolGraph` (Task 6) and `SubjectContext`/`evaluate_condition` (Task 7) into the actual engine: given a subject's existing visited/completed action ids, compute which nodes are done, which is in progress, and which transitions are currently valid next steps. When more than one transition is valid with no distinguishing signal, all of them come back in `next_steps` — the caller (Task 9 `scheduling.py`) is responsible for treating `len(next_steps) > 1` as a required decision-support prompt, never auto-selecting.

**Files:**
- Create: `backend/src/vulcan_soa/soa_engine/engine.py`
- Test: `backend/tests/soa_engine/test_engine.py`

**Interfaces:**
- Consumes: `ProtocolGraph`, `VisitNode`, `Transition` (Task 6); `SubjectContext`, `evaluate_condition` (Task 7).
- Produces:
  ```python
  @dataclass(frozen=True)
  class NextStep:
      action_id: str
      title: str
      transition_type: str | None   # None for the initial/root entry step

  @dataclass(frozen=True)
  class ScheduleState:
      completed_action_ids: frozenset[str]
      current_action_ids: frozenset[str]
      next_steps: tuple[NextStep, ...]

  def resolve_schedule_state(graph: ProtocolGraph, context: SubjectContext) -> ScheduleState: ...
  ```
  Tasks 9, 10, 11 (`scheduling.py`, `enrollment.py`, `tracking.py`) all call `resolve_schedule_state` and read `ScheduleState.next_steps`/`.completed_action_ids`/`.current_action_ids`.

- [ ] **Step 1: Write the failing tests**

`backend/tests/soa_engine/test_engine.py`:
```python
import json
from pathlib import Path

import pytest

from vulcan_soa.soa_engine.conditions import SubjectContext
from vulcan_soa.soa_engine.engine import resolve_schedule_state
from vulcan_soa.soa_engine.graph import parse_protocol_graph

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "plan_definition_uc1.json"

SCREENING_ID = "0700e721-1f12-4998-89b8-6f4e649b62f7"
TREATMENT_DAY1_ID = "a1806239-54f3-4762-af3f-edb9d80d29dc"
DAY7_ID = "349447c3-8ad4-4034-8c31-c3d96dcc5f9a"
DAY15_ID = "d0dd287a-0a87-439d-95cc-8690e7abf0cb"
EOS_ID = "dbc35dee-a5f2-473f-b9b1-bb14b2a1c9ef"
FOLLOWUP_ID = "76fb46ca-2a08-4421-8ce9-b8d412db2fb5"


@pytest.fixture
def graph():
    plan_definition = json.loads(FIXTURE_PATH.read_text())
    return parse_protocol_graph(plan_definition)


def context(withdrawn=False, visited=(), completed=()):
    return SubjectContext(
        withdrawn=withdrawn,
        visited_action_ids=frozenset(visited),
        completed_action_ids=frozenset(completed),
    )


def test_no_history_proposes_root_as_next_step(graph):
    state = resolve_schedule_state(graph, context())
    assert [s.action_id for s in state.next_steps] == [SCREENING_ID]
    assert state.next_steps[0].transition_type is None


def test_completed_screening_proposes_treatment_day1(graph):
    state = resolve_schedule_state(
        graph, context(visited=[SCREENING_ID], completed=[SCREENING_ID])
    )
    assert [s.action_id for s in state.next_steps] == [TREATMENT_DAY1_ID]


def test_in_progress_node_is_current_not_completed(graph):
    state = resolve_schedule_state(graph, context(visited=[SCREENING_ID], completed=[]))
    assert state.current_action_ids == frozenset({SCREENING_ID})
    assert state.completed_action_ids == frozenset()


def test_completed_treatment_day1_not_withdrawn_proposes_day7_only(graph):
    state = resolve_schedule_state(
        graph,
        context(
            withdrawn=False,
            visited=[SCREENING_ID, TREATMENT_DAY1_ID],
            completed=[SCREENING_ID, TREATMENT_DAY1_ID],
        ),
    )
    assert [s.action_id for s in state.next_steps] == [DAY7_ID]


def test_completed_treatment_day1_withdrawn_is_ambiguous(graph):
    state = resolve_schedule_state(
        graph,
        context(
            withdrawn=True,
            visited=[SCREENING_ID, TREATMENT_DAY1_ID],
            completed=[SCREENING_ID, TREATMENT_DAY1_ID],
        ),
    )
    target_ids = {s.action_id for s in state.next_steps}
    assert target_ids == {DAY7_ID, EOS_ID}
    assert len(state.next_steps) > 1


def test_terminal_node_completed_has_no_next_steps(graph):
    state = resolve_schedule_state(
        graph,
        context(
            visited=[SCREENING_ID, TREATMENT_DAY1_ID, DAY7_ID, DAY15_ID, EOS_ID, FOLLOWUP_ID],
            completed=[SCREENING_ID, TREATMENT_DAY1_ID, DAY7_ID, DAY15_ID, EOS_ID, FOLLOWUP_ID],
        ),
    )
    assert state.next_steps == ()


def test_unknown_action_ids_in_context_are_ignored(graph):
    state = resolve_schedule_state(
        graph, context(visited=["not-a-real-action"], completed=["not-a-real-action"])
    )
    assert state.completed_action_ids == frozenset()
    assert state.current_action_ids == frozenset()


def test_completed_through_day7_withdrawn_deduplicates_end_of_study_target(graph):
    # Both Treatment Day 1 and Day 7 have a conditional transition to End of Study; once
    # withdrawn and both are completed, End of Study must appear only once, not twice.
    state = resolve_schedule_state(
        graph,
        context(
            withdrawn=True,
            visited=[SCREENING_ID, TREATMENT_DAY1_ID, DAY7_ID],
            completed=[SCREENING_ID, TREATMENT_DAY1_ID, DAY7_ID],
        ),
    )
    target_ids = [s.action_id for s in state.next_steps]
    assert target_ids.count(EOS_ID) == 1
    assert set(target_ids) == {DAY15_ID, EOS_ID}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/soa_engine/test_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vulcan_soa.soa_engine.engine'`

- [ ] **Step 3: Write the implementation**

`backend/src/vulcan_soa/soa_engine/engine.py`:
```python
from dataclasses import dataclass

from vulcan_soa.soa_engine.conditions import SubjectContext, evaluate_condition
from vulcan_soa.soa_engine.graph import ProtocolGraph


@dataclass(frozen=True)
class NextStep:
    action_id: str
    title: str
    transition_type: str | None


@dataclass(frozen=True)
class ScheduleState:
    completed_action_ids: frozenset[str]
    current_action_ids: frozenset[str]
    next_steps: tuple[NextStep, ...]


def resolve_schedule_state(graph: ProtocolGraph, context: SubjectContext) -> ScheduleState:
    known_ids = frozenset(graph.nodes)
    completed = known_ids & context.completed_action_ids
    visited = known_ids & context.visited_action_ids
    current = visited - completed

    if not visited:
        next_steps = tuple(
            NextStep(action_id=root_id, title=graph.nodes[root_id].title, transition_type=None)
            for root_id in graph.root_ids
        )
        return ScheduleState(
            completed_action_ids=completed, current_action_ids=current, next_steps=next_steps
        )

    next_steps = []
    seen_target_ids: set[str] = set()
    for action_id in completed:
        node = graph.nodes[action_id]
        for transition in node.transitions:
            if transition.target_id not in graph.nodes:
                continue
            if transition.target_id in visited or transition.target_id in seen_target_ids:
                continue
            if transition.condition_expression is not None:
                allowed = evaluate_condition(
                    transition.condition_language, transition.condition_expression, context
                )
            else:
                allowed = True
            if allowed:
                target = graph.nodes[transition.target_id]
                next_steps.append(
                    NextStep(
                        action_id=transition.target_id,
                        title=target.title,
                        transition_type=transition.transition_type,
                    )
                )
                seen_target_ids.add(transition.target_id)

    return ScheduleState(
        completed_action_ids=completed,
        current_action_ids=current,
        next_steps=tuple(next_steps),
    )
```

Two details that aren't obvious from a first pass: `transition.target_id in visited` skips any transition whose target the subject has already reached (completed or in-progress) — without it, a completed node's transition back toward an already-completed downstream node would wrongly resurface as a "next step" (this is what `test_completed_treatment_day1_not_withdrawn_proposes_day7_only` and `test_terminal_node_completed_has_no_next_steps` actually exercise). `seen_target_ids` dedupes the case where two different completed nodes both validly transition to the same not-yet-visited target — reachable in this exact fixture once a subject has completed both Treatment Day 1 and Day 7 while withdrawn, since both carry a conditional transition to End of Study (`test_completed_through_day7_withdrawn_deduplicates_end_of_study_target`).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/soa_engine/test_engine.py -v`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/src/vulcan_soa/soa_engine/engine.py backend/tests/soa_engine/test_engine.py
git commit -m "Add schedule-state resolver: completed/current/next-steps from FHIR-as-state"
```

---

## Task 9: Scheduling — tagging, materializing visits, reading subject state from Aidbox

This is the bridge between the pure `soa_engine` and Aidbox: tags materialized `Encounter`s back to their originating `PlanDefinition.action.id` (via `Encounter.identifier`, not a custom extension — no new StructureDefinition dependency), and reconstructs a `SubjectContext` by querying which tagged Encounters already exist for a subject. This module is also where the design's protocol-graph loading lives, shared by enrollment, tracking, and the schedule-read API route.

**Files:**
- Create: `backend/src/vulcan_soa/scheduling.py`
- Test: `backend/tests/test_scheduling.py`

**Interfaces:**
- Consumes: `FhirClient` (Task 4); `VisitNode`, `ProtocolGraph`, `parse_protocol_graph` (Task 6); `SubjectContext` (Task 7); `ScheduleState` (Task 8).
- Produces:
  ```python
  ACTION_TAG_SYSTEM: str  # "urn:vulcan-soa:plan-action"

  def tag_for(plan_definition_id: str, action_id: str) -> dict: ...
  async def materialize_visit(client, patient_id, plan_definition_id, node, status="planned") -> dict: ...
  async def load_subject_context(client, research_subject, plan_definition_id) -> tuple[SubjectContext, dict[str, dict]]: ...
  async def load_protocol_graph(client, study_id) -> tuple[ProtocolGraph, str]: ...
  async def load_protocol_graph_for_subject(client, subject) -> tuple[ProtocolGraph, str]: ...
  def schedule_response(state: ScheduleState) -> dict: ...
  ```
  Tasks 10, 11, and 15 import all of these.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_scheduling.py`:
```python
import json

import httpx
import respx

from vulcan_soa.fhir_client import FhirClient
from vulcan_soa.scheduling import (
    ACTION_TAG_SYSTEM,
    load_protocol_graph,
    load_subject_context,
    materialize_visit,
    schedule_response,
    tag_for,
)
from vulcan_soa.soa_engine.engine import NextStep, ScheduleState
from vulcan_soa.soa_engine.graph import VisitNode


def test_tag_for_combines_plan_and_action_id():
    assert tag_for("plan-1", "action-1") == {
        "system": ACTION_TAG_SYSTEM,
        "value": "plan-1#action-1",
    }


@respx.mock
async def test_materialize_visit_creates_tagged_planned_encounter():
    route = respx.post("http://aidbox.test/fhir/Encounter").mock(
        return_value=httpx.Response(201, json={"resourceType": "Encounter", "id": "enc-1"})
    )
    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok")
    node = VisitNode(action_id="action-1", title="Screening", transitions=())

    result = await materialize_visit(client, "patient-1", "plan-1", node)
    await client.close()

    assert result["id"] == "enc-1"
    payload = json.loads(route.calls.last.request.content)
    assert payload["status"] == "planned"
    assert payload["subject"] == {"reference": "Patient/patient-1"}
    assert payload["identifier"] == [{"system": ACTION_TAG_SYSTEM, "value": "plan-1#action-1"}]


@respx.mock
async def test_load_subject_context_reads_withdrawn_state_and_encounters():
    respx.get("http://aidbox.test/fhir/Encounter").mock(
        return_value=httpx.Response(
            200,
            json={
                "resourceType": "Bundle",
                "entry": [
                    {
                        "resource": {
                            "resourceType": "Encounter",
                            "id": "enc-1",
                            "status": "finished",
                            "identifier": [
                                {"system": ACTION_TAG_SYSTEM, "value": "plan-1#action-1"}
                            ],
                        }
                    },
                    {
                        "resource": {
                            "resourceType": "Encounter",
                            "id": "enc-2",
                            "status": "planned",
                            "identifier": [
                                {"system": ACTION_TAG_SYSTEM, "value": "plan-1#action-2"}
                            ],
                        }
                    },
                ],
            },
        )
    )
    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok")
    subject = {
        "resourceType": "ResearchSubject",
        "subjectState": {"coding": [{"code": "withdrawn"}]},
        "subject": {"reference": "Patient/patient-1"},
    }

    context, by_action_id = await load_subject_context(client, subject, "plan-1")
    await client.close()

    assert context.withdrawn is True
    assert context.visited_action_ids == frozenset({"action-1", "action-2"})
    assert context.completed_action_ids == frozenset({"action-1"})
    assert by_action_id["action-1"]["id"] == "enc-1"


@respx.mock
async def test_load_subject_context_not_withdrawn_when_state_differs():
    respx.get("http://aidbox.test/fhir/Encounter").mock(
        return_value=httpx.Response(200, json={"resourceType": "Bundle"})
    )
    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok")
    subject = {
        "resourceType": "ResearchSubject",
        "subjectState": {"coding": [{"code": "on-study"}]},
        "subject": {"reference": "Patient/patient-1"},
    }

    context, by_action_id = await load_subject_context(client, subject, "plan-1")
    await client.close()

    assert context.withdrawn is False
    assert context.visited_action_ids == frozenset()
    assert by_action_id == {}


@respx.mock
async def test_load_protocol_graph_reads_study_then_plan_definition():
    respx.get("http://aidbox.test/fhir/ResearchStudy/study-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "resourceType": "ResearchStudy",
                "id": "study-1",
                "protocol": [{"reference": "PlanDefinition/plan-1"}],
            },
        )
    )
    respx.get("http://aidbox.test/fhir/PlanDefinition/plan-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "resourceType": "PlanDefinition",
                "id": "plan-1",
                "action": [{"id": "action-1", "title": "Screening"}],
            },
        )
    )
    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok")

    graph, plan_definition_id = await load_protocol_graph(client, "study-1")
    await client.close()

    assert plan_definition_id == "plan-1"
    assert graph.root_ids == ("action-1",)


def test_schedule_response_shapes_state_and_flags_ambiguous():
    state = ScheduleState(
        completed_action_ids=frozenset({"a"}),
        current_action_ids=frozenset(),
        next_steps=(
            NextStep(action_id="b", title="Day 7", transition_type="SS"),
            NextStep(action_id="c", title="End of Study", transition_type="FS"),
        ),
    )
    response = schedule_response(state)

    assert response["completed"] == ["a"]
    assert response["nextSteps"] == [
        {"actionId": "b", "title": "Day 7", "transitionType": "SS"},
        {"actionId": "c", "title": "End of Study", "transitionType": "FS"},
    ]
    assert response["ambiguous"] is True


def test_schedule_response_not_ambiguous_for_single_next_step():
    state = ScheduleState(
        completed_action_ids=frozenset(),
        current_action_ids=frozenset(),
        next_steps=(NextStep(action_id="a", title="Screening", transition_type=None),),
    )
    assert schedule_response(state)["ambiguous"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_scheduling.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vulcan_soa.scheduling'`

- [ ] **Step 3: Write the implementation**

`backend/src/vulcan_soa/scheduling.py`:
```python
from vulcan_soa.fhir_client import FhirClient
from vulcan_soa.soa_engine.conditions import SubjectContext
from vulcan_soa.soa_engine.engine import ScheduleState
from vulcan_soa.soa_engine.graph import ProtocolGraph, VisitNode, parse_protocol_graph

ACTION_TAG_SYSTEM = "urn:vulcan-soa:plan-action"


def tag_for(plan_definition_id: str, action_id: str) -> dict:
    return {"system": ACTION_TAG_SYSTEM, "value": f"{plan_definition_id}#{action_id}"}


async def materialize_visit(
    client: FhirClient,
    patient_id: str,
    plan_definition_id: str,
    node: VisitNode,
    status: str = "planned",
) -> dict:
    encounter = {
        "resourceType": "Encounter",
        "status": status,
        "class": [
            {"coding": [{"system": "http://terminology.hl7.org/CodeSystem/v3-ActCode", "code": "AMB"}]}
        ],
        "subject": {"reference": f"Patient/{patient_id}"},
        "identifier": [tag_for(plan_definition_id, node.action_id)],
    }
    return await client.create("Encounter", encounter)


async def load_subject_context(
    client: FhirClient, research_subject: dict, plan_definition_id: str
) -> tuple[SubjectContext, dict[str, dict]]:
    state_codes = {
        coding.get("code") for coding in research_subject.get("subjectState", {}).get("coding", [])
    }
    withdrawn = "withdrawn" in state_codes
    patient_id = research_subject["subject"]["reference"].split("/", 1)[1]

    encounters = await client.search(
        "Encounter",
        {"subject": f"Patient/{patient_id}", "identifier": f"{ACTION_TAG_SYSTEM}|"},
    )

    prefix = f"{plan_definition_id}#"
    visited: set[str] = set()
    completed: set[str] = set()
    by_action_id: dict[str, dict] = {}
    for encounter in encounters:
        for identifier in encounter.get("identifier", []):
            if identifier.get("system") != ACTION_TAG_SYSTEM:
                continue
            value = identifier.get("value", "")
            if not value.startswith(prefix):
                continue
            action_id = value[len(prefix):]
            visited.add(action_id)
            by_action_id[action_id] = encounter
            if encounter.get("status") == "finished":
                completed.add(action_id)

    context = SubjectContext(
        withdrawn=withdrawn,
        visited_action_ids=frozenset(visited),
        completed_action_ids=frozenset(completed),
    )
    return context, by_action_id


async def load_protocol_graph(client: FhirClient, study_id: str) -> tuple[ProtocolGraph, str]:
    study = await client.read("ResearchStudy", study_id)
    plan_definition_id = study["protocol"][0]["reference"].split("/", 1)[1]
    plan_definition = await client.read("PlanDefinition", plan_definition_id)
    return parse_protocol_graph(plan_definition), plan_definition_id


async def load_protocol_graph_for_subject(
    client: FhirClient, subject: dict
) -> tuple[ProtocolGraph, str]:
    study_id = subject["study"]["reference"].split("/", 1)[1]
    return await load_protocol_graph(client, study_id)


def schedule_response(state: ScheduleState) -> dict:
    return {
        "completed": sorted(state.completed_action_ids),
        "current": sorted(state.current_action_ids),
        "nextSteps": [
            {"actionId": s.action_id, "title": s.title, "transitionType": s.transition_type}
            for s in state.next_steps
        ],
        "ambiguous": len(state.next_steps) > 1,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_scheduling.py -v`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/src/vulcan_soa/scheduling.py backend/tests/test_scheduling.py
git commit -m "Add scheduling: action tagging, visit materialization, subject-state reconstruction"
```

---

## Task 10: Enrollment

**Files:**
- Create: `backend/src/vulcan_soa/enrollment.py`
- Test: `backend/tests/test_enrollment.py`

**Interfaces:**
- Consumes: `FhirClient` (Task 4); `resolve_schedule_state`, `SubjectContext` (Tasks 7-8); `materialize_visit`, `load_protocol_graph`, `schedule_response` (Task 9).
- Produces: `async def enroll(client: FhirClient, study_id: str, patient_id: str) -> dict` returning `{"researchSubjectId": str, "schedule": dict}`. Task 14 (`api/research_studies.py`) calls this directly.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_enrollment.py`:
```python
import json

import httpx
import respx

from vulcan_soa.enrollment import enroll
from vulcan_soa.fhir_client import FhirClient

STUDY = {
    "resourceType": "ResearchStudy",
    "id": "uc1-demo-research-study",
    "protocol": [{"reference": "PlanDefinition/plan-1"}],
}
PLAN_DEFINITION = {
    "resourceType": "PlanDefinition",
    "id": "plan-1",
    "action": [{"id": "screening-1", "title": "Screening"}],
}


@respx.mock
async def test_enroll_creates_subject_and_materializes_root_visit():
    respx.get("http://aidbox.test/fhir/ResearchStudy/uc1-demo-research-study").mock(
        return_value=httpx.Response(200, json=STUDY)
    )
    respx.get("http://aidbox.test/fhir/PlanDefinition/plan-1").mock(
        return_value=httpx.Response(200, json=PLAN_DEFINITION)
    )
    respx.get("http://aidbox.test/fhir/ResearchSubject").mock(
        return_value=httpx.Response(200, json={"resourceType": "Bundle"})
    )
    create_subject_route = respx.post("http://aidbox.test/fhir/ResearchSubject").mock(
        return_value=httpx.Response(201, json={"resourceType": "ResearchSubject", "id": "subj-1"})
    )
    create_encounter_route = respx.post("http://aidbox.test/fhir/Encounter").mock(
        return_value=httpx.Response(201, json={"resourceType": "Encounter", "id": "enc-1"})
    )

    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok")
    result = await enroll(client, "uc1-demo-research-study", "patient-1")
    await client.close()

    assert result["researchSubjectId"] == "subj-1"
    assert result["schedule"]["nextSteps"] == []  # the root visit is materialized, not "next"
    assert create_subject_route.called
    assert create_encounter_route.called
    encounter_payload = json.loads(create_encounter_route.calls.last.request.content)
    assert encounter_payload["identifier"] == [
        {"system": "urn:vulcan-soa:plan-action", "value": "plan-1#screening-1"}
    ]


@respx.mock
async def test_enroll_is_idempotent_via_conditional_create():
    respx.get("http://aidbox.test/fhir/ResearchStudy/uc1-demo-research-study").mock(
        return_value=httpx.Response(200, json=STUDY)
    )
    respx.get("http://aidbox.test/fhir/PlanDefinition/plan-1").mock(
        return_value=httpx.Response(200, json=PLAN_DEFINITION)
    )
    respx.get("http://aidbox.test/fhir/ResearchSubject").mock(
        return_value=httpx.Response(
            200,
            json={
                "resourceType": "Bundle",
                "entry": [{"resource": {"resourceType": "ResearchSubject", "id": "subj-existing"}}],
            },
        )
    )
    create_subject_route = respx.post("http://aidbox.test/fhir/ResearchSubject")
    respx.post("http://aidbox.test/fhir/Encounter").mock(
        return_value=httpx.Response(201, json={"resourceType": "Encounter", "id": "enc-1"})
    )

    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok")
    result = await enroll(client, "uc1-demo-research-study", "patient-1")
    await client.close()

    assert result["researchSubjectId"] == "subj-existing"
    assert not create_subject_route.called
```

Note: `result["schedule"]["nextSteps"] == []` looks surprising at first — `enroll` immediately materializes the resolved root visit(s) (here, Screening) rather than leaving them as "next steps," so right after enrollment there are zero *pending* next steps until that first visit is itself completed. This matches the design's data flow: "scheduling resolves the first reachable node(s) ... materializes the corresponding Encounter/Task ... returns the initial schedule slice."

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_enrollment.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vulcan_soa.enrollment'`

- [ ] **Step 3: Write the implementation**

`backend/src/vulcan_soa/enrollment.py`:
```python
from vulcan_soa.fhir_client import FhirClient
from vulcan_soa.scheduling import load_protocol_graph, materialize_visit, schedule_response
from vulcan_soa.soa_engine.conditions import SubjectContext
from vulcan_soa.soa_engine.engine import resolve_schedule_state

RESEARCH_SUBJECT_STATE_SYSTEM = "http://terminology.hl7.org/CodeSystem/research-subject-state"


async def enroll(client: FhirClient, study_id: str, patient_id: str) -> dict:
    graph, plan_definition_id = await load_protocol_graph(client, study_id)

    subject_resource = {
        "resourceType": "ResearchSubject",
        "subjectState": {
            "coding": [{"system": RESEARCH_SUBJECT_STATE_SYSTEM, "code": "candidate"}]
        },
        "study": {"reference": f"ResearchStudy/{study_id}"},
        "subject": {"reference": f"Patient/{patient_id}"},
    }
    created = await client.conditional_create(
        "ResearchSubject",
        subject_resource,
        {"study": f"ResearchStudy/{study_id}", "subject": f"Patient/{patient_id}"},
    )

    initial_context = SubjectContext(
        withdrawn=False, visited_action_ids=frozenset(), completed_action_ids=frozenset()
    )
    initial_state = resolve_schedule_state(graph, initial_context)
    for step in initial_state.next_steps:
        node = graph.nodes[step.action_id]
        await materialize_visit(client, patient_id, plan_definition_id, node)

    materialized_ids = frozenset(step.action_id for step in initial_state.next_steps)
    post_enroll_state = resolve_schedule_state(
        graph,
        SubjectContext(
            withdrawn=False, visited_action_ids=materialized_ids, completed_action_ids=frozenset()
        ),
    )

    return {
        "researchSubjectId": created["id"],
        "schedule": schedule_response(post_enroll_state),
    }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_enrollment.py -v`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/src/vulcan_soa/enrollment.py backend/tests/test_enrollment.py
git commit -m "Add enrollment: conditional-create ResearchSubject and materialize root visit"
```

---

## Task 11: Tracking — withdrawal and visit completion

**Files:**
- Create: `backend/src/vulcan_soa/tracking.py`
- Test: `backend/tests/test_tracking.py`

**Interfaces:**
- Consumes: `FhirClient` (Task 4); `resolve_schedule_state` (Task 8); `load_subject_context`, `load_protocol_graph_for_subject`, `materialize_visit`, `schedule_response` (Task 9).
- Produces: `async def withdraw_subject(client, subject_id) -> dict`; `async def complete_visit(client, subject_id, action_id, transition_choice) -> dict`. Task 15 (`api/research_subjects.py`) calls both directly.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_tracking.py`:
```python
import json

import httpx
import respx

from vulcan_soa.fhir_client import FhirClient
from vulcan_soa.tracking import complete_visit, withdraw_subject

SUBJECT = {
    "resourceType": "ResearchSubject",
    "id": "subj-1",
    "subjectState": {"coding": [{"code": "on-study"}]},
    "study": {"reference": "ResearchStudy/study-1"},
    "subject": {"reference": "Patient/patient-1"},
}
STUDY = {
    "resourceType": "ResearchStudy",
    "id": "study-1",
    "protocol": [{"reference": "PlanDefinition/plan-1"}],
}
PLAN_DEFINITION = {
    "resourceType": "PlanDefinition",
    "id": "plan-1",
    "action": [
        {
            "id": "screening-1",
            "title": "Screening",
            "action": [
                {
                    "extension": [
                        {
                            "url": "http://hl7.org/fhir/uv/vulcan-schedule/StructureDefinition/soaTransition",
                            "extension": [
                                {"url": "soaTargetId", "valueString": "treatment-1"},
                                {"url": "soaTransitionType", "valueString": "SS"},
                            ],
                        }
                    ]
                }
            ],
        },
        {"id": "treatment-1", "title": "Treatment Day 1"},
    ],
}
SCREENING_ENCOUNTER = {
    "resourceType": "Encounter",
    "id": "enc-1",
    "status": "planned",
    "meta": {"versionId": "1"},
    "identifier": [{"system": "urn:vulcan-soa:plan-action", "value": "plan-1#screening-1"}],
}


@respx.mock
async def test_withdraw_subject_updates_subject_state():
    respx.get("http://aidbox.test/fhir/ResearchSubject/subj-1").mock(
        return_value=httpx.Response(200, json=dict(SUBJECT, meta={"versionId": "5"}))
    )
    update_route = respx.put("http://aidbox.test/fhir/ResearchSubject/subj-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "resourceType": "ResearchSubject",
                "id": "subj-1",
                "subjectState": {"coding": [{"code": "withdrawn"}]},
            },
        )
    )

    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok")
    result = await withdraw_subject(client, "subj-1")
    await client.close()

    assert result == {"id": "subj-1", "subjectState": "withdrawn"}
    assert update_route.calls.last.request.headers["If-Match"] == 'W/"5"'
    payload = json.loads(update_route.calls.last.request.content)
    assert payload["subjectState"]["coding"][0]["code"] == "withdrawn"


@respx.mock
async def test_complete_visit_marks_finished_and_materializes_single_next_step():
    respx.get("http://aidbox.test/fhir/ResearchSubject/subj-1").mock(
        return_value=httpx.Response(200, json=SUBJECT)
    )
    respx.get("http://aidbox.test/fhir/ResearchStudy/study-1").mock(
        return_value=httpx.Response(200, json=STUDY)
    )
    respx.get("http://aidbox.test/fhir/PlanDefinition/plan-1").mock(
        return_value=httpx.Response(200, json=PLAN_DEFINITION)
    )
    respx.get("http://aidbox.test/fhir/Encounter").mock(
        return_value=httpx.Response(
            200,
            json={"resourceType": "Bundle", "entry": [{"resource": SCREENING_ENCOUNTER}]},
        )
    )
    update_route = respx.put("http://aidbox.test/fhir/Encounter/enc-1").mock(
        return_value=httpx.Response(200, json=dict(SCREENING_ENCOUNTER, status="finished"))
    )
    create_route = respx.post("http://aidbox.test/fhir/Encounter").mock(
        return_value=httpx.Response(201, json={"resourceType": "Encounter", "id": "enc-2"})
    )

    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok")
    result = await complete_visit(client, "subj-1", "screening-1", None)
    await client.close()

    assert update_route.called
    assert json.loads(update_route.calls.last.request.content)["status"] == "finished"
    assert create_route.called
    new_encounter_payload = json.loads(create_route.calls.last.request.content)
    assert new_encounter_payload["identifier"] == [
        {"system": "urn:vulcan-soa:plan-action", "value": "plan-1#treatment-1"}
    ]
    assert result["completed"] == ["screening-1"]


@respx.mock
async def test_complete_visit_raises_when_action_not_materialized():
    respx.get("http://aidbox.test/fhir/ResearchSubject/subj-1").mock(
        return_value=httpx.Response(200, json=SUBJECT)
    )
    respx.get("http://aidbox.test/fhir/ResearchStudy/study-1").mock(
        return_value=httpx.Response(200, json=STUDY)
    )
    respx.get("http://aidbox.test/fhir/PlanDefinition/plan-1").mock(
        return_value=httpx.Response(200, json=PLAN_DEFINITION)
    )
    respx.get("http://aidbox.test/fhir/Encounter").mock(
        return_value=httpx.Response(200, json={"resourceType": "Bundle"})
    )

    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok")
    try:
        await complete_visit(client, "subj-1", "screening-1", None)
        raised = False
    except ValueError:
        raised = True
    await client.close()

    assert raised
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_tracking.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vulcan_soa.tracking'`

- [ ] **Step 3: Write the implementation**

`backend/src/vulcan_soa/tracking.py`:
```python
from vulcan_soa.fhir_client import FhirClient
from vulcan_soa.scheduling import (
    load_protocol_graph_for_subject,
    load_subject_context,
    materialize_visit,
    schedule_response,
)
from vulcan_soa.soa_engine.engine import resolve_schedule_state

RESEARCH_SUBJECT_STATE_SYSTEM = "http://terminology.hl7.org/CodeSystem/research-subject-state"


def _if_match(resource: dict) -> str | None:
    version_id = resource.get("meta", {}).get("versionId")
    return f'W/"{version_id}"' if version_id else None


async def withdraw_subject(client: FhirClient, subject_id: str) -> dict:
    subject = await client.read("ResearchSubject", subject_id)
    subject["subjectState"] = {
        "coding": [{"system": RESEARCH_SUBJECT_STATE_SYSTEM, "code": "withdrawn"}]
    }
    updated = await client.update(
        "ResearchSubject", subject_id, subject, if_match=_if_match(subject)
    )
    return {"id": updated["id"], "subjectState": "withdrawn"}


async def complete_visit(
    client: FhirClient, subject_id: str, action_id: str, transition_choice: str | None
) -> dict:
    subject = await client.read("ResearchSubject", subject_id)
    graph, plan_definition_id = await load_protocol_graph_for_subject(client, subject)
    patient_id = subject["subject"]["reference"].split("/", 1)[1]

    _, by_action_id = await load_subject_context(client, subject, plan_definition_id)
    encounter = by_action_id.get(action_id)
    if encounter is None:
        raise ValueError(f"No materialized visit found for action {action_id}")

    encounter["status"] = "finished"
    await client.update("Encounter", encounter["id"], encounter, if_match=_if_match(encounter))

    context, _ = await load_subject_context(client, subject, plan_definition_id)
    state = resolve_schedule_state(graph, context)

    if len(state.next_steps) == 1:
        node = graph.nodes[state.next_steps[0].action_id]
        await materialize_visit(client, patient_id, plan_definition_id, node)
    elif len(state.next_steps) > 1 and transition_choice is not None:
        chosen = next((s for s in state.next_steps if s.action_id == transition_choice), None)
        if chosen is not None:
            node = graph.nodes[chosen.action_id]
            await materialize_visit(client, patient_id, plan_definition_id, node)

    return schedule_response(state)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_tracking.py -v`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/src/vulcan_soa/tracking.py backend/tests/test_tracking.py
git commit -m "Add tracking: withdrawal and visit completion with decision-support on ambiguity"
```

---

## Task 12: Auth — PKCE, SMART launch URL building, token exchange, `fhirContext` parsing

**Files:**
- Create: `backend/src/vulcan_soa/auth.py`
- Test: `backend/tests/test_auth.py`

**Interfaces:**
- Consumes: `Settings` (Task 2).
- Produces:
  ```python
  @dataclass(frozen=True)
  class PendingLaunch:
      code_verifier: str
      launch: str | None  # None for standalone launch

  @dataclass(frozen=True)
  class Session:
      access_token: str
      patient_id: str | None
      research_study_id: str | None

  def generate_pkce_pair() -> tuple[str, str]: ...  # (code_verifier, code_challenge)
  def build_authorize_url(settings, pending_launch, *, state: str, code_challenge: str) -> str: ...
  async def exchange_code_for_token(settings, http_client, code, code_verifier) -> dict: ...
  def parse_research_study_id(fhir_context: list[dict] | None) -> str | None: ...
  def session_from_token_response(token_response: dict) -> Session: ...
  ```
  `PendingLaunch` deliberately has no `state` field: Task 14 uses the opaque key that `InMemoryStore.create()` (Task 3) returns when storing the `PendingLaunch` *as* the OAuth `state` value, so there is exactly one source of truth for it. `build_authorize_url` takes `state` as an explicit argument for the same reason. Task 14 (`api/launch.py`) uses all of these directly.

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_auth.py`:
```python
import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import httpx
import respx

from vulcan_soa.auth import (
    PendingLaunch,
    build_authorize_url,
    exchange_code_for_token,
    generate_pkce_pair,
    parse_research_study_id,
    session_from_token_response,
)
from vulcan_soa.config import Settings

SETTINGS = Settings(
    fhir_base_url="https://aidbox.test/fhir",
    oauth_authorize_url="https://aidbox.test/authorize",
    oauth_token_url="https://aidbox.test/token",
    smart_client_id="client-1",
    smart_client_secret="secret-1",
    redirect_uri="https://app.test/callback",
)


def test_generate_pkce_pair_challenge_matches_verifier():
    code_verifier, code_challenge = generate_pkce_pair()

    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    expected_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    assert code_challenge == expected_challenge
    assert len(code_verifier) >= 43  # RFC 7636 minimum


def test_build_authorize_url_includes_launch_scope_for_ehr_launch():
    pending = PendingLaunch(code_verifier="verifier-1", launch="launch-1")
    url = build_authorize_url(SETTINGS, pending, state="state-1", code_challenge="challenge-1")

    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "aidbox.test"
    assert parsed.path == "/authorize"
    assert "launch" in query["scope"][0]
    assert query["launch"] == ["launch-1"]
    assert query["state"] == ["state-1"]
    assert query["code_challenge"] == ["challenge-1"]
    assert query["code_challenge_method"] == ["S256"]
    assert query["client_id"] == ["client-1"]
    assert query["redirect_uri"] == ["https://app.test/callback"]


def test_build_authorize_url_omits_launch_for_standalone():
    pending = PendingLaunch(code_verifier="verifier-1", launch=None)
    url = build_authorize_url(SETTINGS, pending, state="state-1", code_challenge="challenge-1")

    query = parse_qs(urlparse(url).query)
    assert "launch" not in query
    assert "launch" not in query["scope"][0]


@respx.mock
async def test_exchange_code_for_token_posts_pkce_verifier_and_basic_auth():
    route = respx.post("https://aidbox.test/token").mock(
        return_value=httpx.Response(200, json={"access_token": "tok-1", "patient": "patient-1"})
    )

    async with httpx.AsyncClient() as http_client:
        token_response = await exchange_code_for_token(SETTINGS, http_client, "code-1", "verifier-1")

    assert token_response == {"access_token": "tok-1", "patient": "patient-1"}
    sent = route.calls.last.request
    assert sent.headers["Authorization"].startswith("Basic ")
    body = parse_qs(sent.content.decode("utf-8"))
    assert body["grant_type"] == ["authorization_code"]
    assert body["code"] == ["code-1"]
    assert body["code_verifier"] == ["verifier-1"]
    assert body["redirect_uri"] == ["https://app.test/callback"]


def test_parse_research_study_id_finds_research_study_reference():
    fhir_context = [{"reference": "Patient/patient-1"}, {"reference": "ResearchStudy/study-1"}]
    assert parse_research_study_id(fhir_context) == "study-1"


def test_parse_research_study_id_returns_none_when_absent_or_empty():
    assert parse_research_study_id([{"reference": "Patient/patient-1"}]) is None
    assert parse_research_study_id(None) is None
    assert parse_research_study_id([]) is None


def test_session_from_token_response_extracts_patient_and_research_study():
    token_response = {
        "access_token": "tok-1",
        "patient": "patient-1",
        "fhirContext": [{"reference": "ResearchStudy/study-1"}],
    }
    session = session_from_token_response(token_response)

    assert session.access_token == "tok-1"
    assert session.patient_id == "patient-1"
    assert session.research_study_id == "study-1"


def test_session_from_token_response_handles_missing_context():
    session = session_from_token_response({"access_token": "tok-1"})
    assert session.patient_id is None
    assert session.research_study_id is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vulcan_soa.auth'`

- [ ] **Step 3: Write the implementation**

`backend/src/vulcan_soa/auth.py`:
```python
import base64
import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from vulcan_soa.config import Settings


@dataclass(frozen=True)
class PendingLaunch:
    code_verifier: str
    launch: str | None


@dataclass(frozen=True)
class Session:
    access_token: str
    patient_id: str | None
    research_study_id: str | None


def generate_pkce_pair() -> tuple[str, str]:
    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return code_verifier, code_challenge


def build_authorize_url(
    settings: Settings, pending_launch: PendingLaunch, *, state: str, code_challenge: str
) -> str:
    scope = "openid fhirUser patient/*.read"
    if pending_launch.launch is not None:
        scope = f"{scope} launch"

    params = {
        "response_type": "code",
        "client_id": settings.smart_client_id,
        "redirect_uri": settings.redirect_uri,
        "scope": scope,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "aud": settings.fhir_base_url,
    }
    if pending_launch.launch is not None:
        params["launch"] = pending_launch.launch

    return f"{settings.oauth_authorize_url}?{urlencode(params)}"


async def exchange_code_for_token(
    settings: Settings, http_client: httpx.AsyncClient, code: str, code_verifier: str
) -> dict:
    response = await http_client.post(
        settings.oauth_token_url,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.redirect_uri,
            "client_id": settings.smart_client_id,
            "code_verifier": code_verifier,
        },
        auth=(settings.smart_client_id, settings.smart_client_secret),
    )
    response.raise_for_status()
    return response.json()


def parse_research_study_id(fhir_context: list[dict] | None) -> str | None:
    if not fhir_context:
        return None
    for entry in fhir_context:
        reference = entry.get("reference", "")
        if reference.startswith("ResearchStudy/"):
            return reference.split("/", 1)[1]
    return None


def session_from_token_response(token_response: dict) -> Session:
    return Session(
        access_token=token_response["access_token"],
        patient_id=token_response.get("patient"),
        research_study_id=parse_research_study_id(token_response.get("fhirContext")),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_auth.py -v`
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/src/vulcan_soa/auth.py backend/tests/test_auth.py
git commit -m "Add SMART launch auth: PKCE, authorize-URL building, token exchange, fhirContext parsing"
```

---

## Task 13: API request models and shared FastAPI dependencies

**Files:**
- Create: `backend/src/vulcan_soa/api/__init__.py` (empty)
- Create: `backend/src/vulcan_soa/api/models.py`
- Create: `backend/src/vulcan_soa/api/deps.py`
- Test: `backend/tests/api/__init__.py` (empty)
- Test: `backend/tests/api/test_deps.py`

**Interfaces:**
- Consumes: `Settings` (Task 2); `InMemoryStore` (Task 3); `FhirClient` (Task 4); `Session` (Task 12).
- Produces:
  ```python
  # models.py
  class EnrollRequest(BaseModel):
      patientId: str

  class CompleteVisitRequest(BaseModel):
      transitionChoice: str | None = None

  # deps.py
  SESSION_COOKIE_NAME: str  # "vulcan_soa_session"

  def get_settings(request: Request) -> Settings: ...
  def get_session_store(request: Request) -> InMemoryStore: ...
  def get_pending_launch_store(request: Request) -> InMemoryStore: ...
  def get_current_session(request, session_store=Depends(get_session_store)) -> Session: ...  # 401 if missing/unknown
  async def get_fhir_client(session=Depends(get_current_session), settings=Depends(get_settings)) -> AsyncIterator[FhirClient]: ...
  ```
  All of `models.py` and `deps.py` are used directly by Tasks 14-16 (`api/launch.py`, `api/context.py`, `api/research_studies.py`, `api/research_subjects.py`, `api/app.py`).

- [ ] **Step 1: Write the failing tests**

`backend/tests/api/__init__.py`: (empty file)

`backend/tests/api/test_deps.py`:
```python
import httpx
import respx
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from vulcan_soa.api.deps import SESSION_COOKIE_NAME, get_current_session, get_fhir_client
from vulcan_soa.auth import Session
from vulcan_soa.config import Settings
from vulcan_soa.store import InMemoryStore


def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.state.settings = Settings(
        fhir_base_url="https://aidbox.test/fhir",
        oauth_authorize_url="https://aidbox.test/authorize",
        oauth_token_url="https://aidbox.test/token",
        smart_client_id="client-1",
        smart_client_secret="secret-1",
        redirect_uri="https://app.test/callback",
    )
    app.state.session_store = InMemoryStore()
    app.state.pending_launch_store = InMemoryStore()

    @app.get("/whoami")
    def whoami(session: Session = Depends(get_current_session)):
        return {"patientId": session.patient_id}

    @app.get("/fhir-patient")
    async def fhir_patient(client=Depends(get_fhir_client)):
        return await client.read("Patient", "patient-1")

    return app


def test_get_current_session_returns_401_without_cookie():
    client = TestClient(_build_test_app())
    response = client.get("/whoami")
    assert response.status_code == 401


def test_get_current_session_returns_401_for_unknown_session_id():
    client = TestClient(_build_test_app())
    response = client.get("/whoami", cookies={SESSION_COOKIE_NAME: "does-not-exist"})
    assert response.status_code == 401


def test_get_current_session_succeeds_for_known_session():
    app = _build_test_app()
    session_id = app.state.session_store.create(
        Session(access_token="tok-1", patient_id="patient-1", research_study_id=None)
    )
    client = TestClient(app)

    response = client.get("/whoami", cookies={SESSION_COOKIE_NAME: session_id})

    assert response.status_code == 200
    assert response.json() == {"patientId": "patient-1"}


@respx.mock
def test_get_fhir_client_authorizes_requests_with_session_access_token():
    app = _build_test_app()
    session_id = app.state.session_store.create(
        Session(access_token="tok-1", patient_id="patient-1", research_study_id=None)
    )
    route = respx.get("https://aidbox.test/fhir/Patient/patient-1").mock(
        return_value=httpx.Response(200, json={"resourceType": "Patient", "id": "patient-1"})
    )
    client = TestClient(app)

    response = client.get("/fhir-patient", cookies={SESSION_COOKIE_NAME: session_id})

    assert response.status_code == 200
    assert response.json() == {"resourceType": "Patient", "id": "patient-1"}
    assert route.calls.last.request.headers["Authorization"] == "Bearer tok-1"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/api/test_deps.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vulcan_soa.api'`

- [ ] **Step 3: Write the implementation**

`backend/src/vulcan_soa/api/__init__.py`: (empty file)

`backend/src/vulcan_soa/api/models.py`:
```python
from pydantic import BaseModel


class EnrollRequest(BaseModel):
    patientId: str


class CompleteVisitRequest(BaseModel):
    transitionChoice: str | None = None
```

`backend/src/vulcan_soa/api/deps.py`:
```python
from collections.abc import AsyncIterator

from fastapi import Depends, HTTPException, Request

from vulcan_soa.auth import Session
from vulcan_soa.config import Settings
from vulcan_soa.fhir_client import FhirClient
from vulcan_soa.store import InMemoryStore

SESSION_COOKIE_NAME = "vulcan_soa_session"


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_session_store(request: Request) -> InMemoryStore:
    return request.app.state.session_store


def get_pending_launch_store(request: Request) -> InMemoryStore:
    return request.app.state.pending_launch_store


def get_current_session(
    request: Request, session_store: InMemoryStore = Depends(get_session_store)
) -> Session:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    session = session_store.get(session_id) if session_id else None
    if session is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return session


async def get_fhir_client(
    session: Session = Depends(get_current_session),
    settings: Settings = Depends(get_settings),
) -> AsyncIterator[FhirClient]:
    client = FhirClient(base_url=settings.fhir_base_url, access_token=session.access_token)
    try:
        yield client
    finally:
        await client.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/api/test_deps.py -v`
Expected: `4 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/src/vulcan_soa/api/__init__.py backend/src/vulcan_soa/api/models.py backend/src/vulcan_soa/api/deps.py backend/tests/api/__init__.py backend/tests/api/test_deps.py
git commit -m "Add API request models and shared FastAPI dependencies"
```

---

## Task 14: Launch routes — EHR launch, standalone launch, OAuth callback

The OAuth `state` parameter is never generated separately from the `PendingLaunch` record: storing the `PendingLaunch` in `pending_launch_store` (Task 3) returns an opaque key, and that key is used directly as `state`. This keeps the launch flow as the single place that creates and consumes pending-launch records, and avoids a second, parallel "state" identity that could drift out of sync with the stored record.

**Files:**
- Create: `backend/src/vulcan_soa/api/launch.py`
- Test: `backend/tests/api/test_launch.py`

**Interfaces:**
- Consumes: `Settings`, `get_settings`, `get_pending_launch_store`, `get_session_store`, `SESSION_COOKIE_NAME` (Tasks 2, 13); `PendingLaunch`, `Session`, `generate_pkce_pair`, `build_authorize_url`, `exchange_code_for_token`, `session_from_token_response` (Task 12).
- Produces: `router: APIRouter` with `GET /launch`, `GET /launch/standalone`, `GET /callback`. Task 16 (`api/app.py`) mounts this router.

- [ ] **Step 1: Write the failing tests**

`backend/tests/api/test_launch.py`:
```python
from urllib.parse import parse_qs, urlparse

import httpx
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vulcan_soa.api.deps import SESSION_COOKIE_NAME
from vulcan_soa.api.launch import router as launch_router
from vulcan_soa.config import Settings
from vulcan_soa.store import InMemoryStore


def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.state.settings = Settings(
        fhir_base_url="https://aidbox.test/fhir",
        oauth_authorize_url="https://aidbox.test/authorize",
        oauth_token_url="https://aidbox.test/token",
        smart_client_id="client-1",
        smart_client_secret="secret-1",
        redirect_uri="https://app.test/callback",
        frontend_url="https://app.test",
    )
    app.state.pending_launch_store = InMemoryStore()
    app.state.session_store = InMemoryStore()
    app.include_router(launch_router)
    return app


def test_launch_redirects_to_authorize_url_for_trusted_iss():
    client = TestClient(_build_test_app(), follow_redirects=False)

    response = client.get("/launch", params={"iss": "https://aidbox.test/fhir", "launch": "launch-1"})

    assert response.status_code in (302, 307)
    location = response.headers["location"]
    assert location.startswith("https://aidbox.test/authorize?")
    assert "launch=launch-1" in location


def test_launch_redirects_to_error_page_for_untrusted_iss():
    client = TestClient(_build_test_app(), follow_redirects=False)

    response = client.get("/launch", params={"iss": "https://evil.test/fhir", "launch": "launch-1"})

    assert response.status_code in (302, 307)
    assert response.headers["location"].startswith("https://app.test/launch-error")


def test_launch_standalone_redirects_to_authorize_url_without_launch_param():
    client = TestClient(_build_test_app(), follow_redirects=False)

    response = client.get("/launch/standalone")

    location = response.headers["location"]
    assert location.startswith("https://aidbox.test/authorize?")
    assert "launch=" not in location


@respx.mock
def test_launch_then_callback_round_trip_sets_session_cookie():
    respx.post("https://aidbox.test/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "tok-1",
                "patient": "patient-1",
                "fhirContext": [{"reference": "ResearchStudy/study-1"}],
            },
        )
    )
    app = _build_test_app()
    client = TestClient(app, follow_redirects=False)

    launch_response = client.get(
        "/launch", params={"iss": "https://aidbox.test/fhir", "launch": "launch-1"}
    )
    authorize_location = launch_response.headers["location"]
    state = parse_qs(urlparse(authorize_location).query)["state"][0]

    callback_response = client.get("/callback", params={"code": "code-1", "state": state})

    assert callback_response.status_code in (302, 307)
    assert callback_response.headers["location"] == "https://app.test"
    assert "HttpOnly" in callback_response.headers["set-cookie"]
    session_id = callback_response.cookies[SESSION_COOKIE_NAME]
    session = app.state.session_store.get(session_id)
    assert session.access_token == "tok-1"
    assert session.patient_id == "patient-1"
    assert session.research_study_id == "study-1"


def test_callback_redirects_to_error_page_for_unknown_state():
    client = TestClient(_build_test_app(), follow_redirects=False)

    response = client.get("/callback", params={"code": "code-1", "state": "does-not-exist"})

    assert response.headers["location"].startswith("https://app.test/launch-error")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/api/test_launch.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vulcan_soa.api.launch'`

- [ ] **Step 3: Write the implementation**

`backend/src/vulcan_soa/api/launch.py`:
```python
import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse

from vulcan_soa.api.deps import (
    SESSION_COOKIE_NAME,
    get_pending_launch_store,
    get_session_store,
    get_settings,
)
from vulcan_soa.auth import (
    PendingLaunch,
    build_authorize_url,
    exchange_code_for_token,
    generate_pkce_pair,
    session_from_token_response,
)
from vulcan_soa.config import Settings
from vulcan_soa.store import InMemoryStore

router = APIRouter()


def _start_launch(settings: Settings, pending_launch_store: InMemoryStore, launch: str | None):
    code_verifier, code_challenge = generate_pkce_pair()
    pending = PendingLaunch(code_verifier=code_verifier, launch=launch)
    state = pending_launch_store.create(pending)
    authorize_url = build_authorize_url(settings, pending, state=state, code_challenge=code_challenge)
    return RedirectResponse(authorize_url)


@router.get("/launch")
async def launch(
    iss: str,
    launch: str,
    settings: Settings = Depends(get_settings),
    pending_launch_store: InMemoryStore = Depends(get_pending_launch_store),
):
    if iss != settings.fhir_base_url:
        return RedirectResponse(f"{settings.frontend_url}/launch-error?reason=untrusted_iss")
    return _start_launch(settings, pending_launch_store, launch)


@router.get("/launch/standalone")
async def launch_standalone(
    settings: Settings = Depends(get_settings),
    pending_launch_store: InMemoryStore = Depends(get_pending_launch_store),
):
    return _start_launch(settings, pending_launch_store, None)


@router.get("/callback")
async def callback(
    code: str,
    state: str,
    settings: Settings = Depends(get_settings),
    pending_launch_store: InMemoryStore = Depends(get_pending_launch_store),
    session_store: InMemoryStore = Depends(get_session_store),
):
    pending = pending_launch_store.pop(state)
    if pending is None:
        return RedirectResponse(f"{settings.frontend_url}/launch-error?reason=invalid_state")

    async with httpx.AsyncClient() as http_client:
        token_response = await exchange_code_for_token(
            settings, http_client, code, pending.code_verifier
        )

    session = session_from_token_response(token_response)
    session_id = session_store.create(session)

    response = RedirectResponse(settings.frontend_url)
    response.set_cookie(
        SESSION_COOKIE_NAME,
        session_id,
        httponly=True,
        samesite="lax",
        secure=settings.frontend_url.startswith("https://"),
    )
    return response
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/api/test_launch.py -v`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/src/vulcan_soa/api/launch.py backend/tests/api/test_launch.py
git commit -m "Add SMART launch routes: EHR launch, standalone launch, OAuth callback"
```

---

## Task 15: Context, research-study, and research-subject routes

**Files:**
- Create: `backend/src/vulcan_soa/api/context.py`
- Create: `backend/src/vulcan_soa/api/research_studies.py`
- Create: `backend/src/vulcan_soa/api/research_subjects.py`
- Test: `backend/tests/api/test_context.py`
- Test: `backend/tests/api/test_research_studies.py`
- Test: `backend/tests/api/test_research_subjects.py`

**Interfaces:**
- Consumes: `get_current_session`, `get_fhir_client` (Task 13); `EnrollRequest`, `CompleteVisitRequest` (Task 13); `enroll` (Task 10); `complete_visit`, `withdraw_subject` (Task 11); `load_protocol_graph_for_subject`, `load_subject_context`, `schedule_response` (Task 9); `resolve_schedule_state` (Task 8).
- Produces: three `router: APIRouter` objects. Task 16 (`api/app.py`) mounts all three.

- [ ] **Step 1: Write the failing tests**

`backend/tests/api/test_context.py`:
```python
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vulcan_soa.api.context import router as context_router
from vulcan_soa.api.deps import get_current_session
from vulcan_soa.auth import Session


def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(context_router)
    return app


def test_get_context_returns_401_without_session():
    client = TestClient(_build_test_app())
    response = client.get("/api/context")
    assert response.status_code == 401


def test_get_context_returns_patient_and_research_study_ids():
    app = _build_test_app()
    app.dependency_overrides[get_current_session] = lambda: Session(
        access_token="tok-1", patient_id="patient-1", research_study_id="study-1"
    )
    client = TestClient(app)

    response = client.get("/api/context")

    assert response.status_code == 200
    assert response.json() == {"patientId": "patient-1", "researchStudyId": "study-1"}
```

`backend/tests/api/test_research_studies.py`:
```python
import httpx
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vulcan_soa.api.deps import get_fhir_client
from vulcan_soa.api.research_studies import router as research_studies_router
from vulcan_soa.fhir_client import FhirClient


def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(research_studies_router)
    return app


@respx.mock
def test_list_research_studies_returns_id_and_title():
    respx.get("https://aidbox.test/fhir/ResearchStudy").mock(
        return_value=httpx.Response(
            200,
            json={
                "resourceType": "Bundle",
                "entry": [
                    {
                        "resource": {
                            "resourceType": "ResearchStudy",
                            "id": "study-1",
                            "title": "UC1 Demo Study",
                        }
                    }
                ],
            },
        )
    )
    app = _build_test_app()
    app.dependency_overrides[get_fhir_client] = lambda: FhirClient(
        base_url="https://aidbox.test/fhir", access_token="tok-1"
    )
    test_client = TestClient(app)

    response = test_client.get("/api/research-studies")

    assert response.status_code == 200
    assert response.json() == [{"id": "study-1", "title": "UC1 Demo Study"}]


@respx.mock
def test_enroll_patient_calls_enrollment_and_returns_schedule():
    respx.get("https://aidbox.test/fhir/ResearchStudy/study-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "resourceType": "ResearchStudy",
                "id": "study-1",
                "protocol": [{"reference": "PlanDefinition/plan-1"}],
            },
        )
    )
    respx.get("https://aidbox.test/fhir/PlanDefinition/plan-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "resourceType": "PlanDefinition",
                "id": "plan-1",
                "action": [{"id": "screening-1", "title": "Screening"}],
            },
        )
    )
    respx.get("https://aidbox.test/fhir/ResearchSubject").mock(
        return_value=httpx.Response(200, json={"resourceType": "Bundle"})
    )
    respx.post("https://aidbox.test/fhir/ResearchSubject").mock(
        return_value=httpx.Response(201, json={"resourceType": "ResearchSubject", "id": "subj-1"})
    )
    respx.post("https://aidbox.test/fhir/Encounter").mock(
        return_value=httpx.Response(201, json={"resourceType": "Encounter", "id": "enc-1"})
    )

    app = _build_test_app()
    app.dependency_overrides[get_fhir_client] = lambda: FhirClient(
        base_url="https://aidbox.test/fhir", access_token="tok-1"
    )
    test_client = TestClient(app)

    response = test_client.post(
        "/api/research-studies/study-1/enroll", json={"patientId": "patient-1"}
    )

    assert response.status_code == 200
    assert response.json()["researchSubjectId"] == "subj-1"
```

`backend/tests/api/test_research_subjects.py`:
```python
import httpx
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from vulcan_soa.api.deps import get_fhir_client
from vulcan_soa.api.research_subjects import router as research_subjects_router
from vulcan_soa.fhir_client import FhirClient

SUBJECT = {
    "resourceType": "ResearchSubject",
    "id": "subj-1",
    "subjectState": {"coding": [{"code": "on-study"}]},
    "study": {"reference": "ResearchStudy/study-1"},
    "subject": {"reference": "Patient/patient-1"},
}
STUDY = {
    "resourceType": "ResearchStudy",
    "id": "study-1",
    "protocol": [{"reference": "PlanDefinition/plan-1"}],
}
PLAN_DEFINITION = {
    "resourceType": "PlanDefinition",
    "id": "plan-1",
    "action": [{"id": "screening-1", "title": "Screening"}],
}


def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(research_subjects_router)
    return app


@respx.mock
def test_get_schedule_returns_resolved_state():
    respx.get("https://aidbox.test/fhir/ResearchSubject/subj-1").mock(
        return_value=httpx.Response(200, json=SUBJECT)
    )
    respx.get("https://aidbox.test/fhir/ResearchStudy/study-1").mock(
        return_value=httpx.Response(200, json=STUDY)
    )
    respx.get("https://aidbox.test/fhir/PlanDefinition/plan-1").mock(
        return_value=httpx.Response(200, json=PLAN_DEFINITION)
    )
    respx.get("https://aidbox.test/fhir/Encounter").mock(
        return_value=httpx.Response(200, json={"resourceType": "Bundle"})
    )

    app = _build_test_app()
    app.dependency_overrides[get_fhir_client] = lambda: FhirClient(
        base_url="https://aidbox.test/fhir", access_token="tok-1"
    )
    test_client = TestClient(app)

    response = test_client.get("/api/research-subjects/subj-1/schedule")

    assert response.status_code == 200
    assert response.json()["nextSteps"] == [
        {"actionId": "screening-1", "title": "Screening", "transitionType": None}
    ]


@respx.mock
def test_withdraw_route_updates_subject_state():
    respx.get("https://aidbox.test/fhir/ResearchSubject/subj-1").mock(
        return_value=httpx.Response(200, json=dict(SUBJECT, meta={"versionId": "1"}))
    )
    respx.put("https://aidbox.test/fhir/ResearchSubject/subj-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "resourceType": "ResearchSubject",
                "id": "subj-1",
                "subjectState": {"coding": [{"code": "withdrawn"}]},
            },
        )
    )

    app = _build_test_app()
    app.dependency_overrides[get_fhir_client] = lambda: FhirClient(
        base_url="https://aidbox.test/fhir", access_token="tok-1"
    )
    test_client = TestClient(app)

    response = test_client.post("/api/research-subjects/subj-1/withdraw")

    assert response.status_code == 200
    assert response.json() == {"id": "subj-1", "subjectState": "withdrawn"}


@respx.mock
def test_complete_visit_route_marks_finished_and_returns_schedule():
    respx.get("https://aidbox.test/fhir/ResearchSubject/subj-1").mock(
        return_value=httpx.Response(200, json=SUBJECT)
    )
    respx.get("https://aidbox.test/fhir/ResearchStudy/study-1").mock(
        return_value=httpx.Response(200, json=STUDY)
    )
    respx.get("https://aidbox.test/fhir/PlanDefinition/plan-1").mock(
        return_value=httpx.Response(200, json=PLAN_DEFINITION)
    )
    encounter = {
        "resourceType": "Encounter",
        "id": "enc-1",
        "status": "planned",
        "identifier": [{"system": "urn:vulcan-soa:plan-action", "value": "plan-1#screening-1"}],
    }
    respx.get("https://aidbox.test/fhir/Encounter").mock(
        return_value=httpx.Response(
            200, json={"resourceType": "Bundle", "entry": [{"resource": encounter}]}
        )
    )
    respx.put("https://aidbox.test/fhir/Encounter/enc-1").mock(
        return_value=httpx.Response(200, json=dict(encounter, status="finished"))
    )

    app = _build_test_app()
    app.dependency_overrides[get_fhir_client] = lambda: FhirClient(
        base_url="https://aidbox.test/fhir", access_token="tok-1"
    )
    test_client = TestClient(app)

    response = test_client.post(
        "/api/research-subjects/subj-1/visits/screening-1/complete", json={"transitionChoice": None}
    )

    assert response.status_code == 200
    assert response.json()["completed"] == ["screening-1"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/api/test_context.py tests/api/test_research_studies.py tests/api/test_research_subjects.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vulcan_soa.api.context'`

- [ ] **Step 3: Write the implementation**

`backend/src/vulcan_soa/api/context.py`:
```python
from fastapi import APIRouter, Depends

from vulcan_soa.api.deps import get_current_session
from vulcan_soa.auth import Session

router = APIRouter(prefix="/api")


@router.get("/context")
async def get_context(session: Session = Depends(get_current_session)) -> dict:
    return {"patientId": session.patient_id, "researchStudyId": session.research_study_id}
```

`backend/src/vulcan_soa/api/research_studies.py`:
```python
from fastapi import APIRouter, Depends

from vulcan_soa.api.deps import get_fhir_client
from vulcan_soa.api.models import EnrollRequest
from vulcan_soa.enrollment import enroll
from vulcan_soa.fhir_client import FhirClient

router = APIRouter(prefix="/api/research-studies")


@router.get("")
async def list_research_studies(client: FhirClient = Depends(get_fhir_client)) -> list[dict]:
    studies = await client.search("ResearchStudy", {})
    return [
        {"id": study["id"], "title": study.get("title", study["id"])} for study in studies
    ]


@router.post("/{study_id}/enroll")
async def enroll_patient(
    study_id: str, body: EnrollRequest, client: FhirClient = Depends(get_fhir_client)
) -> dict:
    return await enroll(client, study_id, body.patientId)
```

`backend/src/vulcan_soa/api/research_subjects.py`:
```python
from fastapi import APIRouter, Depends

from vulcan_soa.api.deps import get_fhir_client
from vulcan_soa.api.models import CompleteVisitRequest
from vulcan_soa.fhir_client import FhirClient
from vulcan_soa.scheduling import (
    load_protocol_graph_for_subject,
    load_subject_context,
    schedule_response,
)
from vulcan_soa.soa_engine.engine import resolve_schedule_state
from vulcan_soa.tracking import complete_visit, withdraw_subject

router = APIRouter(prefix="/api/research-subjects")


@router.get("/{subject_id}/schedule")
async def get_schedule(subject_id: str, client: FhirClient = Depends(get_fhir_client)) -> dict:
    subject = await client.read("ResearchSubject", subject_id)
    graph, plan_definition_id = await load_protocol_graph_for_subject(client, subject)
    context, _ = await load_subject_context(client, subject, plan_definition_id)
    state = resolve_schedule_state(graph, context)
    return schedule_response(state)


@router.post("/{subject_id}/visits/{action_id}/complete")
async def complete_visit_route(
    subject_id: str,
    action_id: str,
    body: CompleteVisitRequest,
    client: FhirClient = Depends(get_fhir_client),
) -> dict:
    return await complete_visit(client, subject_id, action_id, body.transitionChoice)


@router.post("/{subject_id}/withdraw")
async def withdraw_route(subject_id: str, client: FhirClient = Depends(get_fhir_client)) -> dict:
    return await withdraw_subject(client, subject_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/api/test_context.py tests/api/test_research_studies.py tests/api/test_research_subjects.py -v`
Expected: `9 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/src/vulcan_soa/api/context.py backend/src/vulcan_soa/api/research_studies.py backend/src/vulcan_soa/api/research_subjects.py backend/tests/api/test_context.py backend/tests/api/test_research_studies.py backend/tests/api/test_research_subjects.py
git commit -m "Add context, research-study, and research-subject API routes"
```

---

## Task 16: App factory — wiring, CORS, and the uvicorn entrypoint

`create_app()` takes an optional `Settings` so tests can construct a fully isolated app (own `Settings`, own `InMemoryStore`s) without touching environment variables or a real `.env.local` file. The bare module-level `app = create_app()` — used only by `uvicorn vulcan_soa.api.app:app` — does call `Settings()` with no arguments, which requires a real `.env.local` (or `.env.connectathon`, via `ENV_FILE`) to exist (Task 2). No test in this plan imports or exercises that module-level `app`; every test builds its own app via `create_app(settings=...)`.

**Files:**
- Create: `backend/src/vulcan_soa/api/app.py`
- Test: `backend/tests/api/test_app.py`

**Interfaces:**
- Consumes: `Settings` (Task 2); `InMemoryStore` (Task 3); all four routers (`launch`, `context`, `research_studies`, `research_subjects`) from Tasks 14-15.
- Produces: `def create_app(settings: Settings | None = None) -> FastAPI` and module-level `app`. This is the entrypoint Task 17's integration test and `uvicorn` both run against.

- [ ] **Step 1: Write the failing tests**

`backend/tests/api/test_app.py`:
```python
from fastapi.testclient import TestClient

from vulcan_soa.api.app import create_app
from vulcan_soa.config import Settings


def _test_settings() -> Settings:
    return Settings(
        fhir_base_url="https://aidbox.test/fhir",
        oauth_authorize_url="https://aidbox.test/authorize",
        oauth_token_url="https://aidbox.test/token",
        smart_client_id="client-1",
        smart_client_secret="secret-1",
        redirect_uri="https://app.test/callback",
        frontend_url="https://app.test",
    )


def test_create_app_returns_401_on_context_without_session_cookie():
    client = TestClient(create_app(settings=_test_settings()))

    response = client.get("/api/context")

    assert response.status_code == 401


def test_create_app_mounts_launch_routes():
    client = TestClient(create_app(settings=_test_settings()), follow_redirects=False)

    response = client.get("/launch/standalone")

    assert response.status_code in (302, 307)


def test_create_app_sets_cors_allow_origin_for_frontend_url():
    client = TestClient(create_app(settings=_test_settings()))

    response = client.options(
        "/api/context",
        headers={"Origin": "https://app.test", "Access-Control-Request-Method": "GET"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://app.test"
    assert response.headers["access-control-allow-credentials"] == "true"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/api/test_app.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'vulcan_soa.api.app'`

- [ ] **Step 3: Write the implementation**

`backend/src/vulcan_soa/api/app.py`:
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from vulcan_soa.api.context import router as context_router
from vulcan_soa.api.launch import router as launch_router
from vulcan_soa.api.research_studies import router as research_studies_router
from vulcan_soa.api.research_subjects import router as research_subjects_router
from vulcan_soa.config import Settings
from vulcan_soa.store import InMemoryStore


def create_app(settings: Settings | None = None) -> FastAPI:
    app = FastAPI(title="Vulcan SoA")
    app.state.settings = settings or Settings()
    app.state.session_store = InMemoryStore()
    app.state.pending_launch_store = InMemoryStore()

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[app.state.settings.frontend_url],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(launch_router)
    app.include_router(context_router)
    app.include_router(research_studies_router)
    app.include_router(research_subjects_router)

    return app


app = create_app()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/api/test_app.py -v`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add backend/src/vulcan_soa/api/app.py backend/tests/api/test_app.py
git commit -m "Add create_app() factory wiring routers, CORS, and per-app state"
```

---

## Task 17: Backend golden-path integration test

End-to-end proof, against a **real local Aidbox**, of the design's required golden path: enroll → view schedule → complete a visit → see the next suggested step → withdraw → see the ambiguous decision-support prompt. Every earlier task tested its own module against mocked HTTP; this task is the one place that calls the real domain functions back-to-back against real Aidbox state, using the exact Use Case 1 fixture graph confirmed in Task 6 (`Screening` → `Treatment Day 1` → `Day 7`/`End of Study` → `Day 15`/`End of Study` → `End of Study` → `Follow Up`, with the withdraw condition gating both `Treatment Day 1 → End of Study` and `Day 7 → End of Study`).

This test requires a running local Aidbox with the IG content and this plan's own fixtures already loaded (Task 5, Steps 6-7) — it is gated behind an environment variable so it never runs as part of routine `pytest` invocations in this plan's other tasks or in CI without explicit opt-in.

**Files:**
- Create: `backend/tests/test_golden_path_integration.py`

**Interfaces:**
- Consumes: `Settings` (Task 2); `FhirClient` (Task 4); `load_directory` (Task 5); `parse_protocol_graph` (Task 6, unused directly but documents the graph this test walks); `enroll` (Task 10); `withdraw_subject`, `complete_visit` (Task 11).
- Produces: nothing consumed by later tasks — this is a leaf/terminal test.

- [ ] **Step 1: Write the test**

`backend/tests/test_golden_path_integration.py`:
```python
import os
from pathlib import Path

import pytest

from scripts.load_fixtures import load_directory
from vulcan_soa.config import Settings
from vulcan_soa.enrollment import enroll
from vulcan_soa.fhir_client import FhirClient
from vulcan_soa.tracking import complete_visit, withdraw_subject

IG_OUTPUT_DIR = Path(
    os.environ.get(
        "VULCAN_IG_OUTPUT_DIR",
        "/Users/GLW1/Documents/Devel/hl7/Vulcan-schedule-ig/output",
    )
)
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"

STUDY_ID = "uc1-demo-research-study"
PATIENT_ID = "uc1-demo-patient"

SCREENING_ID = "0700e721-1f12-4998-89b8-6f4e649b62f7"
TREATMENT_DAY1_ID = "a1806239-54f3-4762-af3f-edb9d80d29dc"
DAY7_ID = "349447c3-8ad4-4034-8c31-c3d96dcc5f9a"
EOS_ID = "dbc35dee-a5f2-473f-b9b1-bb14b2a1c9ef"

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="requires a real local Aidbox with the IG and this plan's fixtures loaded; set RUN_INTEGRATION_TESTS=1 to run",
)


@pytest.fixture
async def client():
    settings = Settings()
    fhir_client = FhirClient(
        base_url=settings.fhir_base_url,
        basic_auth=(settings.smart_client_id, settings.smart_client_secret),
    )
    await load_directory(fhir_client, IG_OUTPUT_DIR)
    await load_directory(fhir_client, FIXTURES_DIR)
    yield fhir_client
    await fhir_client.close()


async def test_golden_path_enroll_progress_withdraw_ambiguous(client):
    enroll_result = await enroll(client, STUDY_ID, PATIENT_ID)
    subject_id = enroll_result["researchSubjectId"]
    assert enroll_result["schedule"]["nextSteps"] == []

    after_screening = await complete_visit(client, subject_id, SCREENING_ID, None)
    assert [s["actionId"] for s in after_screening["nextSteps"]] == [TREATMENT_DAY1_ID]
    assert after_screening["ambiguous"] is False

    await withdraw_subject(client, subject_id)

    after_treatment_day1 = await complete_visit(client, subject_id, TREATMENT_DAY1_ID, None)
    target_ids = {s["actionId"] for s in after_treatment_day1["nextSteps"]}
    assert target_ids == {DAY7_ID, EOS_ID}
    assert after_treatment_day1["ambiguous"] is True
```

Note: `enroll`/`complete_visit` are idempotent against re-runs of this test — `enroll` uses `conditional_create` keyed on `(study, subject)`, so re-running against the same Aidbox finds the existing `ResearchSubject` rather than creating a duplicate, and completing an already-finished visit just re-marks it finished and recomputes next steps, which is harmless. The withdrawal happens *between* completing Screening and completing Treatment Day 1: Treatment Day 1's two outgoing transitions are `Day 7` (unconditional) and `End of Study` (only valid when withdrawn) — so once the subject is withdrawn, completing Treatment Day 1 makes both targets simultaneously valid with no automatic signal to prefer one, which is exactly the required decision-support surface from the design's error-handling rules. `transition_choice` is passed as `None` here deliberately: the whole point of this assertion is that the backend returns the ambiguity for a human to resolve rather than auto-selecting either path.

- [ ] **Step 2: Run it against a real local Aidbox**

With local Aidbox running, `backend/.env.local` filled in, and Task 5's Steps 6-7 already confirmed working:

```bash
cd backend
source .venv/bin/activate
export ENV_FILE=.env.local
export RUN_INTEGRATION_TESTS=1
pytest tests/test_golden_path_integration.py -v
```

Expected: `1 passed`. If it fails, the failure is informative about real Aidbox/R6 behavior (e.g. a resource shape Aidbox rejects that the mocked unit tests couldn't catch) — fix the underlying domain code, not this test, unless the test's assumption about the fixture graph itself is wrong.

- [ ] **Step 3: Run the full backend suite to confirm the skip-gate works without the env var**

```bash
cd backend
unset RUN_INTEGRATION_TESTS
pytest -v
```

Expected: every other test from Tasks 1-16 passes, and `test_golden_path_integration.py::test_golden_path_enroll_progress_withdraw_ambiguous` reports `SKIPPED` (not run, not failed) — confirming the rest of this plan's test suite never depends on a live Aidbox.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_golden_path_integration.py
git commit -m "Add golden-path integration test against real Aidbox, gated behind RUN_INTEGRATION_TESTS"
```

---

## Task 18: Frontend project scaffold

Vite + React + TypeScript, with Vitest/Testing Library wired up for component tests and a dev-server proxy so the browser sees the SPA and the FastAPI backend as a single origin — required for the session cookie (Task 14's `SameSite=Lax`, `HttpOnly` cookie) to survive in dev, since the Vite dev server runs on `:5173` and the backend on `:8000`.

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/index.html`
- Create: `frontend/.gitignore`
- Create: `frontend/src/setupTests.ts`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/routes.tsx` (minimal placeholder; replaced in Task 23)
- Create: `frontend/src/App.tsx`
- Test: `frontend/src/App.test.tsx`

**Interfaces:**
- Produces: a working `npm test` (Vitest) and `npm run dev` (Vite, proxying `/api`, `/launch`, `/callback` to `http://localhost:8000`) for every later frontend task. `App.tsx` renders `<AppRoutes />` from `routes.tsx`, which Task 23 replaces with real routing — every other frontend task between now and then only adds new files under `src/api/`, `src/launch/`, or `src/views/`, none of which `routes.tsx` references yet.

- [ ] **Step 1: Create `package.json`**

`frontend/package.json`:
```json
{
  "name": "vulcan-soa-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "test": "vitest run",
    "test:e2e": "playwright test"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.26.2"
  },
  "devDependencies": {
    "@playwright/test": "^1.47.2",
    "@testing-library/jest-dom": "^6.5.0",
    "@testing-library/react": "^16.0.1",
    "@testing-library/user-event": "^14.5.2",
    "@types/react": "^18.3.9",
    "@types/react-dom": "^18.3.0",
    "@vitejs/plugin-react": "^4.3.2",
    "jsdom": "^25.0.1",
    "typescript": "^5.6.2",
    "vite": "^5.4.8",
    "vitest": "^2.1.2"
  }
}
```

- [ ] **Step 2: Create `vite.config.ts`**

`frontend/vite.config.ts`:
```ts
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
      "/launch": "http://localhost:8000",
      "/callback": "http://localhost:8000",
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/setupTests.ts"],
  },
});
```

Without this proxy, the browser would see the SPA at `http://localhost:5173` and the backend at `http://localhost:8000` as cross-site, and a `SameSite=Lax` cookie set by the backend's `/callback` redirect (Task 14) would not be sent back on the SPA's `fetch("/api/...")` calls. The proxy makes every request the browser issues look same-origin to `localhost:5173`, which Vite forwards server-side.

- [ ] **Step 3: Create `tsconfig.json`**

`frontend/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true
  },
  "include": ["src", "e2e"]
}
```

- [ ] **Step 4: Create `index.html`**

`frontend/index.html`:
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <title>Vulcan Schedule of Activities</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 5: Create `.gitignore`**

`frontend/.gitignore`:
```
node_modules/
dist/
playwright-report/
test-results/
```

- [ ] **Step 6: Create `setupTests.ts`**

`frontend/src/setupTests.ts`:
```ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 7: Create the placeholder `routes.tsx`**

`frontend/src/routes.tsx`:
```tsx
import { Route, Routes } from "react-router-dom";

function Placeholder() {
  return <p>Coming soon.</p>;
}

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Placeholder />} />
    </Routes>
  );
}
```

Task 23 replaces this with the real landing/launch-error/enroll/subject-dashboard route tree, once all the views it routes to exist.

- [ ] **Step 8: Write the failing smoke test**

`frontend/src/App.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";

import App from "./App";

describe("App", () => {
  it("renders the app header", () => {
    render(
      <MemoryRouter>
        <App />
      </MemoryRouter>,
    );

    expect(screen.getByRole("heading", { name: "Vulcan Schedule of Activities" })).toBeInTheDocument();
  });
});
```

- [ ] **Step 9: Run the test to verify it fails**

Run: `cd frontend && npm install && npm test`
Expected: FAIL — `Cannot find module './App'` (or similar; `App.tsx` does not exist yet)

- [ ] **Step 10: Create `App.tsx` and `main.tsx`**

`frontend/src/App.tsx`:
```tsx
import AppRoutes from "./routes";

export default function App() {
  return (
    <div>
      <header>
        <h1>Vulcan Schedule of Activities</h1>
      </header>
      <main>
        <AppRoutes />
      </main>
    </div>
  );
}
```

`frontend/src/main.tsx`:
```tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
);
```

- [ ] **Step 11: Run the test to verify it passes**

Run: `cd frontend && npm test`
Expected: `1 passed` (or Vitest's equivalent summary, e.g. `Test Files  1 passed (1)` / `Tests  1 passed (1)`)

- [ ] **Step 12: Run the dev server by hand and confirm the proxy works**

```bash
cd frontend
npm run dev
```
With the backend also running (`uvicorn vulcan_soa.api.app:app --reload` from `backend/`, `ENV_FILE=.env.local`), open `http://localhost:5173` and confirm the page renders the header. This is the first point where backend and frontend run together — note any proxy/CORS errors in the browser console now, rather than discovering them later.

- [ ] **Step 13: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/vite.config.ts frontend/tsconfig.json frontend/index.html frontend/.gitignore frontend/src/setupTests.ts frontend/src/routes.tsx frontend/src/App.tsx frontend/src/App.test.tsx frontend/src/main.tsx
git commit -m "Scaffold frontend Vite/React/TS project with a dev-server proxy to the backend"
```

---

## Task 19: Typed API client

The single point of contact between the SPA and the backend's JSON API (Tasks 13-16). Every later frontend task (views) imports from here, never calls `fetch` directly — this keeps the exact request/response shapes (camelCase keys, `credentials: "include"` so the session cookie is sent) in one place.

**Files:**
- Create: `frontend/src/api/types.ts`
- Create: `frontend/src/api/client.ts`
- Test: `frontend/src/api/client.test.ts`

**Interfaces:**
- Consumes: nothing from earlier frontend tasks; mirrors the backend response shapes from Tasks 13, 15 exactly (`GET /api/context`, `GET /api/research-studies`, `POST /api/research-studies/{id}/enroll`, `GET /api/research-subjects/{id}/schedule`, `POST /api/research-subjects/{id}/visits/{actionId}/complete`, `POST /api/research-subjects/{id}/withdraw`).
- Produces:
  ```ts
  // types.ts
  export interface Context { patientId: string | null; researchStudyId: string | null; }
  export interface ResearchStudySummary { id: string; title: string; }
  export interface NextStep { actionId: string; title: string; transitionType: string | null; }
  export interface Schedule { completed: string[]; current: string[]; nextSteps: NextStep[]; ambiguous: boolean; }
  export interface EnrollResult { researchSubjectId: string; schedule: Schedule; }
  export interface WithdrawResult { id: string; subjectState: string; }

  // client.ts
  export function getContext(): Promise<Context>;
  export function listResearchStudies(): Promise<ResearchStudySummary[]>;
  export function enrollPatient(studyId: string, patientId: string): Promise<EnrollResult>;
  export function getSchedule(subjectId: string): Promise<Schedule>;
  export function completeVisit(subjectId: string, actionId: string, transitionChoice: string | null): Promise<Schedule>;
  export function withdrawSubject(subjectId: string): Promise<WithdrawResult>;
  ```
  Tasks 20-23 (`launch/`, `views/StudyWorklist`, `views/Enroll`, `views/SubjectDashboard`, `routes.tsx`) import all six functions and every type above.

- [ ] **Step 1: Write the failing tests**

`frontend/src/api/client.test.ts`:
```ts
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  completeVisit,
  enrollPatient,
  getContext,
  getSchedule,
  listResearchStudies,
  withdrawSubject,
} from "./client";

function mockFetchOnce(body: unknown, ok = true, status = 200) {
  const response = { ok, status, json: () => Promise.resolve(body) } as Response;
  vi.mocked(fetch).mockResolvedValueOnce(response);
  return response;
}

describe("api client", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("getContext calls GET /api/context with credentials included", async () => {
    mockFetchOnce({ patientId: "patient-1", researchStudyId: null });

    const context = await getContext();

    expect(context).toEqual({ patientId: "patient-1", researchStudyId: null });
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/context");
    expect(init?.credentials).toBe("include");
  });

  it("listResearchStudies calls GET /api/research-studies", async () => {
    mockFetchOnce([{ id: "study-1", title: "UC1 Demo Study" }]);

    const studies = await listResearchStudies();

    expect(studies).toEqual([{ id: "study-1", title: "UC1 Demo Study" }]);
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/research-studies");
  });

  it("enrollPatient posts the patientId as JSON", async () => {
    mockFetchOnce({
      researchSubjectId: "subj-1",
      schedule: { completed: [], current: [], nextSteps: [], ambiguous: false },
    });

    const result = await enrollPatient("study-1", "patient-1");

    expect(result.researchSubjectId).toBe("subj-1");
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/research-studies/study-1/enroll");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(init?.body as string)).toEqual({ patientId: "patient-1" });
  });

  it("getSchedule calls GET /api/research-subjects/{id}/schedule", async () => {
    mockFetchOnce({ completed: [], current: [], nextSteps: [], ambiguous: false });

    await getSchedule("subj-1");

    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/research-subjects/subj-1/schedule");
  });

  it("completeVisit posts the transition choice", async () => {
    mockFetchOnce({ completed: [], current: [], nextSteps: [], ambiguous: false });

    await completeVisit("subj-1", "action-1", "day7-1");

    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/research-subjects/subj-1/visits/action-1/complete");
    expect(JSON.parse(init?.body as string)).toEqual({ transitionChoice: "day7-1" });
  });

  it("withdrawSubject posts to the withdraw endpoint", async () => {
    mockFetchOnce({ id: "subj-1", subjectState: "withdrawn" });

    const result = await withdrawSubject("subj-1");

    expect(result).toEqual({ id: "subj-1", subjectState: "withdrawn" });
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/research-subjects/subj-1/withdraw");
    expect(init?.method).toBe("POST");
  });

  it("throws when the response is not ok", async () => {
    mockFetchOnce({}, false, 401);

    await expect(getContext()).rejects.toThrow();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test -- src/api/client.test.ts`
Expected: FAIL — `Cannot find module './client'`

- [ ] **Step 3: Write `types.ts`**

`frontend/src/api/types.ts`:
```ts
export interface Context {
  patientId: string | null;
  researchStudyId: string | null;
}

export interface ResearchStudySummary {
  id: string;
  title: string;
}

export interface NextStep {
  actionId: string;
  title: string;
  transitionType: string | null;
}

export interface Schedule {
  completed: string[];
  current: string[];
  nextSteps: NextStep[];
  ambiguous: boolean;
}

export interface EnrollResult {
  researchSubjectId: string;
  schedule: Schedule;
}

export interface WithdrawResult {
  id: string;
  subjectState: string;
}
```

- [ ] **Step 4: Write `client.ts`**

`frontend/src/api/client.ts`:
```ts
import type {
  Context,
  EnrollResult,
  NextStep,
  ResearchStudySummary,
  Schedule,
  WithdrawResult,
} from "./types";

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { ...init, credentials: "include" });
  if (!response.ok) {
    throw new Error(`Request to ${url} failed with status ${response.status}`);
  }
  return (await response.json()) as T;
}

function postJson<T>(url: string, body: unknown): Promise<T> {
  return request<T>(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function getContext(): Promise<Context> {
  return request<Context>("/api/context");
}

export function listResearchStudies(): Promise<ResearchStudySummary[]> {
  return request<ResearchStudySummary[]>("/api/research-studies");
}

export function enrollPatient(studyId: string, patientId: string): Promise<EnrollResult> {
  return postJson<EnrollResult>(`/api/research-studies/${studyId}/enroll`, { patientId });
}

export function getSchedule(subjectId: string): Promise<Schedule> {
  return request<Schedule>(`/api/research-subjects/${subjectId}/schedule`);
}

export function completeVisit(
  subjectId: string,
  actionId: string,
  transitionChoice: string | null,
): Promise<Schedule> {
  return postJson<Schedule>(`/api/research-subjects/${subjectId}/visits/${actionId}/complete`, {
    transitionChoice,
  });
}

export function withdrawSubject(subjectId: string): Promise<WithdrawResult> {
  return postJson<WithdrawResult>(`/api/research-subjects/${subjectId}/withdraw`, undefined);
}

export type { NextStep };
```

`withdrawSubject` calls `postJson(url, undefined)`: `JSON.stringify(undefined)` evaluates to `undefined`, so `fetch`'s `body` ends up `undefined` too — i.e. no body is actually sent, which matches `POST /api/research-subjects/{id}/withdraw` (Task 15) taking no request body. The `Content-Type: application/json` header is still sent but harmless since there's nothing for the backend to parse.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npm test -- src/api/client.test.ts`
Expected: `7 passed`

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/api/client.ts frontend/src/api/client.test.ts
git commit -m "Add typed API client for the backend's JSON endpoints"
```

---

## Task 20: `StudyWorklist` view

The general entry point when a launch carries neither a `patient` nor a `researchStudyId` (a standalone launch): browse available `ResearchStudy`s and pick one to enroll into.

**Files:**
- Create: `frontend/src/views/StudyWorklist/StudyWorklist.tsx`
- Test: `frontend/src/views/StudyWorklist/StudyWorklist.test.tsx`

**Interfaces:**
- Consumes: `listResearchStudies`, `ResearchStudySummary` (Task 19).
- Produces: default-exported `StudyWorklist` component, rendering a `Link` to `/enroll/:studyId` per study. Task 23 (`routes.tsx`) renders this at `/` when there's no launch context.

- [ ] **Step 1: Write the failing tests**

`frontend/src/views/StudyWorklist/StudyWorklist.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { listResearchStudies } from "../../api/client";
import StudyWorklist from "./StudyWorklist";

vi.mock("../../api/client");

describe("StudyWorklist", () => {
  beforeEach(() => {
    vi.mocked(listResearchStudies).mockReset();
  });

  it("renders a link to enroll for each study", async () => {
    vi.mocked(listResearchStudies).mockResolvedValue([
      { id: "study-1", title: "UC1 Demo Study" },
    ]);

    render(
      <MemoryRouter>
        <StudyWorklist />
      </MemoryRouter>,
    );

    const link = await screen.findByRole("link", { name: "UC1 Demo Study" });
    expect(link).toHaveAttribute("href", "/enroll/study-1");
  });

  it("shows an error message when the studies request fails", async () => {
    vi.mocked(listResearchStudies).mockRejectedValue(new Error("network error"));

    render(
      <MemoryRouter>
        <StudyWorklist />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load research studies.");
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test -- src/views/StudyWorklist/StudyWorklist.test.tsx`
Expected: FAIL — `Cannot find module './StudyWorklist'`

- [ ] **Step 3: Write the implementation**

`frontend/src/views/StudyWorklist/StudyWorklist.tsx`:
```tsx
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { listResearchStudies } from "../../api/client";
import type { ResearchStudySummary } from "../../api/types";

export default function StudyWorklist() {
  const [studies, setStudies] = useState<ResearchStudySummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listResearchStudies()
      .then(setStudies)
      .catch(() => setError("Could not load research studies."));
  }, []);

  if (error) {
    return <p role="alert">{error}</p>;
  }

  if (studies === null) {
    return <p>Loading studies…</p>;
  }

  if (studies.length === 0) {
    return <p>No research studies are available yet.</p>;
  }

  return (
    <ul>
      {studies.map((study) => (
        <li key={study.id}>
          <Link to={`/enroll/${study.id}`}>{study.title}</Link>
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm test -- src/views/StudyWorklist/StudyWorklist.test.tsx`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/StudyWorklist/StudyWorklist.tsx frontend/src/views/StudyWorklist/StudyWorklist.test.tsx
git commit -m "Add StudyWorklist view listing research studies to enroll into"
```

---

## Task 21: `Enroll` view

Enrolls a patient into the study named by the `:studyId` route param. The backend (Task 13's `EnrollRequest`) takes a raw `patientId: str` with no lookup of its own, and there is no patient-search endpoint anywhere in this plan's API surface (Tasks 13-16) — by design, this app only ever learns a patient id from two places: the SMART launch's `patient` context, or a coordinator typing one in directly. So this view has two modes:

- **EHR launch with patient context** (`GET /api/context` returned a non-null `patientId`): show that patient id directly, no input needed — this is the common case for a coordinator working from a patient's chart.
- **Standalone launch via the study worklist** (`patientId` is `null`): show a plain text input for a Patient FHIR id, since there's nothing to search against. This is a deliberate V1 limitation, not a placeholder — adding real patient search would mean adding a new backend endpoint, which is out of scope for this plan (see Global Constraints).

**Files:**
- Create: `frontend/src/views/Enroll/Enroll.tsx`
- Test: `frontend/src/views/Enroll/Enroll.test.tsx`

**Interfaces:**
- Consumes: `getContext`, `enrollPatient` (Task 19).
- Produces: default-exported `Enroll` component, reading `:studyId` from the route, navigating to `/subjects/:subjectId` on success. Task 23 (`routes.tsx`) mounts this at `/enroll/:studyId`.

- [ ] **Step 1: Write the failing tests**

`frontend/src/views/Enroll/Enroll.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { enrollPatient, getContext } from "../../api/client";
import Enroll from "./Enroll";

vi.mock("../../api/client");

function renderAtStudy(studyId: string) {
  return render(
    <MemoryRouter initialEntries={[`/enroll/${studyId}`]}>
      <Routes>
        <Route path="/enroll/:studyId" element={<Enroll />} />
        <Route path="/subjects/:subjectId" element={<p>Subject dashboard</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("Enroll", () => {
  beforeEach(() => {
    vi.mocked(getContext).mockReset();
    vi.mocked(enrollPatient).mockReset();
  });

  it("enrolls the patient from launch context without asking for manual input", async () => {
    vi.mocked(getContext).mockResolvedValue({ patientId: "patient-1", researchStudyId: null });
    vi.mocked(enrollPatient).mockResolvedValue({
      researchSubjectId: "subj-1",
      schedule: { completed: [], current: [], nextSteps: [], ambiguous: false },
    });

    renderAtStudy("study-1");

    expect(await screen.findByText("Patient: patient-1")).toBeInTheDocument();
    expect(screen.queryByLabelText("Patient FHIR ID")).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Enroll" }));

    expect(await screen.findByText("Subject dashboard")).toBeInTheDocument();
    expect(enrollPatient).toHaveBeenCalledWith("study-1", "patient-1");
  });

  it("accepts a manually entered patient id when there is no launch context", async () => {
    vi.mocked(getContext).mockResolvedValue({ patientId: null, researchStudyId: null });
    vi.mocked(enrollPatient).mockResolvedValue({
      researchSubjectId: "subj-2",
      schedule: { completed: [], current: [], nextSteps: [], ambiguous: false },
    });

    renderAtStudy("study-1");

    const input = await screen.findByLabelText("Patient FHIR ID");
    await userEvent.type(input, "uc1-demo-patient");
    await userEvent.click(screen.getByRole("button", { name: "Enroll" }));

    expect(await screen.findByText("Subject dashboard")).toBeInTheDocument();
    expect(enrollPatient).toHaveBeenCalledWith("study-1", "uc1-demo-patient");
  });

  it("disables the Enroll button until a patient id is available", async () => {
    vi.mocked(getContext).mockResolvedValue({ patientId: null, researchStudyId: null });

    renderAtStudy("study-1");

    expect(await screen.findByRole("button", { name: "Enroll" })).toBeDisabled();
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test -- src/views/Enroll/Enroll.test.tsx`
Expected: FAIL — `Cannot find module './Enroll'`

- [ ] **Step 3: Write the implementation**

`frontend/src/views/Enroll/Enroll.tsx`:
```tsx
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { enrollPatient, getContext } from "../../api/client";

export default function Enroll() {
  const { studyId } = useParams<{ studyId: string }>();
  const navigate = useNavigate();
  const [contextPatientId, setContextPatientId] = useState<string | null>(null);
  const [manualPatientId, setManualPatientId] = useState("");
  const [status, setStatus] = useState<"loading" | "ready" | "enrolling">("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getContext()
      .then((context) => setContextPatientId(context.patientId))
      .catch(() => {
        // No session context yet (e.g. mid-launch); treat as "no patient context".
      })
      .finally(() => setStatus("ready"));
  }, []);

  const patientId = contextPatientId ?? manualPatientId.trim();

  async function handleEnroll() {
    if (!studyId || !patientId) {
      return;
    }
    setStatus("enrolling");
    setError(null);
    try {
      const result = await enrollPatient(studyId, patientId);
      navigate(`/subjects/${result.researchSubjectId}`);
    } catch {
      setError("Enrollment failed. Please try again.");
      setStatus("ready");
    }
  }

  if (status === "loading") {
    return <p>Loading…</p>;
  }

  return (
    <div>
      <h2>Enroll a patient</h2>
      {error && <p role="alert">{error}</p>}
      {contextPatientId ? (
        <p>Patient: {contextPatientId}</p>
      ) : (
        <label>
          Patient FHIR ID
          <input
            value={manualPatientId}
            onChange={(event) => setManualPatientId(event.target.value)}
          />
        </label>
      )}
      <button onClick={handleEnroll} disabled={status === "enrolling" || !patientId}>
        {status === "enrolling" ? "Enrolling…" : "Enroll"}
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm test -- src/views/Enroll/Enroll.test.tsx`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/Enroll/Enroll.tsx frontend/src/views/Enroll/Enroll.test.tsx
git commit -m "Add Enroll view using launch patient context or a manually entered patient id"
```

---

## Task 22: `SubjectDashboard` view

Shows a subject's progress and exposes the two tracking actions: mark a current visit complete, and withdraw. The decision-support interaction is two calls to the *same* backend endpoint, which is the natural shape of `complete_visit`'s own semantics (Task 11): calling it with `transitionChoice: null` marks the visit finished and, if more than one outgoing transition is now valid, returns `ambiguous: true` with `nextSteps` listing the candidates *without materializing any of them*. Calling it again for the same `actionId` — now already finished, so re-marking it finished is a harmless no-op — with a chosen `transitionChoice` materializes that one candidate. So:

1. User clicks "Mark complete" on a current visit → `completeVisit(subjectId, actionId, null)`.
2. If the result is `ambiguous`, show its `nextSteps` as a choice prompt instead of treating the call as finished.
3. User picks one → `completeVisit(subjectId, actionId, chosenActionId)` again, which materializes it and clears the prompt.

Because `schedule_response()` (Task 9) only puts human-readable `title`s on `nextSteps` entries — `completed`/`current` are plain action-id strings — this view deliberately renders raw action ids for completed/current visits in V1. Adding titles there would mean changing `schedule_response`'s signature to also take the `ProtocolGraph` (a change touching Tasks 9, 10, 11, 15, and their tests); given the connectathon timeline, that's a Plan 2+ polish item, not a defect to fix now.

**Files:**
- Create: `frontend/src/views/SubjectDashboard/SubjectDashboard.tsx`
- Test: `frontend/src/views/SubjectDashboard/SubjectDashboard.test.tsx`

**Interfaces:**
- Consumes: `getSchedule`, `completeVisit`, `withdrawSubject`, `Schedule`, `NextStep` (Task 19).
- Produces: default-exported `SubjectDashboard` component, reading `:subjectId` from the route. Task 23 (`routes.tsx`) mounts this at `/subjects/:subjectId`.

- [ ] **Step 1: Write the failing tests**

`frontend/src/views/SubjectDashboard/SubjectDashboard.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { completeVisit, getSchedule, withdrawSubject } from "../../api/client";
import SubjectDashboard from "./SubjectDashboard";

vi.mock("../../api/client");

function renderAtSubject(subjectId: string) {
  return render(
    <MemoryRouter initialEntries={[`/subjects/${subjectId}`]}>
      <Routes>
        <Route path="/subjects/:subjectId" element={<SubjectDashboard />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("SubjectDashboard", () => {
  beforeEach(() => {
    vi.mocked(getSchedule).mockReset();
    vi.mocked(completeVisit).mockReset();
    vi.mocked(withdrawSubject).mockReset();
  });

  it("shows a decision prompt when completing a visit is ambiguous, then schedules the chosen step", async () => {
    vi.mocked(getSchedule).mockResolvedValue({
      completed: ["screening-1"],
      current: ["treatment-1"],
      nextSteps: [],
      ambiguous: false,
    });
    vi.mocked(completeVisit).mockResolvedValueOnce({
      completed: ["screening-1", "treatment-1"],
      current: [],
      nextSteps: [
        { actionId: "day7-1", title: "Day 7", transitionType: "SS" },
        { actionId: "eos-1", title: "End of Study", transitionType: "FS" },
      ],
      ambiguous: true,
    });
    vi.mocked(completeVisit).mockResolvedValueOnce({
      completed: ["screening-1", "treatment-1"],
      current: ["day7-1"],
      nextSteps: [],
      ambiguous: false,
    });

    renderAtSubject("subj-1");

    const completeButton = await screen.findByRole("button", { name: "Mark complete" });
    await userEvent.click(completeButton);

    expect(await screen.findByText("Decision needed")).toBeInTheDocument();
    const day7Button = screen.getByRole("button", { name: "Day 7" });
    await userEvent.click(day7Button);

    expect(completeVisit).toHaveBeenNthCalledWith(1, "subj-1", "treatment-1", null);
    expect(completeVisit).toHaveBeenNthCalledWith(2, "subj-1", "treatment-1", "day7-1");
    expect(screen.queryByText("Decision needed")).not.toBeInTheDocument();
  });

  it("withdraws the subject and shows a confirmation message", async () => {
    vi.mocked(getSchedule).mockResolvedValue({
      completed: [],
      current: ["screening-1"],
      nextSteps: [],
      ambiguous: false,
    });
    vi.mocked(withdrawSubject).mockResolvedValue({ id: "subj-1", subjectState: "withdrawn" });

    renderAtSubject("subj-1");

    const withdrawButton = await screen.findByRole("button", { name: "Withdraw subject" });
    await userEvent.click(withdrawButton);

    expect(await screen.findByRole("status")).toHaveTextContent("Subject withdrawn from study.");
    expect(withdrawSubject).toHaveBeenCalledWith("subj-1");
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test -- src/views/SubjectDashboard/SubjectDashboard.test.tsx`
Expected: FAIL — `Cannot find module './SubjectDashboard'`

- [ ] **Step 3: Write the implementation**

`frontend/src/views/SubjectDashboard/SubjectDashboard.tsx`:
```tsx
import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { completeVisit, getSchedule, withdrawSubject } from "../../api/client";
import type { NextStep, Schedule } from "../../api/types";

interface PendingChoice {
  actionId: string;
  options: NextStep[];
}

export default function SubjectDashboard() {
  const { subjectId } = useParams<{ subjectId: string }>();
  const [schedule, setSchedule] = useState<Schedule | null>(null);
  const [pendingChoice, setPendingChoice] = useState<PendingChoice | null>(null);
  const [withdrawn, setWithdrawn] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(() => {
    if (!subjectId) {
      return;
    }
    getSchedule(subjectId)
      .then(setSchedule)
      .catch(() => setError("Could not load this subject's schedule."));
  }, [subjectId]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  async function handleComplete(actionId: string) {
    if (!subjectId) {
      return;
    }
    try {
      const result = await completeVisit(subjectId, actionId, null);
      if (result.ambiguous) {
        setPendingChoice({ actionId, options: result.nextSteps });
      } else {
        setPendingChoice(null);
        setSchedule(result);
      }
    } catch {
      setError("Could not mark this visit complete.");
    }
  }

  async function handleChoice(targetActionId: string) {
    if (!subjectId || !pendingChoice) {
      return;
    }
    try {
      const result = await completeVisit(subjectId, pendingChoice.actionId, targetActionId);
      setPendingChoice(null);
      setSchedule(result);
    } catch {
      setError("Could not schedule the chosen next visit.");
    }
  }

  async function handleWithdraw() {
    if (!subjectId) {
      return;
    }
    try {
      await withdrawSubject(subjectId);
      setWithdrawn(true);
      refresh();
    } catch {
      setError("Could not withdraw this subject.");
    }
  }

  if (error) {
    return <p role="alert">{error}</p>;
  }

  if (!schedule) {
    return <p>Loading schedule…</p>;
  }

  return (
    <div>
      {withdrawn && <p role="status">Subject withdrawn from study.</p>}

      <section aria-label="Completed visits">
        <h2>Completed</h2>
        <ul>
          {schedule.completed.map((actionId) => (
            <li key={actionId}>{actionId}</li>
          ))}
        </ul>
      </section>

      <section aria-label="Current visits">
        <h2>Current</h2>
        <ul>
          {schedule.current.map((actionId) => (
            <li key={actionId}>
              {actionId}
              <button onClick={() => handleComplete(actionId)}>Mark complete</button>
            </li>
          ))}
        </ul>
      </section>

      {pendingChoice && (
        <section aria-label="Decision needed">
          <h2>Decision needed</h2>
          <p>More than one next step is valid. Choose which one to schedule:</p>
          <ul>
            {pendingChoice.options.map((option) => (
              <li key={option.actionId}>
                <button onClick={() => handleChoice(option.actionId)}>{option.title}</button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {!pendingChoice && schedule.nextSteps.length > 0 && (
        <section aria-label="Next steps">
          <h2>Next steps</h2>
          <ul>
            {schedule.nextSteps.map((step) => (
              <li key={step.actionId}>{step.title}</li>
            ))}
          </ul>
        </section>
      )}

      <button onClick={handleWithdraw} disabled={withdrawn}>
        Withdraw subject
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd frontend && npm test -- src/views/SubjectDashboard/SubjectDashboard.test.tsx`
Expected: `2 passed`

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/SubjectDashboard/SubjectDashboard.tsx frontend/src/views/SubjectDashboard/SubjectDashboard.test.tsx
git commit -m "Add SubjectDashboard view with decision-support prompt and withdraw action"
```

---

## Task 23: Launch pages and full app routing

This is the task that replaces Task 18's placeholder `routes.tsx` with the real route tree, now that `StudyWorklist`, `Enroll`, and `SubjectDashboard` (Tasks 20-22) all exist to route to. It also adds the two `launch/` pages: a pending/loading state shown while `GET /api/context` is in flight, and an error page for `/launch-error?reason=...` (the redirect target Task 14's backend uses for `untrusted_iss` and `invalid_state`).

The root route (`/`) does the branching the design's data-flow step 2 describes: call `GET /api/context` once, then render the view that matches whatever the backend's launch flow captured —
- no session at all (the call 401s) → a message pointing at `/launch/standalone` (a real backend route, hit via a plain `<a href>` full-page navigation, not a SPA route — the SPA itself never drives the OAuth redirect chain);
- a `researchStudyId` (EHR launch via `fhirContext`, design data-flow step 1) → redirect straight into `Enroll` for that study;
- neither → `StudyWorklist`, the standalone-launch entry point.

**Files:**
- Create: `frontend/src/launch/LaunchPending.tsx`
- Create: `frontend/src/launch/LaunchError.tsx`
- Test: `frontend/src/launch/LaunchError.test.tsx`
- Modify: `frontend/src/routes.tsx` (replaces Task 18's placeholder entirely)
- Test: `frontend/src/routes.test.tsx`

**Interfaces:**
- Consumes: `getContext`, `Context` (Task 19); `StudyWorklist` (Task 20); `Enroll` (Task 21); `SubjectDashboard` (Task 22).
- Produces: the route tree every other frontend task and Task 24's Playwright spec navigate against: `/` (landing), `/launch-error`, `/enroll/:studyId`, `/subjects/:subjectId`.

- [ ] **Step 1: Write the failing tests**

`frontend/src/launch/LaunchError.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";

import LaunchError from "./LaunchError";

function renderWithReason(reason: string | null) {
  const path = reason ? `/launch-error?reason=${reason}` : "/launch-error";
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/launch-error" element={<LaunchError />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("LaunchError", () => {
  it("shows a specific message for untrusted_iss", async () => {
    renderWithReason("untrusted_iss");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This app was launched from an unrecognized FHIR server.",
    );
  });

  it("shows a specific message for invalid_state", async () => {
    renderWithReason("invalid_state");
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Your sign-in session expired or was already used.",
    );
  });

  it("falls back to a generic message for an unknown or missing reason", async () => {
    renderWithReason(null);
    expect(await screen.findByRole("alert")).toHaveTextContent("Sign-in failed.");
  });
});
```

`frontend/src/routes.test.tsx`:
```tsx
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { getContext } from "./api/client";
import AppRoutes from "./routes";

vi.mock("./api/client");
vi.mock("./views/StudyWorklist/StudyWorklist", () => ({
  default: () => <p>Study worklist</p>,
}));
vi.mock("./views/Enroll/Enroll", () => ({
  default: () => <p>Enroll view</p>,
}));

describe("AppRoutes", () => {
  beforeEach(() => {
    vi.mocked(getContext).mockReset();
  });

  it("shows the study worklist when there is no research study context", async () => {
    vi.mocked(getContext).mockResolvedValue({ patientId: null, researchStudyId: null });

    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Study worklist")).toBeInTheDocument();
  });

  it("redirects to enroll when context carries a research study id", async () => {
    vi.mocked(getContext).mockResolvedValue({ patientId: "patient-1", researchStudyId: "study-1" });

    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Enroll view")).toBeInTheDocument();
  });

  it("shows a standalone-launch link when there is no session", async () => {
    vi.mocked(getContext).mockRejectedValue(new Error("401"));

    render(
      <MemoryRouter initialEntries={["/"]}>
        <AppRoutes />
      </MemoryRouter>,
    );

    expect(await screen.findByRole("link", { name: "start a standalone launch" })).toHaveAttribute(
      "href",
      "/launch/standalone",
    );
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd frontend && npm test -- src/launch/LaunchError.test.tsx src/routes.test.tsx`
Expected: FAIL — `Cannot find module './LaunchError'` (and `routes.test.tsx` fails because the placeholder `routes.tsx` doesn't render any of the mocked views or the standalone-launch link)

- [ ] **Step 3: Write `LaunchPending.tsx` and `LaunchError.tsx`**

`frontend/src/launch/LaunchPending.tsx`:
```tsx
export default function LaunchPending() {
  return <p role="status">Completing sign-in…</p>;
}
```

`frontend/src/launch/LaunchError.tsx`:
```tsx
import { useSearchParams } from "react-router-dom";

const REASON_MESSAGES: Record<string, string> = {
  untrusted_iss: "This app was launched from an unrecognized FHIR server.",
  invalid_state: "Your sign-in session expired or was already used.",
};

export default function LaunchError() {
  const [searchParams] = useSearchParams();
  const reason = searchParams.get("reason");
  const message = (reason && REASON_MESSAGES[reason]) ?? "Sign-in failed.";

  return (
    <div>
      <p role="alert">{message}</p>
      <p>Please relaunch this app from your EHR.</p>
    </div>
  );
}
```

- [ ] **Step 4: Replace `routes.tsx` with the real route tree**

`frontend/src/routes.tsx`:
```tsx
import { useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { getContext } from "./api/client";
import type { Context } from "./api/types";
import LaunchError from "./launch/LaunchError";
import LaunchPending from "./launch/LaunchPending";
import Enroll from "./views/Enroll/Enroll";
import StudyWorklist from "./views/StudyWorklist/StudyWorklist";
import SubjectDashboard from "./views/SubjectDashboard/SubjectDashboard";

function Landing() {
  const [context, setContext] = useState<Context | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    getContext()
      .then(setContext)
      .catch(() => setFailed(true));
  }, []);

  if (failed) {
    return (
      <p>
        No active session. Launch this app from your EHR, or{" "}
        <a href="/launch/standalone">start a standalone launch</a>.
      </p>
    );
  }

  if (!context) {
    return <LaunchPending />;
  }

  if (context.researchStudyId) {
    return <Navigate to={`/enroll/${context.researchStudyId}`} replace />;
  }

  return <StudyWorklist />;
}

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/launch-error" element={<LaunchError />} />
      <Route path="/enroll/:studyId" element={<Enroll />} />
      <Route path="/subjects/:subjectId" element={<SubjectDashboard />} />
    </Routes>
  );
}
```

`/launch/standalone` is a backend route (Task 14), not a SPA route — there is deliberately no matching `<Route>` for it. The plain `<a href="/launch/standalone">` triggers a full-page browser navigation, which Vite's dev proxy (Task 18) forwards to the backend, which redirects on to Aidbox's real `/authorize` endpoint.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npm test -- src/launch/LaunchError.test.tsx src/routes.test.tsx`
Expected: `6 passed`

- [ ] **Step 6: Run the full frontend test suite**

Run: `cd frontend && npm test`
Expected: every test from Tasks 18-23 passes.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/launch/LaunchPending.tsx frontend/src/launch/LaunchError.tsx frontend/src/launch/LaunchError.test.tsx frontend/src/routes.tsx frontend/src/routes.test.tsx
git commit -m "Add launch pending/error pages and wire the full app route tree"
```

---

## Task 24: Playwright golden-path E2E test

The design's testing strategy calls for "Playwright E2E covering the golden path — launch → enroll → view schedule → complete a visit → see the next suggested step — against the local Aidbox." Two parts of that golden path have genuinely different automation characteristics, so this task is split into two tests rather than forcing one:

1. **The launch redirect itself is fully automatable without touching Aidbox's login UI.** Clicking the standalone-launch link only needs to be shown to navigate to Aidbox's real `/authorize` endpoint — Playwright doesn't need to complete the login to prove the redirect chain (frontend → backend `/launch/standalone` → Aidbox `/authorize`) is wired correctly.
2. **Everything after a session exists is fully automatable within this app's own UI** — but getting a logged-in session in the first place requires a human to complete Aidbox's own hosted login/consent screen at least once, since that screen belongs to Aidbox, not this app, and this plan adds no backend test-bypass for it (that would be a new, security-sensitive surface, not a frontend task). Playwright's standard answer to exactly this situation is `storageState`: log in once by hand, save the resulting cookies to a JSON file, and reuse that file on every subsequent run without repeating the login. This test is gated on that file existing — same shape as Task 17's `RUN_INTEGRATION_TESTS` gate, just expressed as a file-existence check instead of an environment variable.

**Files:**
- Create: `frontend/playwright.config.ts`
- Create: `frontend/e2e/golden-path.spec.ts`
- Modify: `frontend/.gitignore` (add `e2e/.auth/`)

**Interfaces:**
- Consumes: the running dev servers (frontend `npm run dev` on `:5173`, backend `uvicorn` on `:8000`) and a real local Aidbox loaded per Task 5. Not consumed by anything else — this is this plan's last task.

- [ ] **Step 1: Add `e2e/.auth/` to `.gitignore`**

`frontend/.gitignore`:
```
node_modules/
dist/
playwright-report/
test-results/
e2e/.auth/
```

- [ ] **Step 2: Create `playwright.config.ts`**

`frontend/playwright.config.ts`:
```ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: {
    baseURL: "http://localhost:5173",
  },
});
```

This intentionally has no `webServer` entry: the frontend dev server's proxy target (the backend) needs a real Aidbox connection that Playwright can't establish on its own, so both dev servers are started by hand before running this spec (Step 5), the same precondition Task 17's integration test and Task 5's spike already depend on.

- [ ] **Step 3: Write the spec**

`frontend/e2e/golden-path.spec.ts`:
```ts
import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

const STORAGE_STATE_PATH = path.join(__dirname, ".auth", "session.json");
const hasBootstrappedSession = fs.existsSync(STORAGE_STATE_PATH);

test("standalone launch redirects to the configured Aidbox authorize endpoint", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("link", { name: "start a standalone launch" }).click();
  await page.waitForURL(/\/auth\/authorize\?/);
  expect(page.url()).toContain("response_type=code");
});

test.describe("authenticated golden path", () => {
  test.skip(
    !hasBootstrappedSession,
    "requires a one-time manual login bootstrap: " +
      "npx playwright codegen --save-storage=e2e/.auth/session.json http://localhost:5173 " +
      "(complete the standalone launch + Aidbox login once, then close the browser)",
  );
  test.use({ storageState: STORAGE_STATE_PATH });

  test("worklist to enroll to schedule to complete to ambiguous decision prompt", async ({ page }) => {
    await page.goto("/");
    await page.getByRole("link", { name: "Use Case 1 Demo Study (Exit Example)" }).click();

    await page.getByLabel("Patient FHIR ID").fill("uc1-demo-patient");
    await page.getByRole("button", { name: "Enroll" }).click();

    await expect(page.getByText("0700e721-1f12-4998-89b8-6f4e649b62f7")).toBeVisible();
    await page.getByRole("button", { name: "Mark complete" }).click();

    await expect(page.getByText("a1806239-54f3-4762-af3f-edb9d80d29dc")).toBeVisible();
    await page.getByRole("button", { name: "Withdraw subject" }).click();
    await expect(page.getByText("Subject withdrawn from study.")).toBeVisible();

    await page.getByRole("button", { name: "Mark complete" }).click();
    await expect(page.getByText("Decision needed")).toBeVisible();
    await expect(page.getByRole("button", { name: "Day 7" })).toBeVisible();
    await expect(page.getByRole("button", { name: "End of Study" })).toBeVisible();
  });
});
```

The action ids (`0700e721-...`, `a1806239-...`) and the patient/study ids (`uc1-demo-patient`, the "Use Case 1 Demo Study (Exit Example)" title) are the exact values from Task 5's fixtures and Task 6's parsed Use Case 1 graph — this spec walks the identical sequence Task 17's integration test already proved against the domain layer directly, just driven through the real UI instead. As with Task 17, re-running this spec against the same long-lived local Aidbox accumulates state on the `uc1-demo-patient`/`uc1-demo-research-study` subject (enrollment is idempotent via conditional-create, but a subject that's already past withdrawal won't show the same screen sequence on a second run) — re-run against a freshly reloaded Aidbox, or delete that subject's `Encounter`/`ResearchSubject` resources between runs, for a clean repeat.

- [ ] **Step 4: Run Playwright's browsers install (one-time per machine)**

```bash
cd frontend
npx playwright install --with-deps chromium
```

- [ ] **Step 5: Run the redirect test**

With the backend running (`uvicorn vulcan_soa.api.app:app --reload`, `ENV_FILE=.env.local`) and the frontend dev server running (`npm run dev`) in two separate terminals:

```bash
cd frontend
npx playwright test golden-path.spec.ts -g "standalone launch redirects"
```

Expected: `1 passed`. The second `test.describe` block reports `1 skipped` (the bootstrap file doesn't exist yet) — this is expected, not a failure.

- [ ] **Step 6: Bootstrap a session once and run the full golden path**

```bash
cd frontend
npx playwright codegen --save-storage=e2e/.auth/session.json http://localhost:5173
```

In the browser window that opens, click "start a standalone launch", complete Aidbox's login/consent screen, wait for the SPA to load back at `/`, then close the codegen window — this saves the resulting session cookie to `e2e/.auth/session.json`. Then:

```bash
npx playwright test golden-path.spec.ts
```

Expected: `2 passed`. If the second test fails partway through, re-check Aidbox's actual current state for `uc1-demo-patient`'s `ResearchSubject` (see the idempotency note in Step 3) before assuming the frontend is broken.

- [ ] **Step 7: Commit**

```bash
git add frontend/playwright.config.ts frontend/e2e/golden-path.spec.ts frontend/.gitignore
git commit -m "Add Playwright golden-path E2E test against the local Aidbox"
```

---

## Task 25: Generate the Aidbox Client + AccessPolicy application registration

The app needs an Aidbox `Client` (the SMART confidential client) and a linked `AccessPolicy` before anything can authenticate. Locally, `docker/aidbox/init-bundle.json` creates them at first boot — but on a remote instance (the connectathon box) `docs/smart-on-fhir-setup.md` currently tells the user to hand-edit two JSON blobs in the Aidbox REST console, re-typing the secret and redirect URI that already live in `backend/.env.connectathon`. Hand-copied values are exactly how the "401 invalid_client" and "redirect_uri mismatch" failure modes in that doc's troubleshooting table happen.

This task adds `backend/scripts/generate_client_registration.py`, which builds both resources *from `Settings`* (so `SMART_CLIENT_ID`, `SMART_CLIENT_SECRET`, and `REDIRECT_URI` can never drift from what the backend will actually send). Default mode prints a batch `Bundle` to paste into the REST console; `--apply` PUTs the resources directly using admin (root-client) basic-auth credentials — admin credentials are required because the app client can't create its own registration (chicken-and-egg).

Two Aidbox specifics worth knowing (you can't guess these from FHIR alone):

- `Client` and `AccessPolicy` are **Aidbox system resources, not FHIR resources**. They live at the box base URL (`http://localhost:8888/Client/...`), not under `/fhir`. The script derives the box base by stripping the trailing `/fhir` from `fhir_base_url`.
- The generated shapes must stay identical to the first two entries of `docker/aidbox/init-bundle.json` (grant types `authorization_code` + `basic`, PKCE on, `open-for-<client-id>` allow policy) — the local bootstrap and this script are two delivery mechanisms for the same registration. `engine: allow` is acceptable for local dev and a connectathon sandbox only; the security note in `docs/smart-on-fhir-setup.md` already covers this.

**Files:**
- Create: `backend/scripts/generate_client_registration.py`
- Modify: `Taskfile.yml` (add `aidbox:register-client` after `aidbox:wait`)
- Modify: `docs/smart-on-fhir-setup.md` (remote setup step 1)
- Test: `backend/tests/test_generate_client_registration.py`

**Interfaces:**
- Consumes: `Settings` with fields `fhir_base_url`, `smart_client_id`, `smart_client_secret`, `redirect_uri` (Task 2); `FhirClient(base_url, *, basic_auth=(id, secret))` and its `put_by_id(resource_type, resource_id, resource) -> dict` (Task 4); `backend/tests/conftest.py` already puts `backend/` on `sys.path` so `from scripts... import` works (Task 5).
- Produces: `build_client(client_id: str, secret: str, redirect_uri: str) -> dict`, `build_access_policy(client_id: str) -> dict`, `build_registration_bundle(client_id: str, secret: str, redirect_uri: str) -> dict`, `aidbox_base_url(fhir_base_url: str) -> str`, `apply_registration(client: FhirClient, client_id: str, secret: str, redirect_uri: str) -> None`, and a `main()` CLI. Nothing else consumes these in code — the consumers are the setup doc and the Taskfile.

- [x] **Step 1: Write the failing tests**

`backend/tests/test_generate_client_registration.py`:
```python
import httpx
import respx

from scripts.generate_client_registration import (
    aidbox_base_url,
    apply_registration,
    build_access_policy,
    build_client,
    build_registration_bundle,
)
from vulcan_soa.fhir_client import FhirClient


def test_build_client_injects_config_values():
    client = build_client("my-app", "s3cret", "https://bff.example/callback")
    assert client["resourceType"] == "Client"
    assert client["id"] == "my-app"
    assert client["secret"] == "s3cret"
    assert client["auth"]["authorization_code"]["redirect_uri"] == "https://bff.example/callback"


def test_build_client_is_confidential_with_pkce_and_basic_grant():
    client = build_client("my-app", "s", "https://cb")
    assert client["type"] == "confidential"
    assert client["auth"]["authorization_code"]["pkce"] is True
    assert set(client["grant_types"]) == {"authorization_code", "basic"}


def test_build_access_policy_links_client():
    policy = build_access_policy("my-app")
    assert policy["resourceType"] == "AccessPolicy"
    assert policy["id"] == "open-for-my-app"
    assert policy["engine"] == "allow"
    assert policy["link"] == [{"resourceType": "Client", "id": "my-app"}]


def test_bundle_puts_both_resources():
    bundle = build_registration_bundle("my-app", "s", "https://cb")
    assert bundle["resourceType"] == "Bundle"
    assert bundle["type"] == "batch"
    assert [entry["request"]["url"] for entry in bundle["entry"]] == [
        "/Client/my-app",
        "/AccessPolicy/open-for-my-app",
    ]
    assert all(entry["request"]["method"] == "PUT" for entry in bundle["entry"])


def test_aidbox_base_url_strips_fhir_suffix():
    assert aidbox_base_url("http://localhost:8888/fhir") == "http://localhost:8888"
    assert aidbox_base_url("https://x.aidbox.app/fhir/") == "https://x.aidbox.app"


@respx.mock
async def test_apply_registration_puts_client_and_policy_with_admin_auth():
    client_route = respx.put("http://aidbox.test/Client/my-app").mock(
        return_value=httpx.Response(200, json={"resourceType": "Client", "id": "my-app"})
    )
    policy_route = respx.put("http://aidbox.test/AccessPolicy/open-for-my-app").mock(
        return_value=httpx.Response(
            200, json={"resourceType": "AccessPolicy", "id": "open-for-my-app"}
        )
    )
    fhir = FhirClient(base_url="http://aidbox.test", basic_auth=("root", "admin-secret"))
    await apply_registration(fhir, "my-app", "s3cret", "https://cb")
    await fhir.close()

    assert client_route.called
    assert policy_route.called
    assert client_route.calls.last.request.headers["Authorization"].startswith("Basic ")
```

- [x] **Step 2: Run tests to verify they fail**

Run: `cd backend && pytest tests/test_generate_client_registration.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.generate_client_registration'`

- [x] **Step 3: Write the implementation**

`backend/scripts/generate_client_registration.py`:
```python
"""Generate (and optionally apply) the app's Aidbox Client + AccessPolicy registration.

Builds the registration from Settings so SMART_CLIENT_ID / SMART_CLIENT_SECRET /
REDIRECT_URI can never drift from what the backend sends. Default: print a batch
Bundle for the Aidbox REST console. --apply: PUT both resources directly, using
admin (root client) basic-auth credentials — the app client cannot create itself.
Client and AccessPolicy are Aidbox system resources living at the box base URL,
not under /fhir.
"""
import argparse
import asyncio
import json
import os

from vulcan_soa.config import Settings
from vulcan_soa.fhir_client import FhirClient


def build_client(client_id: str, secret: str, redirect_uri: str) -> dict:
    return {
        "resourceType": "Client",
        "id": client_id,
        "type": "confidential",
        "secret": secret,
        "grant_types": ["authorization_code", "basic"],
        "auth": {
            "authorization_code": {
                "pkce": True,
                "redirect_uri": redirect_uri,
                "access_token_expiration": 3600,
                "token_format": "jwt",
            }
        },
        "scope": ["openid", "fhirUser", "launch", "patient/*.read"],
    }


def build_access_policy(client_id: str) -> dict:
    return {
        "resourceType": "AccessPolicy",
        "id": f"open-for-{client_id}",
        "engine": "allow",
        "link": [{"resourceType": "Client", "id": client_id}],
    }


def build_registration_bundle(client_id: str, secret: str, redirect_uri: str) -> dict:
    client = build_client(client_id, secret, redirect_uri)
    policy = build_access_policy(client_id)
    return {
        "resourceType": "Bundle",
        "type": "batch",
        "entry": [
            {
                "request": {"method": "PUT", "url": f"/Client/{client['id']}"},
                "resource": client,
            },
            {
                "request": {"method": "PUT", "url": f"/AccessPolicy/{policy['id']}"},
                "resource": policy,
            },
        ],
    }


def aidbox_base_url(fhir_base_url: str) -> str:
    return fhir_base_url.rstrip("/").removesuffix("/fhir")


async def apply_registration(
    client: FhirClient, client_id: str, secret: str, redirect_uri: str
) -> None:
    await client.put_by_id("Client", client_id, build_client(client_id, secret, redirect_uri))
    policy = build_access_policy(client_id)
    await client.put_by_id("AccessPolicy", policy["id"], policy)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate the Aidbox Client + AccessPolicy registration for this app"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="PUT the resources to Aidbox (requires AIDBOX_ADMIN_CLIENT_SECRET) "
        "instead of printing the bundle",
    )
    args = parser.parse_args()

    settings = Settings()

    if not args.apply:
        bundle = build_registration_bundle(
            settings.smart_client_id, settings.smart_client_secret, settings.redirect_uri
        )
        print(json.dumps(bundle, indent=2))
        return

    admin_id = os.environ.get("AIDBOX_ADMIN_CLIENT_ID", "root")
    admin_secret = os.environ.get("AIDBOX_ADMIN_CLIENT_SECRET")
    if not admin_secret:
        raise SystemExit(
            "--apply requires AIDBOX_ADMIN_CLIENT_SECRET "
            "(admin/root client credentials for the target Aidbox)"
        )

    client = FhirClient(
        base_url=aidbox_base_url(settings.fhir_base_url),
        basic_auth=(admin_id, admin_secret),
    )
    try:
        await apply_registration(
            client, settings.smart_client_id, settings.smart_client_secret, settings.redirect_uri
        )
    finally:
        await client.close()

    print(
        f"Registered Client/{settings.smart_client_id} and "
        f"AccessPolicy/open-for-{settings.smart_client_id} "
        f"at {aidbox_base_url(settings.fhir_base_url)}"
    )


if __name__ == "__main__":
    asyncio.run(main())
```

- [x] **Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_generate_client_registration.py -v`
Expected: `6 passed`

- [x] **Step 5: Add the Taskfile entry**

In `Taskfile.yml`, insert after the `aidbox:wait` task (still in the Aidbox section):

```yaml
  aidbox:register-client:
    desc: Print the app's Client + AccessPolicy registration bundle (task aidbox:register-client -- --apply to PUT it).
    dir: "{{.BACKEND_DIR}}"
    cmds:
      - |
        source .venv/bin/activate
        ENV_FILE={{.ENV_FILE}} python scripts/generate_client_registration.py {{.CLI_ARGS}}
    preconditions:
      - sh: test -f .venv/bin/activate
        msg: "Run 'task backend:install' first"
```

`{{.CLI_ARGS}}` is Task's standard pass-through: `task aidbox:register-client -- --apply` forwards `--apply` to the script.

- [x] **Step 6: Verify against the real local Aidbox**

With local Aidbox running (`task aidbox:up && task aidbox:wait`) and `backend/.env.local` in place:

```bash
cd backend && source .venv/bin/activate

# Generate mode: bundle must match the first two entries of docker/aidbox/init-bundle.json
ENV_FILE=.env.local python scripts/generate_client_registration.py

# Apply mode: local root secret is SMART_CLIENT_SECRET from docker/.env (compose maps it to BOX_ROOT_CLIENT_SECRET)
AIDBOX_ADMIN_CLIENT_SECRET=$(grep '^SMART_CLIENT_SECRET=' ../docker/.env | cut -d= -f2) \
  ENV_FILE=.env.local python scripts/generate_client_registration.py --apply

# The registered client's basic-auth grant must now work against the FHIR API
curl -sf -u "vulcan-soa-bff:$(grep '^SMART_CLIENT_SECRET=' .env.local | cut -d= -f2)" \
  http://localhost:8888/fhir/Patient > /dev/null && echo "basic auth OK"
```

Expected: the printed bundle's `Client`/`AccessPolicy` entries are field-for-field identical to `docker/aidbox/init-bundle.json`'s first two entries (only the secret differs if you changed it from `change-me`); apply prints `Registered Client/vulcan-soa-bff and AccessPolicy/open-for-vulcan-soa-bff at http://localhost:8888`; the curl prints `basic auth OK`. Compare the bundle against `init-bundle.json` by eye — if the shapes have drifted (e.g. a scope was added to one but not the other), fix the *bundle file* to match the script, since the script is now the canonical shape.

- [x] **Step 7: Update the setup doc**

In `docs/smart-on-fhir-setup.md`, replace step 1 of the "Remote setup (Connectathon / hosted Aidbox)" section (the "Create the Client and AccessPolicy … REST Console … with two edits" step, including its `PUT /Client/...` code block) with:

```markdown
1. **Create the Client and AccessPolicy** on the remote instance. Fill in
   `backend/.env.connectathon` first (step 2) — the registration is generated from
   it, so the secret and redirect URI cannot drift from what the backend sends:

   ```bash
   cd backend && source .venv/bin/activate
   ENV_FILE=.env.connectathon python scripts/generate_client_registration.py
   ```

   This prints a batch `Bundle` containing the `Client` and `AccessPolicy` from
   [the section above](#the-client-registration-aidbox-needs) with your values
   filled in — paste it into the Aidbox REST console (`POST /`). Or skip the
   console and apply it directly with the instance's admin client:

   ```bash
   AIDBOX_ADMIN_CLIENT_ID=root AIDBOX_ADMIN_CLIENT_SECRET=<admin secret> \
     ENV_FILE=.env.connectathon python scripts/generate_client_registration.py --apply
   ```

   Two values worth double-checking in your env file before generating:

   - `SMART_CLIENT_SECRET` — generate a real secret (`openssl rand -hex 24`); do not
     reuse `change-me`.
   - `REDIRECT_URI` — where the *backend* is reachable from the user's browser, e.g.
     `http://localhost:8000/callback` if you run the BFF locally against the remote
     Aidbox, or `https://<your-host>/callback` if the BFF is deployed.
```

Note the step-ordering wrinkle this introduces: the env file (old step 2) must now exist before registration (step 1). The replacement text handles it with the "Fill in `backend/.env.connectathon` first (step 2)" cross-reference — do not renumber the section's steps.

- [x] **Step 8: Run the full backend suite to confirm nothing regressed**

Run: `cd backend && pytest -v`
Expected: all tests pass (the new file adds 6).

- [x] **Step 9: Commit**

```bash
git add backend/scripts/generate_client_registration.py backend/tests/test_generate_client_registration.py Taskfile.yml docs/smart-on-fhir-setup.md docs/superpowers/plans/2026-06-23-connectathon-foundation.md
git commit -m "Generate Aidbox Client + AccessPolicy registration from backend settings"
```

---
