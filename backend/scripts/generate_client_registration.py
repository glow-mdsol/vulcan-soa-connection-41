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
