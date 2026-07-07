import httpx
import respx

from scripts.check_connection import (
    REQUIRED_FIXTURES,
    check_client_auth,
    check_fixtures,
    check_oauth_endpoints,
    check_reachability,
)
from vulcan_soa.fhir_client import FhirClient

FHIR_BASE = "http://aidbox.test/fhir"
AUTHORIZE_URL = "http://aidbox.test/auth/authorize"
TOKEN_URL = "http://aidbox.test/auth/token"


def make_fhir_client() -> FhirClient:
    return FhirClient(base_url=FHIR_BASE, basic_auth=("vulcan-soa-bff", "secret"))


def capability_statement(version="6.0.0-ballot3"):
    return {"resourceType": "CapabilityStatement", "fhirVersion": version}


# ── check_reachability ──────────────────────────────────────────────────────


@respx.mock
async def test_reachability_passes_on_expected_version():
    respx.get(f"{FHIR_BASE}/metadata").mock(
        return_value=httpx.Response(200, json=capability_statement())
    )
    async with httpx.AsyncClient() as http:
        result = await check_reachability(http, FHIR_BASE)

    assert result.passed
    assert "6.0.0-ballot3" in result.detail


@respx.mock
async def test_reachability_fails_on_wrong_version():
    respx.get(f"{FHIR_BASE}/metadata").mock(
        return_value=httpx.Response(200, json=capability_statement("4.0.1"))
    )
    async with httpx.AsyncClient() as http:
        result = await check_reachability(http, FHIR_BASE)

    assert not result.passed
    assert "4.0.1" in result.detail


@respx.mock
async def test_reachability_treats_401_as_reachable():
    respx.get(f"{FHIR_BASE}/metadata").mock(return_value=httpx.Response(401))
    async with httpx.AsyncClient() as http:
        result = await check_reachability(http, FHIR_BASE)

    assert result.passed
    assert "auth" in result.detail.lower()


@respx.mock
async def test_reachability_fails_on_connection_error():
    respx.get(f"{FHIR_BASE}/metadata").mock(side_effect=httpx.ConnectError("refused"))
    async with httpx.AsyncClient() as http:
        result = await check_reachability(http, FHIR_BASE)

    assert not result.passed
    assert result.hint is not None


@respx.mock
async def test_reachability_fails_on_404():
    respx.get(f"{FHIR_BASE}/metadata").mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as http:
        result = await check_reachability(http, FHIR_BASE)

    assert not result.passed


# ── check_client_auth ───────────────────────────────────────────────────────


@respx.mock
async def test_client_auth_passes_on_successful_search():
    respx.get(f"{FHIR_BASE}/Patient").mock(
        return_value=httpx.Response(200, json={"resourceType": "Bundle"})
    )
    client = make_fhir_client()
    result = await check_client_auth(client)
    await client.close()

    assert result.passed


@respx.mock
async def test_client_auth_401_hints_secret_mismatch():
    respx.get(f"{FHIR_BASE}/Patient").mock(return_value=httpx.Response(401))
    client = make_fhir_client()
    result = await check_client_auth(client)
    await client.close()

    assert not result.passed
    assert "secret" in result.hint.lower()


@respx.mock
async def test_client_auth_403_hints_register_client():
    respx.get(f"{FHIR_BASE}/Patient").mock(return_value=httpx.Response(403))
    client = make_fhir_client()
    result = await check_client_auth(client)
    await client.close()

    assert not result.passed
    assert "register-client" in result.hint


# ── check_oauth_endpoints ───────────────────────────────────────────────────


@respx.mock
async def test_oauth_passes_when_smart_configuration_matches():
    respx.get(f"{FHIR_BASE}/.well-known/smart-configuration").mock(
        return_value=httpx.Response(
            200,
            json={"authorization_endpoint": AUTHORIZE_URL, "token_endpoint": TOKEN_URL},
        )
    )
    async with httpx.AsyncClient() as http:
        result = await check_oauth_endpoints(http, FHIR_BASE, AUTHORIZE_URL, TOKEN_URL)

    assert result.passed


@respx.mock
async def test_oauth_fails_on_endpoint_mismatch():
    respx.get(f"{FHIR_BASE}/.well-known/smart-configuration").mock(
        return_value=httpx.Response(
            200,
            json={
                "authorization_endpoint": "http://other.test/authorize",
                "token_endpoint": TOKEN_URL,
            },
        )
    )
    async with httpx.AsyncClient() as http:
        result = await check_oauth_endpoints(http, FHIR_BASE, AUTHORIZE_URL, TOKEN_URL)

    assert not result.passed
    assert "http://other.test/authorize" in result.detail
    assert AUTHORIZE_URL in result.detail


@respx.mock
async def test_oauth_falls_back_to_authorize_url_when_no_smart_configuration():
    respx.get(f"{FHIR_BASE}/.well-known/smart-configuration").mock(
        return_value=httpx.Response(404)
    )
    respx.get(AUTHORIZE_URL).mock(return_value=httpx.Response(302))
    async with httpx.AsyncClient() as http:
        result = await check_oauth_endpoints(http, FHIR_BASE, AUTHORIZE_URL, TOKEN_URL)

    assert result.passed


@respx.mock
async def test_oauth_fails_when_authorize_url_is_404():
    respx.get(f"{FHIR_BASE}/.well-known/smart-configuration").mock(
        return_value=httpx.Response(404)
    )
    respx.get(AUTHORIZE_URL).mock(return_value=httpx.Response(404))
    async with httpx.AsyncClient() as http:
        result = await check_oauth_endpoints(http, FHIR_BASE, AUTHORIZE_URL, TOKEN_URL)

    assert not result.passed
    assert result.hint is not None


# ── check_fixtures ──────────────────────────────────────────────────────────


def mock_all_fixtures_present():
    for resource_type, resource_id in REQUIRED_FIXTURES:
        respx.get(f"{FHIR_BASE}/{resource_type}/{resource_id}").mock(
            return_value=httpx.Response(
                200, json={"resourceType": resource_type, "id": resource_id}
            )
        )


@respx.mock
async def test_fixtures_pass_when_all_present():
    mock_all_fixtures_present()
    client = make_fhir_client()
    result = await check_fixtures(client)
    await client.close()

    assert result.passed
    assert str(len(REQUIRED_FIXTURES)) in result.detail


@respx.mock
async def test_fixtures_fail_lists_missing_ids():
    mock_all_fixtures_present()
    respx.get(f"{FHIR_BASE}/Patient/uc1-demo-patient").mock(
        return_value=httpx.Response(404)
    )
    client = make_fhir_client()
    result = await check_fixtures(client)
    await client.close()

    assert not result.passed
    assert "Patient/uc1-demo-patient" in result.detail
    assert "fixtures:load-all" in result.hint
