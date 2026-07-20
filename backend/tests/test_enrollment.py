import json

import httpx
import pytest
import respx

from vulcan_soa.enrollment import (
    EnrollmentConflict,
    enroll,
    subject_identifier_of,
    update_subject_state,
)
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


def _mock_protocol():
    respx.get("http://aidbox.test/fhir/ResearchStudy/uc1-demo-research-study").mock(
        return_value=httpx.Response(200, json=STUDY)
    )
    respx.get("http://aidbox.test/fhir/PlanDefinition/plan-1").mock(
        return_value=httpx.Response(200, json=PLAN_DEFINITION)
    )


def _subject_bundle(*resources):
    return {"resourceType": "Bundle", "entry": [{"resource": r} for r in resources]}


def _mock_care_plan_empty():
    # No CarePlan mirror exists yet in these tests; the mirror lookups don't assert
    # on its contents, just need `ensure_care_plan`/`_mirror_activity` to no-op cleanly.
    respx.get("http://aidbox.test/fhir/CarePlan").mock(
        return_value=httpx.Response(200, json={"resourceType": "Bundle"})
    )
    respx.post("http://aidbox.test/fhir/CarePlan").mock(
        return_value=httpx.Response(201, json={"resourceType": "CarePlan", "id": "cp-1"})
    )


@respx.mock
async def test_enroll_creates_subject_and_materializes_root_visit():
    _mock_protocol()
    respx.get("http://aidbox.test/fhir/ResearchSubject").mock(
        return_value=httpx.Response(200, json={"resourceType": "Bundle"})
    )
    create_subject_route = respx.post("http://aidbox.test/fhir/ResearchSubject").mock(
        return_value=httpx.Response(
            201,
            json={
                "resourceType": "ResearchSubject",
                "id": "subj-1",
                "identifier": [{"system": "urn:vulcan-soa:subject-id", "value": "SUBJ-001"}],
            },
        )
    )
    create_service_request_route = respx.post("http://aidbox.test/fhir/ServiceRequest").mock(
        return_value=httpx.Response(201, json={"resourceType": "ServiceRequest", "id": "sr-1"})
    )
    respx.get("http://aidbox.test/fhir/CarePlan").mock(
        side_effect=[
            httpx.Response(200, json={"resourceType": "Bundle"}),  # ensure_care_plan: not found yet
            httpx.Response(  # _mirror_activity (via materialize_proposal): now it exists
                200,
                json={
                    "resourceType": "Bundle",
                    "entry": [
                        {
                            "resource": {
                                "resourceType": "CarePlan", "id": "cp-1", "status": "active",
                                "intent": "plan", "subject": {"reference": "Patient/patient-1"},
                                "identifier": [{"system": "urn:vulcan-soa:care-plan", "value": "plan-1"}],
                                "activity": [],
                            }
                        }
                    ],
                },
            ),
        ]
    )
    create_care_plan_route = respx.post("http://aidbox.test/fhir/CarePlan").mock(
        return_value=httpx.Response(
            201,
            json={
                "resourceType": "CarePlan", "id": "cp-1", "status": "active", "intent": "plan",
                "subject": {"reference": "Patient/patient-1"},
                "identifier": [{"system": "urn:vulcan-soa:care-plan", "value": "plan-1"}],
                "activity": [],
            },
        )
    )
    care_plan_update_route = respx.put("http://aidbox.test/fhir/CarePlan/cp-1").mock(
        return_value=httpx.Response(200, json={"resourceType": "CarePlan", "id": "cp-1"})
    )

    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok")
    result = await enroll(client, "uc1-demo-research-study", "patient-1", "SUBJ-001")
    await client.close()

    assert result["researchSubjectId"] == "subj-1"
    assert result["schedule"]["nextSteps"] == []  # the root visit is materialized, not "next"
    assert result["schedule"]["visits"] == {"screening-1": {"phase": "proposed"}}
    assert create_subject_route.called
    assert create_service_request_route.called
    proposal_payload = json.loads(create_service_request_route.calls.last.request.content)
    assert proposal_payload["intent"] == "proposal"
    assert proposal_payload["identifier"] == [
        {"system": "urn:vulcan-soa:plan-action", "value": "plan-1#screening-1"}
    ]
    subject_payload = json.loads(create_subject_route.calls.last.request.content)
    assert subject_payload["identifier"] == [
        {"system": "urn:vulcan-soa:subject-id", "value": "SUBJ-001"},
        {"system": "urn:vulcan-soa:plan-definition", "value": "plan-1"},
    ]
    # Enrollment creates the additive CPGCarePlan mirror, then the root visit's
    # proposal materialization points its activity entry at the new ServiceRequest.
    care_plan_payload = json.loads(create_care_plan_route.calls.last.request.content)
    assert care_plan_payload["subject"] == {"reference": "Patient/patient-1"}
    assert care_plan_payload["identifier"] == [
        {"system": "urn:vulcan-soa:care-plan", "value": "plan-1"}
    ]
    # R6 Aidbox rejects an empty array outright ("empty-value"): the field must be
    # omitted, not sent as `[]`, until the first activity is mirrored in.
    assert "activity" not in care_plan_payload
    mirrored_payload = json.loads(care_plan_update_route.calls.last.request.content)
    assert mirrored_payload["activity"] == [
        {"id": "screening-1", "plannedActivityReference": {"reference": "ServiceRequest/sr-1"}}
    ]


