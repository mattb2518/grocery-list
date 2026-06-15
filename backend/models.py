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


class CheckRequest(BaseModel):
    checked: bool


class Item(BaseModel):
    id: int
    name: str
    category: str
    submitted_by: str
    submitted_at: datetime
    list_id: int
    checked: int

    class Config:
        from_attributes = True


class ActiveList(BaseModel):
    list_id: int
    created_at: datetime
    items: list[Item]


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
