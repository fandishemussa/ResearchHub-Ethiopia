"""Authentication, refresh-session rotation, and recovery workflows."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from researchhub.core.auth_security import (
    TokenValidationError,
    create_access_token,
    decode_access_token,
    hash_password,
    hash_token,
    new_opaque_token,
    verify_password,
)
from researchhub.core.config import Settings
from researchhub.infrastructure.persistence.models import (
    EmailVerificationToken,
    PasswordResetToken,
    RefreshSession,
    User,
)


class AuthenticationError(ValueError):
    pass


class AccountLockedError(AuthenticationError):
    pass


class AuthenticationService:
    def __init__(self, session: AsyncSession, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    async def login(
        self, identifier: str, password: str, *, user_agent: str | None, ip_address: str | None
    ) -> tuple[User, str, str, datetime]:
        normalized = identifier.strip().casefold()
        user = await self.session.scalar(
            select(User).where(
                or_(func.lower(User.email) == normalized, func.lower(User.username) == normalized)
            )
        )
        now = datetime.now(UTC)
        if user and user.locked_until and _as_utc(user.locked_until) > now:
            raise AccountLockedError("Account is temporarily locked")
        if user is None or not verify_password(password, user.password_hash):
            if user:
                user.failed_login_attempts += 1
                if user.failed_login_attempts >= self.settings.auth_max_failed_attempts:
                    user.locked_until = now + timedelta(minutes=self.settings.auth_lockout_minutes)
                    user.failed_login_attempts = 0
                await self.session.commit()
            raise AuthenticationError("Invalid username or password")
        if not user.is_active or user.is_suspended:
            raise AuthenticationError("Account is unavailable")
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = now
        refresh, refresh_session = self._new_refresh_session(user.id, user_agent, ip_address)
        self.session.add(refresh_session)
        access, expires = create_access_token(user.id, self.settings)
        await self.session.commit()
        return user, access, refresh, expires

    async def refresh(
        self, token: str, *, user_agent: str | None, ip_address: str | None
    ) -> tuple[User, str, str, datetime]:
        token_hash = hash_token(token)
        refresh_session = await self.session.scalar(
            select(RefreshSession)
            .where(RefreshSession.token_hash == token_hash)
            .with_for_update()
        )
        now = datetime.now(UTC)
        if refresh_session is None:
            raise AuthenticationError("Invalid refresh token")
        if refresh_session.revoked_at is not None:
            await self.revoke_all(refresh_session.user_id)
            raise AuthenticationError("Refresh token reuse detected")
        if _as_utc(refresh_session.expires_at) <= now:
            refresh_session.revoked_at = now
            await self.session.commit()
            raise AuthenticationError("Refresh token expired")
        user = await self.session.get(User, refresh_session.user_id)
        if user is None or not user.is_active or user.is_suspended:
            await self.revoke_all(refresh_session.user_id)
            raise AuthenticationError("Account is unavailable")
        replacement_token, replacement = self._new_refresh_session(user.id, user_agent, ip_address)
        self.session.add(replacement)
        await self.session.flush()
        refresh_session.revoked_at = now
        refresh_session.last_used_at = now
        refresh_session.replaced_by_session_id = replacement.id
        access, expires = create_access_token(user.id, self.settings)
        await self.session.commit()
        return user, access, replacement_token, expires

    async def authenticate_access_token(self, token: str) -> User:
        try:
            payload = decode_access_token(token, self.settings)
            user_id = UUID(str(payload["sub"]))
        except (TokenValidationError, ValueError) as exc:
            raise AuthenticationError("Invalid or expired access token") from exc
        user = await self.session.get(User, user_id)
        if user is None or not user.is_active or user.is_suspended:
            raise AuthenticationError("Account is unavailable")
        return user

    async def logout(self, token: str) -> None:
        item = await self.session.scalar(
            select(RefreshSession).where(RefreshSession.token_hash == hash_token(token))
        )
        if item and item.revoked_at is None:
            item.revoked_at = datetime.now(UTC)
            await self.session.commit()

    async def revoke_all(self, user_id: UUID) -> None:
        await self.session.execute(
            update(RefreshSession)
            .where(RefreshSession.user_id == user_id, RefreshSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        await self.session.commit()

    async def sessions(self, user_id: UUID) -> list[RefreshSession]:
        return list(
            (
                await self.session.scalars(
                    select(RefreshSession)
                    .where(RefreshSession.user_id == user_id)
                    .order_by(RefreshSession.created_at.desc())
                )
            ).all()
        )

    async def revoke_session(self, user_id: UUID, session_id: UUID) -> bool:
        item = await self.session.get(RefreshSession, session_id)
        if item is None or item.user_id != user_id:
            return False
        if item.revoked_at is None:
            item.revoked_at = datetime.now(UTC)
            await self.session.commit()
        return True

    async def change_password(self, user: User, current: str, new: str) -> None:
        if not verify_password(current, user.password_hash):
            raise AuthenticationError("Current password is incorrect")
        user.password_hash = hash_password(new)
        await self.revoke_all(user.id)
        await self.session.commit()

    async def request_password_reset(self, email: str) -> str | None:
        user = await self.session.scalar(
            select(User).where(func.lower(User.email) == email.strip().casefold())
        )
        if user is None or not user.is_active:
            return None
        token = new_opaque_token()
        self.session.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hash_token(token),
                expires_at=datetime.now(UTC)
                + timedelta(minutes=self.settings.auth_reset_token_minutes),
            )
        )
        await self.session.commit()
        return token

    async def reset_password(self, token: str, new_password: str) -> None:
        item = await self.session.scalar(
            select(PasswordResetToken)
            .where(PasswordResetToken.token_hash == hash_token(token))
            .with_for_update()
        )
        now = datetime.now(UTC)
        if item is None or item.used_at is not None or _as_utc(item.expires_at) <= now:
            raise AuthenticationError("Invalid or expired reset token")
        user = await self.session.get(User, item.user_id)
        if user is None:
            raise AuthenticationError("Invalid or expired reset token")
        user.password_hash = hash_password(new_password)
        item.used_at = now
        await self.revoke_all(user.id)
        await self.session.commit()

    async def verify_email(self, token: str) -> None:
        item = await self.session.scalar(
            select(EmailVerificationToken).where(
                EmailVerificationToken.token_hash == hash_token(token)
            ).with_for_update()
        )
        now = datetime.now(UTC)
        if item is None or item.used_at is not None or _as_utc(item.expires_at) <= now:
            raise AuthenticationError("Invalid or expired verification token")
        user = await self.session.get(User, item.user_id)
        if user is None:
            raise AuthenticationError("Invalid or expired verification token")
        user.is_verified = True
        item.used_at = now
        await self.session.commit()

    def _new_refresh_session(
        self, user_id: UUID, user_agent: str | None, ip_address: str | None
    ) -> tuple[str, RefreshSession]:
        token = new_opaque_token()
        return token, RefreshSession(
            user_id=user_id,
            token_hash=hash_token(token),
            user_agent=(user_agent or "")[:500] or None,
            ip_address=(ip_address or "")[:64] or None,
            expires_at=datetime.now(UTC) + timedelta(days=self.settings.auth_refresh_token_days),
        )


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
