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
