# CPG Activity Flow for Study Visits — Design

**Date:** 2026-07-04
**Status:** Draft, awaiting user review
**Reference:** [FHIR CPG IG — Activity Flow](https://hl7.org/fhir/uv/cpg/activityflow.html)

## Goal

Reproduce the CPG activity lifecycle — `definition → proposal → plan → order → event` —
inside the vulcan-soa app, outside any EHR, as a Connectathon demo track. The visible
deliverable is the full request chain inspectable in Aidbox: every phase a distinct
resource, linked by `basedOn`, instantiating its definition, with the CPG status
machine (`active → completed`, `active → revoked`) honoured.

The app plays all three CPG actors:

| CPG actor | Played by |
|---|---|
| Clinical reasoning system | SoA engine (emits proposals) |
| Workflow system | BFF + SPA (coordinator accepts/authorizes) |
| Performer | Study coordinator via the UI |

**Fidelity caveat:** the CPG IG is R4-based; our stack is FHIR R6 ballot3. We reproduce
the *pattern* (intent ladder, `basedOn` chains, state transitions), not CPG profile
conformance. CPG's two-step prepare/initiate operations collapse to one BFF call per
gate — the "application-level interaction" those two steps exist to allow *is* our UI.

## Decisions made during brainstorming

- **Goal:** Connectathon demo track (standards-faithful chain is the point).
- **Scope:** visits *and* in-visit activities get the lifecycle.
- **Protocol:** the WIP PhUSE IG (`~/Documents/Devel/phuseorg/fhir-schedule-of-activities-ig`),
  specifically the USDM chain — it is R6-ballot3 and complete:
  `PlanDefinition/H2Q-MC-LZZT-ProtocolDesign-USDM` (soaTransition graph + `definitionUri`
  per visit) → `E*-USDM` visit PlanDefinitions → 31 `usdm-act-*` ActivityDefinitions
  (`kind: ServiceRequest`, CDISC codes, `observationResultRequirement`).
- **UX:** visit-level gates. Coordinator promotes per visit; in-visit activity requests
  cascade in bulk with their visit.
- **Approach:** new request resource per phase, promotion via BFF endpoints
  (chosen over Aidbox custom operations and over mutating `intent` in place).

## Section 1 — Resource model & lifecycle

### Visit chain (one per SoA node)

```
ServiceRequest intent=proposal ─basedOn→ SR intent=plan ─basedOn→ SR intent=order ─basedOn→ Encounter (event)
  instantiatesUri: visit PlanDefinition (e.g. PlanDefinition/H2Q-MC-LZZT-E2-USDM)
  identifier: urn:vulcan-soa:plan-action | <protocolPdId>#<actionId>   (on EVERY resource in the chain)
```

- Each promotion **creates a new** ServiceRequest (`status: active`) and marks its
  predecessor `status: completed`.
- Phase is derived from resourceType + `intent`; chain membership from the shared
  action-tag identifier (existing `ACTION_TAG_SYSTEM`).
- `perform` creates the Encounter (`status: planned`, `basedOn` the order). From there
  the existing complete-visit flow is unchanged (`planned → completed`).

### Activity chain (cascades with the visit)

- At visit-proposal time the BFF reads the visit PlanDefinition (via the protocol
  action's `definitionUri`) and, for each action with a `definitionUri` →
  ActivityDefinition, creates an activity ServiceRequest:
  `intent: proposal`, `instantiatesUri` → the AD, `code` from `AD.code`,
  `basedOn` → the visit proposal, same action-tag identifier plus an activity
  discriminator (`<protocolPdId>#<actionId>#<activityAdId>`).
- Visit promotions cascade: each activity gets its next-phase request with
  `basedOn: [its own predecessor, the visit's new request]`; predecessors are completed.
- Activity **events** are created at visit completion: one `Procedure`
  (`status: completed`, `basedOn` the activity order) per activity.
- Stretch goal, explicitly out of scope for the first build: `Observation` stubs from
  the ADs' `observationResultRequirement` ObservationDefinitions.

### Withdrawal

`withdraw_subject` additionally revokes every still-active request in the subject's
chains (`status: revoked`) before retiring the ResearchSubject — demonstrating the
CPG `active → revoked` transition.

## Section 2 — Definitions & fixtures

- New fixture `ResearchStudy/lzzt-usdm-demo-study` with `protocol` →
  `PlanDefinition/H2Q-MC-LZZT-ProtocolDesign-USDM`. The `uc1` exit-example study stays
  as a regression fixture.
- New Taskfile target `fixtures:load-soa-ig` loading the WIP IG's
  `fsh-generated/resources/` via the existing generic loader. Path from
  `SOA_IG_RESOURCES_DIR`, default
  `~/Documents/Devel/phuseorg/fhir-schedule-of-activities-ig/fsh-generated/resources`.
- `soa_engine/graph.py` accepts both extension base URLs when locating
  `soaTransition`/`soaTimepoint`: `http://hl7.org/fhir/uv/vulcan-schedule/StructureDefinition/…`
  and `http://example.org/br-and-r/soa/StructureDefinition/…`.
- **Drift guard:** the WIP IG is moving. Everything the app relies on (protocol action
  `id`s present, `definitionUri` targets resolvable in the loaded set) is asserted by
  the fixture loader at load time so drift fails loudly before a demo, not during one.

## Section 3 — Backend

New module `backend/src/vulcan_soa/activity_flow.py` owning the request lifecycle:

- `materialize_proposal(client, patient_id, plan_definition_id, node)` — replaces
  `materialize_visit` as the engine's output. Creates the visit proposal + activity
  proposals (reads visit PD and its ADs from Aidbox).
- `promote(client, subject_id, action_id, to_phase)` — validates the current phase from
  the chain (wrong-phase attempts → 409), creates the next visit request, cascades the
  activity requests, completes predecessors.
- `perform(client, subject_id, action_id)` — creates the Encounter from the order.
- `complete(client, subject_id, action_id, transition_choice)` — completes the
  Encounter, writes activity `Procedure`s, then materializes the *next* visit's
  proposal (absorbs today's `tracking.complete_visit`).

API additions (join existing `complete` and `withdraw`):

```
POST /api/research-subjects/{id}/visits/{actionId}/plan
POST /api/research-subjects/{id}/visits/{actionId}/order
POST /api/research-subjects/{id}/visits/{actionId}/perform
```

Schedule-state derivation: `load_subject_context` additionally searches tagged
`ServiceRequest`s. Completion semantics are unchanged (Encounter `completed`); "visited"
becomes "any chain resource exists for the action". The schedule response gains a
per-action `phase` (`proposed | planned | ordered | scheduled | completed`) and, for
the current visit, its activity list with statuses.

Engine core (`graph.py` traversal, `conditions.py`, `engine.py`) is untouched apart
from the extension-URL configurability.

## Section 4 — Frontend

- `SubjectDashboard` visit cards: a five-phase stepper (chips) plus **one** gate button
  whose label follows the phase — `Accept proposal` → `Authorize` → `Perform` →
  `Complete visit`.
- The current visit expands to show its activity list with per-activity status.
- Ambiguous-transition choice UI unchanged (applies at proposal-materialization time).
- `types.ts` gains the phase/activity types; `client.ts` gains the three promotion calls.

## Section 5 — Error handling & testing

- Promotion guards in `activity_flow.py`; optimistic locking via `If-Match` as today.
- Unit tests (respx): proposal materialization (visit + activities), each promotion,
  cascade behaviour, wrong-phase guard, withdrawal revocation, schedule-state
  derivation from mixed chains.
- Golden-path integration test extends to: enroll → proposal exists → plan → order →
  perform → complete (activity Procedures written) → next proposal materialized.
- Playwright E2E updated to click through the gates on the dashboard.

## Out of scope

- CPG profile conformance / R4 compatibility.
- `RequestOrchestration` grouping (the visit request is the group anchor).
- Two-step prepare/initiate promotion endpoints.
- Activity-level individual gates in the UI.
- `Observation` generation from ObservationDefinitions (stretch, later).
- Suspend/resume (`on-hold`) transitions.
