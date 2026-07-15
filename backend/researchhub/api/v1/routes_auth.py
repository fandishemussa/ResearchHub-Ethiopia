"""OAuth2 login and revocable session endpoints."""

from hashlib import sha256
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from redis.asyncio import Redis

from researchhub.api.v1.dependencies import get_authentication_service, require_authenticated_user
from researchhub.application.auth import (
    AccountLockedError,
    AuthenticationError,
    AuthenticationService,
)
from researchhub.domain.schemas import (
    EmailVerifyRequest,
    LogoutRequest,
    PasswordChangeRequest,
    PasswordForgotRequest,
    PasswordResetRequest,
    RefreshRequest,
    RefreshSessionRead,
    TokenResponse,
    UserRead,
)
from researchhub.infrastructure.coordination import check_rate_limit
from researchhub.infrastructure.persistence.models import User
from researchhub.infrastructure.redis import get_redis

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    response: Response,
    form: OAuth2PasswordRequestForm = Depends(),
    service: AuthenticationService = Depends(get_authentication_service),
    redis: Redis = Depends(get_redis),
) -> TokenResponse:
    await _rate_limit(request, response, redis, "login", form.username, 10, 60)
    try:
        _, access, refresh, expires = await service.login(
            form.username,
            form.password,
            user_agent=request.headers.get("user-agent"),
            ip_address=_client_ip(request),
        )
    except AccountLockedError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    return TokenResponse(access_token=access, refresh_token=refresh, expires_at=expires)


@router.post("/refresh", response_model=TokenResponse)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    response: Response,
    service: AuthenticationService = Depends(get_authentication_service),
    redis: Redis = Depends(get_redis),
) -> TokenResponse:
    await _rate_limit(request, response, redis, "refresh", "", 30, 60)
    try:
        _, access, replacement, expires = await service.refresh(
            payload.refresh_token,
            user_agent=request.headers.get("user-agent"),
            ip_address=_client_ip(request),
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return TokenResponse(access_token=access, refresh_token=replacement, expires_at=expires)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    payload: LogoutRequest, service: AuthenticationService = Depends(get_authentication_service)
) -> Response:
    await service.logout(payload.refresh_token)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
async def logout_all(
    user: User = Depends(require_authenticated_user),
    service: AuthenticationService = Depends(get_authentication_service),
) -> Response:
    await service.revoke_all(user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me", response_model=UserRead)
async def me(user: User = Depends(require_authenticated_user)) -> UserRead:
    return UserRead.model_validate(user)


@router.get("/sessions", response_model=list[RefreshSessionRead])
async def sessions(
    user: User = Depends(require_authenticated_user),
    service: AuthenticationService = Depends(get_authentication_service),
) -> list[RefreshSessionRead]:
    return [RefreshSessionRead.model_validate(item) for item in await service.sessions(user.id)]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    session_id: UUID,
    user: User = Depends(require_authenticated_user),
    service: AuthenticationService = Depends(get_authentication_service),
) -> Response:
    if not await service.revoke_session(user.id, session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/password/change", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: PasswordChangeRequest,
    user: User = Depends(require_authenticated_user),
    service: AuthenticationService = Depends(get_authentication_service),
) -> Response:
    try:
        await service.change_password(user, payload.current_password, payload.new_password)
    except (AuthenticationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/password/forgot", status_code=status.HTTP_202_ACCEPTED)
async def forgot_password(
    payload: PasswordForgotRequest,
    request: Request,
    response: Response,
    service: AuthenticationService = Depends(get_authentication_service),
    redis: Redis = Depends(get_redis),
) -> dict[str, str]:
    await _rate_limit(request, response, redis, "password-reset", payload.email, 5, 900)
    await service.request_password_reset(payload.email)
    return {"message": "If the account exists, password reset instructions will be sent."}


@router.post("/password/reset", status_code=status.HTTP_204_NO_CONTENT)
async def reset_password(
    payload: PasswordResetRequest,
    service: AuthenticationService = Depends(get_authentication_service),
) -> Response:
    try:
        await service.reset_password(payload.token, payload.new_password)
    except (AuthenticationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/email/verify", status_code=status.HTTP_204_NO_CONTENT)
async def verify_email(
    payload: EmailVerifyRequest,
    service: AuthenticationService = Depends(get_authentication_service),
) -> Response:
    try:
        await service.verify_email(payload.token)
    except AuthenticationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _rate_limit(
    request: Request,
    response: Response,
    redis: Redis,
    operation: str,
    identifier: str,
    limit: int,
    window: int,
) -> None:
    digest = sha256(f"{_client_ip(request)}:{identifier.casefold()}".encode()).hexdigest()
    try:
        result = await check_rate_limit(
            redis, operation, digest, limit=limit, window_seconds=window
        )
        response.headers["X-RateLimit-Limit"] = str(result.limit)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        response.headers["X-RateLimit-Reset"] = str(result.retry_after)
        if not result.allowed:
            raise HTTPException(
                status_code=429,
                detail="Too many authentication attempts",
                headers={"Retry-After": str(result.retry_after)},
            )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Authentication rate limiting is temporarily unavailable",
            headers={"Retry-After": "5"},
        ) from exc


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"
