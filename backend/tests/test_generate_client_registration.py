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
