# FHIR Connection Doctor — Design

**Problem:** Before a connectathon demo (or any run against a remote Aidbox), there
is no fast way to confirm the configured FHIR server is the right one, the client
registration works, the OAuth endpoints aren't typo'd, and the demo fixtures are
loaded. Each of these failure modes currently surfaces mid-demo as a confusing
runtime error.

**Decision:** A doctor-style script, `backend/scripts/check_connection.py`, printing
one `✓`/`✗` line per check with a remediation hint on failure, exit code 0/1.
Config comes entirely from `Settings()` (`ENV_FILE`-driven). Invoked as
`task fhir:doctor` (no localhost precondition — works against any instance).

## Checks

Each check is an independent async function returning a `CheckResult`
(`name`, `passed: bool`, `detail: str`, `hint: str | None`) so one failure never
hides the others and each is unit-testable with respx:

1. **Reachability + version** — unauthenticated `GET {FHIR_BASE_URL}/metadata`.
   Pass: CapabilityStatement with `fhirVersion == "6.0.0-ballot3"`. A 401/403
   counts as reachable (the server answered). Connection errors, 404, or a wrong
   version fail with the observed value. Hint: check `FHIR_BASE_URL`.
2. **Client basic-auth grant** — `Patient?_count=1` search via `FhirClient` with
   `SMART_CLIENT_ID`/`SMART_CLIENT_SECRET`. 401 → hint: secret mismatch with the
   registered Client. 403 → hint: AccessPolicy missing, run
   `task aidbox:register-client -- --apply`.
3. **OAuth endpoints** — `GET {FHIR_BASE_URL}/.well-known/smart-configuration`.
   If 200: its `authorization_endpoint`/`token_endpoint` must equal
   `OAUTH_AUTHORIZE_URL`/`OAUTH_TOKEN_URL` (mismatch fails, showing both values).
   If not published: fall back to `GET OAUTH_AUTHORIZE_URL` and pass on any
   response except 404/connection error.
4. **Fixtures loaded** — read six resources by id:
   `PlanDefinition/dynamic-visit-schedule-exit-example-PlanDefinition`,
   `ResearchStudy/uc1-demo-research-study`, `Patient/uc1-demo-patient`,
   `Practitioner/site-coordinator-demo`,
   `PlanDefinition/H2Q-MC-LZZT-ProtocolDesign-USDM`,
   `ResearchStudy/lzzt-usdm-demo-study`. Fail lists each missing id. Hint:
   `ENV_FILE=<env> task fixtures:load-all`.

## Wiring

- `Taskfile.yml`: `fhir:doctor` task (backend dir, venv precondition only).
- README "Switching Aidbox instances" and the setup doc's remote section gain a
  one-line pointer; the troubleshooting table references it.

## Testing

`backend/tests/test_check_connection.py` — respx-mocked happy path plus the key
failure path(s) per check (~12 tests), following the repo's existing async respx
style. `main()`'s printing/exit-code logic stays thin and is not unit-tested.

## Out of scope

- Checking the EHR-launch flow end to end (requires a browser + login).
- Validating IG StructureDefinitions on the remote instance (drift guard exists).
- Retries — single attempt per check. The doctor's own http client uses a 30 s
  timeout (not httpx's 5 s default): live verification showed Aidbox generates its
  ~3 MB R6 CapabilityStatement on the first post-boot /metadata request, which
  exceeds 5 s and false-failed the reachability check.
