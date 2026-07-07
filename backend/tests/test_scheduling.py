import httpx
import respx

from vulcan_soa.fhir_client import FhirClient
from vulcan_soa.scheduling import load_protocol_graph, schedule_response
from vulcan_soa.soa_engine.engine import NextStep, ScheduleState
from vulcan_soa.soa_engine.graph import ProtocolGraph, VisitNode


def tiny_graph() -> ProtocolGraph:
    return ProtocolGraph(
        plan_definition_id="pd-1",
        nodes={
            "a-1": VisitNode(action_id="a-1", title="Screening", transitions=()),
            "b-2": VisitNode(action_id="b-2", title="Treatment Day 1", transitions=()),
        },
        root_ids=("a-1",),
    )


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
    response = schedule_response(state, tiny_graph())

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
    assert schedule_response(state, tiny_graph())["ambiguous"] is False


def test_schedule_response_includes_titles_for_every_graph_node():
    state = ScheduleState(
        completed_action_ids=frozenset(),
        current_action_ids=frozenset(),
        next_steps=(),
    )
    response = schedule_response(state, tiny_graph())
    assert response["titles"] == {"a-1": "Screening", "b-2": "Treatment Day 1"}
