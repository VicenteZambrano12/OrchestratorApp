from typing import Annotated

from fastapi import APIRouter, Depends

from api.user_deps import UserRepository, UserResponse, get_user_repository


router = APIRouter()


@router.get("/users", response_model=list[UserResponse], tags=["Users"])
def list_users(repository: Annotated[UserRepository, Depends(get_user_repository)]):
    """List profiles by ID, creating Jamie Davis only when the database has no users.

    These local profiles are not authenticated accounts.
    """
    return repository.list_users()