@respx.mock
async def test_enroll_is_idempotent_via_conditional_create():
    _mock_protocol()
    respx.get("http://aidbox.test/fhir/ResearchSubject").mock(
        return_value=httpx.Response(
            200,
            json=_subject_bundle(
                {
                    "resourceType": "ResearchSubject",
                    "id": "subj-existing",
                    "subject": {"reference": "Patient/patient-1"},
                    "identifier": [{"system": "urn:vulcan-soa:subject-id", "value": "SUBJ-001"}],
                }
            ),
        )
    )
    create_subject_route = respx.post("http://aidbox.test/fhir/ResearchSubject")
    respx.post("http://aidbox.test/fhir/ServiceRequest").mock(
        return_value=httpx.Response(201, json={"resourceType": "ServiceRequest", "id": "sr-1"})
    )
    _mock_care_plan_empty()

    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok")
    result = await enroll(client, "uc1-demo-research-study", "patient-1", "SUBJ-001")
    await client.close()

    assert result["researchSubjectId"] == "subj-existing"
    assert not create_subject_route.called


@respx.mock
async def test_enroll_conflicts_when_identifier_taken_by_another_patient():
    _mock_protocol()
    respx.get("http://aidbox.test/fhir/ResearchSubject").mock(
        return_value=httpx.Response(
            200,
            json=_subject_bundle(
                {
                    "resourceType": "ResearchSubject",
                    "id": "subj-other",
                    "subject": {"reference": "Patient/someone-else"},
                    "identifier": [{"system": "urn:vulcan-soa:subject-id", "value": "SUBJ-001"}],
                }
            ),
        )
    )
    create_route = respx.post("http://aidbox.test/fhir/ResearchSubject")

    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok")
    with pytest.raises(EnrollmentConflict):
        await enroll(client, "uc1-demo-research-study", "patient-1", "SUBJ-001")
    await client.close()
    assert not create_route.called


@respx.mock
async def test_reenroll_same_patient_same_identifier_is_idempotent(monkeypatch):
    _mock_protocol()
    existing = {
        "resourceType": "ResearchSubject",
        "id": "subj-existing",
        "subject": {"reference": "Patient/patient-1"},
        "identifier": [{"system": "urn:vulcan-soa:subject-id", "value": "SUBJ-001"}],
    }
    respx.get("http://aidbox.test/fhir/ResearchSubject").mock(
        return_value=httpx.Response(200, json=_subject_bundle(existing))
    )
    respx.post("http://aidbox.test/fhir/ServiceRequest").mock(
        return_value=httpx.Response(201, json={"resourceType": "ServiceRequest", "id": "sr-1"})
    )
    _mock_care_plan_empty()
    update_route = respx.put("http://aidbox.test/fhir/ResearchSubject/subj-existing")

    # Spy on the reconciliation's identifier lookup so this test fails (not just
    # vacuously passes) if the post-conditional-create reconciliation is removed.
    reconciled_subjects: list[dict] = []

    def spy_subject_identifier_of(subject: dict) -> str | None:
        reconciled_subjects.append(subject)
        return subject_identifier_of(subject)

    monkeypatch.setattr(
        "vulcan_soa.enrollment.subject_identifier_of", spy_subject_identifier_of
    )

    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok")
    result = await enroll(client, "uc1-demo-research-study", "patient-1", "SUBJ-001")
    await client.close()

    assert result["researchSubjectId"] == "subj-existing"
    assert not update_route.called
    # Positive proof the no-op path ran: reconciliation examined the existing
    # subject and saw the matching identifier (hence no update, no conflict).
    assert any(
        subject.get("id") == "subj-existing" and subject_identifier_of(subject) == "SUBJ-001"
        for subject in reconciled_subjects
    ), "reconciliation never examined the existing subject's identifier"


