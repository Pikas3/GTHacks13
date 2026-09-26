from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.dependencies import Repositories, get_repositories
from app.errors import AppError, ErrorCode
from app.schemas.resource import ResourceDetail, ResourceRead

router = APIRouter(prefix="/resources", tags=["resources"])


@router.get("", response_model=list[ResourceRead])
async def list_resources(
    product: str | None = Query(None, description="Filter by (fictional) product name"),
    repos: Repositories = Depends(get_repositories),
) -> list[ResourceRead]:
    return await repos.resources.list_resources(product)


@router.get("/{resource_id}", response_model=ResourceDetail)
async def get_resource(resource_id: UUID, repos: Repositories = Depends(get_repositories)) -> ResourceDetail:
    detail = await repos.resources.get_detail(resource_id)
    if detail is None:
        raise AppError(ErrorCode.INVALID_RESOURCE, f"Unknown resource {resource_id}")
    return detail
