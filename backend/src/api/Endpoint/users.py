"""List local user scopes with empty-database profile initialization.

The repository serializes first-use initialization so an empty users table gains
one default profile. These profiles do not authenticate or authorize callers.
"""

from typing import Annotated

from fastapi import APIRouter, Depends

from api.user_deps import UserRepository, UserResponse, get_user_repository


router = APIRouter()


@router.get("/users", response_model=list[UserResponse], tags=["Users"])
def list_users(repository: Annotated[UserRepository, Depends(get_user_repository)]):
    """List local profiles in database ID order.

    Creates Jamie Davis only when the database has no users. These local profiles
    are not authenticated accounts.

    No request body is required. Listing may write the initial default profile;
    subsequent requests preserve existing profiles.

    Args:
        repository (UserRepository): Injected profile persistence dependency.

    Returns:
        list[UserResponse]: HTTP 200 profiles in ascending database ID order.

    Raises:
        Exception: Unhandled database, configuration, or stored-row validation
            failures become HTTP 500.
    """
    # 1. Keep default-profile initialization and ordering in the repository layer.
    return repository.list_users()
