"""Idempotent persistence of the central role/permission vocabulary."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from researchhub.core.permissions import ROLE_PERMISSIONS, Permissions, Roles
from researchhub.infrastructure.persistence.models import (
    Permission,
    Role,
    RolePermission,
    UserRole,
)


@dataclass(frozen=True)
class RbacSeedResult:
    roles_created: int
    permissions_created: int
    grants_created: int


async def seed_authorization_vocabulary(session: AsyncSession) -> RbacSeedResult:
    """Create missing system roles, permissions and grants without deleting data."""

    roles = {item.name: item for item in (await session.scalars(select(Role))).all()}
    permissions = {
        item.code: item for item in (await session.scalars(select(Permission))).all()
    }
    roles_created = 0
    permissions_created = 0

    for name in Roles.all():
        if name not in roles:
            role = Role(name=name, description=_role_description(name), is_system=True)
            session.add(role)
            roles[name] = role
            roles_created += 1
    for code in sorted(Permissions.all()):
        if code not in permissions:
            permission = Permission(code=code, description=_permission_description(code))
            session.add(permission)
            permissions[code] = permission
            permissions_created += 1
    await session.flush()

    existing = set(
        (
            await session.execute(
                select(RolePermission.role_id, RolePermission.permission_id)
            )
        ).tuples()
    )
    grants_created = 0
    for role_name, codes in ROLE_PERMISSIONS.items():
        role = roles[role_name]
        for code in codes:
            permission = permissions[code]
            key = (role.id, permission.id)
            if key not in existing:
                session.add(RolePermission(role_id=role.id, permission_id=permission.id))
                existing.add(key)
                grants_created += 1
    return RbacSeedResult(roles_created, permissions_created, grants_created)


async def assign_role(session: AsyncSession, user_id: UUID, role_name: str) -> bool:
    """Assign one existing role, returning whether a new assignment was made."""

    role = await session.scalar(select(Role).where(Role.name == role_name))
    if role is None:
        raise LookupError(f"Role vocabulary has not been seeded: {role_name}")
    existing = await session.scalar(
        select(UserRole.id).where(UserRole.user_id == user_id, UserRole.role_id == role.id)
    )
    if existing is not None:
        return False
    session.add(UserRole(user_id=user_id, role_id=role.id))
    return True


def _role_description(name: str) -> str:
    return f"ResearchHub system role: {name.replace('_', ' ').title()}"


def _permission_description(code: str) -> str:
    resource, action = code.split(".", 1)
    return f"Allow {action.replace('_', ' ')} access to {resource.replace('_', ' ')}."
