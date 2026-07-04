import json

import httpx
import respx

from vulcan_soa.activity_flow import materialize_proposal
from vulcan_soa.fhir_client import FhirClient
from vulcan_soa.soa_engine.graph import VisitNode

VISIT_PD = {
    "resourceType": "PlanDefinition",
    "id": "E1-USDM",
    "action": [
        {"title": "no definition"},
        {"title": "Informed Consent", "definitionUri": "ActivityDefinition/act-consent"},
        {"title": "ADAS-Cog", "definitionUri": "Questionnaire/act-adas-cog"},
    ],
}
CONSENT_AD = {
    "resourceType": "ActivityDefinition",
    "id": "act-consent",
    "title": "Informed Consent",
    "kind": "ServiceRequest",
    "code": {"coding": [{"system": "http://www.cdisc.org", "code": "C16735", "display": "Informed Consent"}]},
}


@respx.mock
async def test_materialize_proposal_creates_visit_and_activity_requests():
    respx.get("http://aidbox.test/fhir/PlanDefinition/E1-USDM").mock(
        return_value=httpx.Response(200, json=VISIT_PD)
    )
    respx.get("http://aidbox.test/fhir/ActivityDefinition/act-consent").mock(
        return_value=httpx.Response(200, json=CONSENT_AD)
    )
    create_route = respx.post("http://aidbox.test/fhir/ServiceRequest").mock(
        side_effect=[
            httpx.Response(201, json={"resourceType": "ServiceRequest", "id": "sr-visit"}),
            httpx.Response(201, json={"resourceType": "ServiceRequest", "id": "sr-act"}),
        ]
    )

    node = VisitNode(
        action_id="E1", title="Screening 1", transitions=(), definition_uri="PlanDefinition/E1-USDM"
    )
    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok")
    created = await materialize_proposal(client, "p-1", "pd-1", node)
    await client.close()

    assert created["id"] == "sr-visit"
    assert create_route.call_count == 2

    visit_payload = json.loads(create_route.calls[0].request.content)
    assert visit_payload["intent"] == "proposal"
    assert visit_payload["status"] == "active"
    assert visit_payload["identifier"] == [{"system": "urn:vulcan-soa:plan-action", "value": "pd-1#E1"}]
    assert visit_payload["groupIdentifier"] == {"system": "urn:vulcan-soa:promotion", "value": "pd-1#E1:proposal"}
    assert visit_payload["instantiatesUri"] == ["PlanDefinition/E1-USDM"]
    assert visit_payload["code"] == {"concept": {"text": "Screening 1"}}
    assert visit_payload["subject"] == {"reference": "Patient/p-1"}

    activity_payload = json.loads(create_route.calls[1].request.content)
    assert activity_payload["identifier"] == [
        {"system": "urn:vulcan-soa:plan-action", "value": "pd-1#E1#act-consent"}
    ]
    assert activity_payload["basedOn"] == [{"reference": "ServiceRequest/sr-visit"}]
    assert activity_payload["instantiatesUri"] == ["ActivityDefinition/act-consent"]
    assert activity_payload["code"] == {"concept": CONSENT_AD["code"]}


@respx.mock
async def test_materialize_proposal_without_definition_uri_creates_only_visit_request():
    create_route = respx.post("http://aidbox.test/fhir/ServiceRequest").mock(
        return_value=httpx.Response(201, json={"resourceType": "ServiceRequest", "id": "sr-visit"})
    )

    node = VisitNode(action_id="screening-1", title="Screening", transitions=())
    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok")
    await materialize_proposal(client, "p-1", "pd-1", node)
    await client.close()

    assert create_route.call_count == 1
    payload = json.loads(create_route.calls[0].request.content)
    assert "instantiatesUri" not in payload
