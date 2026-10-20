"""Register selectable local profiles through the user repository.

This router accepts profile metadata, not credentials. Database uniqueness
conflicts are exposed without overwriting an existing profile.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from api.user_deps import UserRegistration, UserRepository, UserResponse, get_user_repository


router = APIRouter()


@router.post("/users", response_model=UserResponse, status_code=201, tags=["Users"])
def register_user(
    registration: UserRegistration,
    repository: Annotated[UserRepository, Depends(get_user_repository)],
):
    """Create a local user profile.

    The JSON body requires a username trimmed to 1–80 characters and optionally
    a weight_unit of ``kg`` (default) or ``lbs``. Unknown fields and coercion are
    rejected. No authentication is required; this is not account registration.

    Args:
        registration (UserRegistration): Validated JSON profile body.
        repository (UserRepository): Injected SQL persistence dependency.

    Returns:
        UserResponse: HTTP 201 with the new profile's ID, name, and weight unit.

    Raises:
        HTTPException: With HTTP 409 if the username already exists.
        Exception: Unhandled database/configuration failures become HTTP 500.
            FastAPI rejects invalid request bodies with HTTP 422 before entry.
    """
    # 1. Delegate uniqueness and transaction handling to the profile repository.
    return repository.create(registration)
