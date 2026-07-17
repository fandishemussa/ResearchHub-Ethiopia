"""Create or update the initial verified platform administrator identity."""

from __future__ import annotations

import argparse
import asyncio
import os
from getpass import getpass

from researchhub.application.rbac import assign_role, seed_authorization_vocabulary
from researchhub.core.auth_security import hash_password
from researchhub.core.permissions import Roles
from researchhub.infrastructure.persistence.models import User
from researchhub.infrastructure.persistence.session import SessionLocal
from sqlalchemy import func, select


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--username", required=True)
    parser.add_argument("--full-name", required=True)
    parser.add_argument(
        "--password-env",
        default="RESEARCHHUB_ADMIN_PASSWORD",
        help="Environment variable containing the password (prompted when unset).",
    )
    return parser.parse_args()


async def create_admin(email: str, username: str, full_name: str, password: str) -> str:
    normalized_email = email.strip().casefold()
    normalized_username = username.strip().casefold()
    async with SessionLocal() as session:
        user = await session.scalar(select(User).where(func.lower(User.email) == normalized_email))
        if user is None:
            user = User(
                email=normalized_email,
                username=normalized_username,
                full_name=full_name.strip(),
                password_hash=hash_password(password),
                is_active=True,
                is_verified=True,
            )
            session.add(user)
            action = "created"
        else:
            user.username = normalized_username
            user.full_name = full_name.strip()
            user.password_hash = hash_password(password)
            user.is_active = True
            user.is_verified = True
            user.is_suspended = False
            action = "updated"
        await session.flush()
        await seed_authorization_vocabulary(session)
        await assign_role(session, user.id, Roles.PLATFORM_ADMIN)
        await session.commit()
        return action


def main() -> None:
    args = arguments()
    password = os.getenv(args.password_env) or getpass("Administrator password: ")
    print(asyncio.run(create_admin(args.email, args.username, args.full_name, password)))


if __name__ == "__main__":
    main()
