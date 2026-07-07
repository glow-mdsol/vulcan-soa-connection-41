from fastapi import FastAPI
from fastapi.testclient import TestClient

from vulcan_soa.api.context import router as context_router
from vulcan_soa.api.deps import get_current_session
from vulcan_soa.auth import Session
from vulcan_soa.store import InMemoryStore


def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.state.session_store = InMemoryStore()
    app.state.pending_launch_store = InMemoryStore()
    app.include_router(context_router)
    return app


def test_get_context_returns_401_without_session():
    client = TestClient(_build_test_app())
    response = client.get("/api/context")
    assert response.status_code == 401


def test_get_context_returns_patient_and_research_study_ids():
    app = _build_test_app()
    app.dependency_overrides[get_current_session] = lambda: Session(
        access_token="tok-1", patient_id="patient-1", research_study_id="study-1"
    )
    client = TestClient(app)

    response = client.get("/api/context")

    assert response.status_code == 200
    assert response.json() == {"patientId": "patient-1", "researchStudyId": "study-1"}


def test_delete_context_clears_the_session_cookie_and_store():
    app = _build_test_app()
    session_id = app.state.session_store.create(
        Session(access_token="tok-1", patient_id="patient-1", research_study_id="study-1")
    )
    client = TestClient(app)

    response = client.delete("/api/context", cookies={"vulcan_soa_session": session_id})

    assert response.status_code == 204
    assert app.state.session_store.get(session_id) is None
    assert "vulcan_soa_session=" in response.headers["set-cookie"]
