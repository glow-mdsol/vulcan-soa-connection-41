from fastapi import APIRouter, Depends, Request, Response

from vulcan_soa.api.deps import SESSION_COOKIE_NAME, get_current_session, get_session_store
from vulcan_soa.auth import Session
from vulcan_soa.store import InMemoryStore

router = APIRouter(prefix="/api")


@router.get("/context")
async def get_context(session: Session = Depends(get_current_session)) -> dict:
    return {"patientId": session.patient_id, "researchStudyId": session.research_study_id}


@router.delete("/context", status_code=204)
async def clear_context(
    request: Request,
    response: Response,
    session_store: InMemoryStore = Depends(get_session_store),
) -> Response:
    session_id = request.cookies.get(SESSION_COOKIE_NAME)
    if session_id:
        session_store.pop(session_id)
    response.delete_cookie(SESSION_COOKIE_NAME, httponly=True, samesite="lax")
    response.status_code = 204
    return response
