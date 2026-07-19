from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class InboundEmail(BaseModel):
    sender: str
    subject: str
    body: str


class ArchiveRequest(BaseModel):
    label: Optional[str] = None
    checked_only: bool = False


class AddItemsRequest(BaseModel):
    item_ids: list[int]


class AddItemRequest(BaseModel):
    name: str
    submitted_by: str = "web"


class CheckRequest(BaseModel):
    checked: bool


class EditRequest(BaseModel):
    name: str


class CategoryRequest(BaseModel):
    category: str


class ProbablyHaveRequest(BaseModel):
    probably_have: bool


class Item(BaseModel):
    id: int
    name: str
    category: str
    submitted_by: str
    submitted_at: datetime
    list_id: int
    checked: int
    probably_have: int = 0

    class Config:
        from_attributes = True


class Recipe(BaseModel):
    id: int
    list_id: int
    url: str
    submitter: str
    archived: int
    created_at: datetime

    class Config:
        from_attributes = True


class ActiveList(BaseModel):
    list_id: int
    created_at: datetime
    items: list[Item]
    recipes: list[Recipe] = []


class ArchivedListSummary(BaseModel):
    list_id: int
    archived_at: Optional[datetime]
    label: Optional[str]
    item_count: int


class ArchivedListDetail(BaseModel):
    list_id: int
    archived_at: Optional[datetime]
    label: Optional[str]
    items: list[Item]
