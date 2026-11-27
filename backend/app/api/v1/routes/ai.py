"""Ad-hoc AI critique route (M1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.config import settings
from app.core.rate_limit import enforce_user_rate_limit
from app.core.security import get_current_user
from app.models.user import User
from app.schemas.ai import CritiqueRequest, CritiqueResponse
from app.services.ai_critique import get_provider

router = APIRouter(prefix="/ai", tags=["ai"])


@router.post("/critique", response_model=CritiqueResponse,
             summary="AI critique of arbitrary draft review text")
def critique(payload: CritiqueRequest,
             user: User = Depends(get_current_user)) -> CritiqueResponse:
    # Keyed by account, not address: the cost of a critique follows the person
    # asking, and one account must not reset its allowance by switching networks.
    enforce_user_rate_limit(user.id, "ai_critique",
                            max_requests=settings.ai_critique_rate_limit_max,
                            window_seconds=3600)
    return get_provider().critique(payload.title, payload.text)
