from typing import TypeVar, Generic, Optional
from pydantic import BaseModel
from datetime import datetime

T = TypeVar('T')

class ResponseModel(BaseModel, Generic[T]):
    """Generic response model for API endpoints."""
    success: bool
    message: str
    data: Optional[T] = None

class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response model."""
    items: list[T]
    total: int
    page: int
    size: int
    pages: int

class TimeStampMixin(BaseModel):
    """Mixin for models that include timestamp fields."""
    created_at: datetime
    updated_at: datetime

class SoftDeleteMixin(BaseModel):
    """Mixin for models that support soft deletion."""
    is_active: bool = True
    deleted_at: Optional[datetime] = None 