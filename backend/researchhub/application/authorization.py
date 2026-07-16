"""Database-backed centralized authorization checks."""

from __future__ import annotations

from collections.abc import Collection
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from researchhub.core.permissions import Roles
from researchhub.infrastructure.persistence.models import (
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)


class AuthorizationService:
    """Resolve RBAC grants and tenant scope without route-local role checks."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def role_names(self, user_id: UUID) -> frozenset[str]:
        values = await self.session.scalars(
            select(Role.name)
            .join(UserRole, UserRole.role_id == Role.id)
            .where(UserRole.user_id == user_id)
        )
        return frozenset(values.all())

    async def permission_codes(self, user_id: UUID) -> frozenset[str]:
        values = await self.session.scalars(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .join(UserRole, UserRole.role_id == RolePermission.role_id)
            .where(UserRole.user_id == user_id)
            .distinct()
        )
        return frozenset(values.all())

    async def has_permission(self, user_id: UUID, code: str) -> bool:
        roles = await self.role_names(user_id)
        if Roles.PLATFORM_ADMIN in roles:
            return True
        return code in await self.permission_codes(user_id)

    async def has_any_permission(self, user_id: UUID, codes: Collection[str]) -> bool:
        roles = await self.role_names(user_id)
        if Roles.PLATFORM_ADMIN in roles:
            return True
        return bool(await self.permission_codes(user_id) & set(codes))

    async def is_admin(self, user_id: UUID) -> bool:
        return bool(
            await self.role_names(user_id)
            & {Roles.PLATFORM_ADMIN, Roles.UNIVERSITY_ADMIN, Roles.ICT_ADMIN}
        )

    async def within_university(self, user: User, university_id: UUID) -> bool:
        if Roles.PLATFORM_ADMIN in await self.role_names(user.id):
            return True
        return user.university_id is not None and user.university_id == university_id

    async def within_department(self, user: User, department_id: UUID) -> bool:
        if Roles.PLATFORM_ADMIN in await self.role_names(user.id):
            return True
        return user.department_id is not None and user.department_id == department_id
