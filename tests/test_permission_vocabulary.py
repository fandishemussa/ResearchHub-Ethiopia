from researchhub.core.permissions import ROLE_PERMISSIONS, Permissions, Roles


def test_every_required_role_has_an_explicit_policy() -> None:
    assert set(ROLE_PERMISSIONS) == set(Roles.all())


def test_role_matrix_contains_only_canonical_permissions() -> None:
    canonical = Permissions.all()
    assert canonical
    assert all(grants <= canonical for grants in ROLE_PERMISSIONS.values())


def test_platform_admin_has_every_permission_and_public_user_is_read_only() -> None:
    assert ROLE_PERMISSIONS[Roles.PLATFORM_ADMIN] == Permissions.all()
    assert ROLE_PERMISSIONS[Roles.PUBLIC_USER] == {Permissions.PUBLICATIONS_READ}
