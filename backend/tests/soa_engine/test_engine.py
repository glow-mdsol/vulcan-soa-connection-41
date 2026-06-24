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
