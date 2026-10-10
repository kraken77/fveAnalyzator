"""Interní viditelnost — jen známé zaměstnanecké role, ne „cokoli mimo customer“."""
from reportgen.auth import INTERNAL_ROLES, is_internal_user
from reportgen.storage import ROLES


class _U:
    """Minimální stub Useru — auth funkce čtou jen .roles a .role."""

    def __init__(self, roles, primary=None):
        self.roles = list(roles)
        self.role = primary or (roles[0] if roles else "customer")


def test_allow_list_covers_all_registered_staff_roles():
    # Jediná neinterní registrovaná role je customer; seznam se nesmí rozejít.
    assert set(INTERNAL_ROLES) == set(ROLES) - {"customer"}


def test_known_staff_roles_are_internal():
    for r in ("admin", "antelon", "sales", "buyer", "inspector", "roofer"):
        assert is_internal_user(_U([r])) is True, r


def test_customer_is_not_internal():
    assert is_internal_user(_U(["customer"])) is False
    assert is_internal_user(None) is False


def test_unknown_role_does_not_grant_internal():
    """Dřív stačilo být „cokoli jiného než customer“ — to je bezpečnostní díra."""
    assert is_internal_user(_U(["customer", "neznama"])) is False
    assert is_internal_user(_U(["fuj"])) is False


def test_primary_role_fallback_when_roles_empty():
    assert is_internal_user(_U([], primary="sales")) is True
    assert is_internal_user(_U([], primary="customer")) is False
