from enum import Enum


class RoleEnum(str, Enum):
    """Role enum — single source of truth for roles used by models, auth, and deps."""

    admin = "admin"
    operator = "operator"
    readonly = "readonly"