@respx.mock
async def test_reenroll_same_patient_different_identifier_conflicts():
    _mock_protocol()
    existing = {
        "resourceType": "ResearchSubject",
        "id": "subj-existing",
        "subject": {"reference": "Patient/patient-1"},
        "identifier": [{"system": "urn:vulcan-soa:subject-id", "value": "SUBJ-001"}],
    }
    respx.get("http://aidbox.test/fhir/ResearchSubject").mock(
        return_value=httpx.Response(200, json=_subject_bundle(existing))
    )

    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok")
    with pytest.raises(EnrollmentConflict):
        await enroll(client, "uc1-demo-research-study", "patient-1", "SUBJ-002")
    await client.close()


@respx.mock
async def test_legacy_subject_without_identifier_gains_one_via_update():
    _mock_protocol()
    existing = {
        "resourceType": "ResearchSubject",
        "id": "subj-legacy",
        "meta": {"versionId": "3"},
        "subject": {"reference": "Patient/patient-1"},
    }
    respx.get("http://aidbox.test/fhir/ResearchSubject").mock(
        return_value=httpx.Response(200, json=_subject_bundle(existing))
    )
    update_route = respx.put("http://aidbox.test/fhir/ResearchSubject/subj-legacy").mock(
        return_value=httpx.Response(
            200,
            json={**existing, "identifier": [{"system": "urn:vulcan-soa:subject-id", "value": "SUBJ-009"}]},
        )
    )
    respx.post("http://aidbox.test/fhir/ServiceRequest").mock(
        return_value=httpx.Response(201, json={"resourceType": "ServiceRequest", "id": "sr-1"})
    )
    _mock_care_plan_empty()

    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok")
    result = await enroll(client, "uc1-demo-research-study", "patient-1", "SUBJ-009")
    await client.close()

    assert result["researchSubjectId"] == "subj-legacy"
    assert update_route.called
    update_payload = json.loads(update_route.calls.last.request.content)
    assert update_payload["identifier"] == [
        {"system": "urn:vulcan-soa:subject-id", "value": "SUBJ-009"}
    ]
    assert update_route.calls.last.request.headers["If-Match"] == 'W/"3"'


@respx.mock
async def test_update_subject_state_appends_tho_state_entry():
    respx.get("http://aidbox.test/fhir/ResearchSubject/subj-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "resourceType": "ResearchSubject",
                "id": "subj-1",
                "status": "active",
                "meta": {"versionId": "2"},
                "study": {"reference": "ResearchStudy/uc1-demo-research-study"},
                "subject": {"reference": "Patient/patient-1"},
                "subjectState": [
                    {
                        "code": {
                            "coding": [
                                {
                                    "system": "http://terminology.hl7.org/CodeSystem/research-subject-state",
                                    "code": "eligible",
                                }
                            ]
                        },
                        "startDate": "2026-07-01",
                    }
                ],
            },
        )
    )
    update_route = respx.put("http://aidbox.test/fhir/ResearchSubject/subj-1").mock(
        return_value=httpx.Response(200, json={"resourceType": "ResearchSubject", "id": "subj-1"})
    )

    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok")
    await update_subject_state(client, "uc1-demo-research-study", "subj-1", "on-study")
    await client.close()

    payload = json.loads(update_route.calls.last.request.content)
    assert update_route.calls.last.request.headers["If-Match"] == 'W/"2"'
    new_entry = payload["subjectState"][-1]
    assert new_entry["code"]["coding"] == [
        {
            "system": "http://terminology.hl7.org/CodeSystem/research-subject-state",
            "code": "on-study",
        }
    ]
    assert new_entry["startDate"]


async def test_update_subject_state_rejects_code_outside_value_set():
    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok")
    with pytest.raises(ValueError, match="Invalid research subject state"):
        # R6-build draft code, not in THO research-subject-state
        await update_subject_state(client, "uc1-demo-research-study", "subj-1", "in-screening")
    await client.close()


@respx.mock
async def test_update_subject_state_rejects_subject_from_another_study():
    respx.get("http://aidbox.test/fhir/ResearchSubject/subj-1").mock(
        return_value=httpx.Response(
            200,
            json={
                "resourceType": "ResearchSubject",
                "id": "subj-1",
                "status": "active",
                "study": {"reference": "ResearchStudy/other-study"},
                "subject": {"reference": "Patient/patient-1"},
            },
        )
    )

    client = FhirClient(base_url="http://aidbox.test/fhir", access_token="tok")
    with pytest.raises(ValueError, match="does not belong to study"):
        await update_subject_state(client, "uc1-demo-research-study", "subj-1", "on-study")
    await client.close()
