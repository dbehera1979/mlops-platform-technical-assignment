from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from app.core.security import authenticate_demo_user, create_access_token
from app.schemas.auth import TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse)
async def login(form_data: OAuth2PasswordRequestForm = Depends()) -> TokenResponse:
    """Demo token issuance — see app/core/security.py docstring. Use
    username one of admin/approver/operator/viewer; password is ignored."""
    user = authenticate_demo_user(form_data.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unknown demo user. Use admin/approver/operator/viewer.",
        )
    token = create_access_token(user)
    return TokenResponse(access_token=token)
