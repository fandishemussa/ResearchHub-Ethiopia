"""Central enterprise role and permission vocabulary.

Route handlers must import these constants instead of comparing role-name
strings.  The matrix is also the source used by the RBAC seed command and the
authorization documentation.
"""

from __future__ import annotations


class Permissions:
    SOURCES_READ = "sources.read"
    SOURCES_MANAGE = "sources.manage"
    HARVEST_START = "harvest.start"
    HARVEST_CANCEL = "harvest.cancel"
    IMPORTS_CREATE = "imports.create"
    PUBLICATIONS_READ = "publications.read"
    PUBLICATIONS_MANAGE = "publications.manage"
    METADATA_CORRECT = "metadata.correct"
    METADATA_APPROVE = "metadata.approve"
    DOCUMENTS_READ = "documents.read"
    DOCUMENTS_MANAGE = "documents.manage"
    DOCUMENTS_DOWNLOAD = "documents.download"
    AI_USE = "ai.use"
    AI_MANAGE = "ai.manage"
    USERS_READ = "users.read"
    USERS_MANAGE = "users.manage"
    ROLES_MANAGE = "roles.manage"
    AUDIT_READ = "audit.read"
    REPORTS_EXPORT = "reports.export"
    SETTINGS_MANAGE = "settings.manage"

    @classmethod
    def all(cls) -> frozenset[str]:
        return frozenset(
            value for name, value in vars(cls).items() if name.isupper() and isinstance(value, str)
        )


class Roles:
    PLATFORM_ADMIN = "PLATFORM_ADMIN"
    UNIVERSITY_ADMIN = "UNIVERSITY_ADMIN"
    ICT_ADMIN = "ICT_ADMIN"
    RESEARCH_OFFICE_DIRECTOR = "RESEARCH_OFFICE_DIRECTOR"
    RESEARCH_OFFICE_OFFICER = "RESEARCH_OFFICE_OFFICER"
    LIBRARY_ADMIN = "LIBRARY_ADMIN"
    METADATA_OFFICER = "METADATA_OFFICER"
    COLLEGE_ADMIN = "COLLEGE_ADMIN"
    DEPARTMENT_COORDINATOR = "DEPARTMENT_COORDINATOR"
    RESEARCHER = "RESEARCHER"
    GRADUATE_STUDENT = "GRADUATE_STUDENT"
    PUBLIC_USER = "PUBLIC_USER"
    AUDITOR = "AUDITOR"

    @classmethod
    def all(cls) -> tuple[str, ...]:
        return tuple(
            value for name, value in vars(cls).items() if name.isupper() and isinstance(value, str)
        )


READ_ONLY = frozenset(
    {
        Permissions.SOURCES_READ,
        Permissions.PUBLICATIONS_READ,
        Permissions.DOCUMENTS_READ,
    }
)

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    Roles.PLATFORM_ADMIN: Permissions.all(),
    Roles.UNIVERSITY_ADMIN: Permissions.all()
    - {Permissions.ROLES_MANAGE, Permissions.SETTINGS_MANAGE},
    Roles.ICT_ADMIN: frozenset(
        {
            Permissions.SOURCES_READ,
            Permissions.SOURCES_MANAGE,
            Permissions.HARVEST_START,
            Permissions.HARVEST_CANCEL,
            Permissions.DOCUMENTS_READ,
            Permissions.DOCUMENTS_MANAGE,
            Permissions.AI_MANAGE,
            Permissions.USERS_READ,
            Permissions.AUDIT_READ,
            Permissions.SETTINGS_MANAGE,
        }
    ),
    Roles.RESEARCH_OFFICE_DIRECTOR: READ_ONLY
    | frozenset(
        {
            Permissions.PUBLICATIONS_MANAGE,
            Permissions.METADATA_CORRECT,
            Permissions.METADATA_APPROVE,
            Permissions.AI_USE,
            Permissions.USERS_READ,
            Permissions.AUDIT_READ,
            Permissions.REPORTS_EXPORT,
        }
    ),
    Roles.RESEARCH_OFFICE_OFFICER: READ_ONLY
    | frozenset(
        {
            Permissions.PUBLICATIONS_MANAGE,
            Permissions.METADATA_CORRECT,
            Permissions.AI_USE,
            Permissions.REPORTS_EXPORT,
        }
    ),
    Roles.LIBRARY_ADMIN: READ_ONLY
    | frozenset(
        {
            Permissions.SOURCES_MANAGE,
            Permissions.HARVEST_START,
            Permissions.HARVEST_CANCEL,
            Permissions.IMPORTS_CREATE,
            Permissions.PUBLICATIONS_MANAGE,
            Permissions.METADATA_CORRECT,
            Permissions.METADATA_APPROVE,
            Permissions.DOCUMENTS_MANAGE,
            Permissions.DOCUMENTS_DOWNLOAD,
            Permissions.REPORTS_EXPORT,
        }
    ),
    Roles.METADATA_OFFICER: READ_ONLY
    | frozenset(
        {
            Permissions.IMPORTS_CREATE,
            Permissions.PUBLICATIONS_MANAGE,
            Permissions.METADATA_CORRECT,
            Permissions.DOCUMENTS_MANAGE,
        }
    ),
    Roles.COLLEGE_ADMIN: READ_ONLY
    | frozenset({Permissions.AI_USE, Permissions.USERS_READ, Permissions.REPORTS_EXPORT}),
    Roles.DEPARTMENT_COORDINATOR: READ_ONLY
    | frozenset({Permissions.AI_USE, Permissions.METADATA_CORRECT, Permissions.REPORTS_EXPORT}),
    Roles.RESEARCHER: READ_ONLY | frozenset({Permissions.AI_USE, Permissions.DOCUMENTS_DOWNLOAD}),
    Roles.GRADUATE_STUDENT: READ_ONLY
    | frozenset({Permissions.AI_USE, Permissions.DOCUMENTS_DOWNLOAD}),
    Roles.PUBLIC_USER: frozenset({Permissions.PUBLICATIONS_READ}),
    Roles.AUDITOR: READ_ONLY | frozenset({Permissions.AUDIT_READ, Permissions.REPORTS_EXPORT}),
}
