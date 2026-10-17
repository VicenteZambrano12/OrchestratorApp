from typing import Annotated

from fastapi import APIRouter, Depends

from api.user_deps import UserRegistration, UserRepository, UserResponse, get_user_repository


router = APIRouter()


@router.post("/users", response_model=UserResponse, status_code=201, tags=["Users"])
def register_user(
    registration: UserRegistration,
    repository: Annotated[UserRepository, Depends(get_user_repository)],
):
    """Persist a local profile. Duplicate usernames return 409; no authentication is required."""
    return repository.create(registration)
