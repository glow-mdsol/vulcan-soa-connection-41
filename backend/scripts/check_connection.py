"""Doctor-style checks that the configured FHIR server connection is correct.

Reads the target from Settings (ENV_FILE-driven), runs four independent checks —
reachability/version, client basic-auth grant, OAuth endpoint config, required
demo fixtures — and prints one line per check with a remediation hint on
failure. Exit code 0 when everything passes, 1 otherwise.
"""
import asyncio
import sys
from dataclasses import dataclass

import httpx

from vulcan_soa.config import Settings
from vulcan_soa.fhir_client import FhirClient

EXPECTED_FHIR_VERSION = "6.0.0-ballot3"

REQUIRED_FIXTURES: tuple[tuple[str, str], ...] = (
    ("PlanDefinition", "dynamic-visit-schedule-exit-example-PlanDefinition"),
    ("ResearchStudy", "uc1-demo-research-study"),
    ("Patient", "uc1-demo-patient"),
    ("Practitioner", "site-coordinator-demo"),
    ("PlanDefinition", "H2Q-MC-LZZT-ProtocolDesign-USDM"),
    ("ResearchStudy", "lzzt-usdm-demo-study"),
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    passed: bool
    detail: str
    hint: str | None = None


async def check_reachability(http: httpx.AsyncClient, fhir_base_url: str) -> CheckResult:
    name = "FHIR endpoint reachable"
    url = f"{fhir_base_url.rstrip('/')}/metadata"
    try:
        response = await http.get(url, headers={"Accept": "application/fhir+json"})
    except httpx.HTTPError as exc:
        return CheckResult(name, False, f"{type(exc).__name__}: {exc}", "check FHIR_BASE_URL")

    if response.status_code in (401, 403):
        return CheckResult(name, True, "reachable (metadata requires auth; version not verified)")
    if response.status_code != 200:
        return CheckResult(
            name, False, f"GET /metadata returned {response.status_code}", "check FHIR_BASE_URL"
        )

    capability = response.json()
    version = capability.get("fhirVersion")
    if version != EXPECTED_FHIR_VERSION:
        return CheckResult(
            name,
            False,
            f"fhirVersion is {version}, expected {EXPECTED_FHIR_VERSION}",
            "this is not the R6 ballot instance this app targets",
        )
    return CheckResult(name, True, f"fhirVersion {version}")


async def check_client_auth(fhir_client: FhirClient) -> CheckResult:
    name = "Client basic-auth grant"
    try:
        await fhir_client.search("Patient", {"_count": "1"})
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 401:
            hint = "SMART_CLIENT_SECRET does not match the registered Client's secret"
        elif status == 403:
            hint = (
                "AccessPolicy missing for the client — "
                "AIDBOX_ADMIN_CLIENT_SECRET=<admin> task aidbox:register-client -- --apply"
            )
        else:
            hint = None
        return CheckResult(name, False, f"Patient search returned {status}", hint)
    except httpx.HTTPError as exc:
        return CheckResult(name, False, f"{type(exc).__name__}: {exc}", "check FHIR_BASE_URL")

    return CheckResult(name, True, "authenticated Patient search OK")


async def check_oauth_endpoints(
    http: httpx.AsyncClient, fhir_base_url: str, authorize_url: str, token_url: str
) -> CheckResult:
    name = "OAuth endpoints"
    smart_config_url = f"{fhir_base_url.rstrip('/')}/.well-known/smart-configuration"
    try:
        response = await http.get(smart_config_url)
    except httpx.HTTPError as exc:
        return CheckResult(name, False, f"{type(exc).__name__}: {exc}", "check FHIR_BASE_URL")

    if response.status_code == 200:
        config = response.json()
        mismatches = []
        if config.get("authorization_endpoint") != authorize_url:
            mismatches.append(
                f"authorization_endpoint: server says {config.get('authorization_endpoint')}, "
                f"env says {authorize_url}"
            )
        if config.get("token_endpoint") != token_url:
            mismatches.append(
                f"token_endpoint: server says {config.get('token_endpoint')}, "
                f"env says {token_url}"
            )
        if mismatches:
            return CheckResult(
                name,
                False,
                "; ".join(mismatches),
                "update OAUTH_AUTHORIZE_URL / OAUTH_TOKEN_URL to the server's values",
            )
        return CheckResult(name, True, "smart-configuration matches env")

    # No smart-configuration published — settle for the authorize URL answering at all.
    try:
        authorize_response = await http.get(authorize_url)
    except httpx.HTTPError as exc:
        return CheckResult(name, False, f"{type(exc).__name__}: {exc}", "check OAUTH_AUTHORIZE_URL")
    if authorize_response.status_code == 404:
        return CheckResult(
            name, False, "authorize URL returned 404", "check OAUTH_AUTHORIZE_URL"
        )
    return CheckResult(
        name,
        True,
        f"authorize endpoint responds ({authorize_response.status_code}); "
        "no smart-configuration published",
    )


async def check_fixtures(fhir_client: FhirClient) -> CheckResult:
    name = "Required fixtures loaded"
    missing: list[str] = []
    for resource_type, resource_id in REQUIRED_FIXTURES:
        try:
            await fhir_client.read(resource_type, resource_id)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                missing.append(f"{resource_type}/{resource_id}")
            else:
                return CheckResult(
                    name,
                    False,
                    f"{resource_type}/{resource_id} returned {exc.response.status_code}",
                )
        except httpx.HTTPError as exc:
            return CheckResult(name, False, f"{type(exc).__name__}: {exc}")

    if missing:
        return CheckResult(
            name,
            False,
            f"missing: {', '.join(missing)}",
            "ENV_FILE=<env> task fixtures:load-all",
        )
    return CheckResult(name, True, f"all {len(REQUIRED_FIXTURES)} required resources present")


async def run_checks(settings: Settings) -> list[CheckResult]:
    fhir_client = FhirClient(
        base_url=settings.fhir_base_url,
        basic_auth=(settings.smart_client_id, settings.smart_client_secret),
    )
    try:
        # Aidbox generates its ~3 MB R6 CapabilityStatement on the first /metadata
        # request after boot, which can exceed httpx's 5 s default.
        async with httpx.AsyncClient(follow_redirects=False, timeout=30.0) as http:
            return [
                await check_reachability(http, settings.fhir_base_url),
                await check_client_auth(fhir_client),
                await check_oauth_endpoints(
                    http,
                    settings.fhir_base_url,
                    settings.oauth_authorize_url,
                    settings.oauth_token_url,
                ),
                await check_fixtures(fhir_client),
            ]
    finally:
        await fhir_client.close()


async def main() -> None:
    settings = Settings()
    print(f"Checking {settings.fhir_base_url} (client {settings.smart_client_id})\n")
    results = await run_checks(settings)

    for result in results:
        mark = "✓" if result.passed else "✗"
        print(f"{mark} {result.name} — {result.detail}")
        if not result.passed and result.hint:
            print(f"    hint: {result.hint}")

    failed = sum(1 for r in results if not r.passed)
    print()
    if failed:
        print(f"{failed} of {len(results)} checks failed")
        sys.exit(1)
    print(f"all {len(results)} checks passed")


if __name__ == "__main__":
    asyncio.run(main())
