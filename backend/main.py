import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()

from database import (
    init_db, get_connection, get_active_list, get_items_for_list,
    insert_items, archive_active_list, get_archived_lists,
    get_archived_list, copy_items_to_active, delete_item
)
from models import (
    InboundEmail, ArchiveRequest, AddItemsRequest,
    ActiveList, ArchivedListSummary, ArchivedListDetail, Item
)
from categorizer import categorize_items

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WORKER_SECRET = os.getenv("WORKER_SECRET", "")
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(lifespan=lifespan)


def _row_to_item(row) -> Item:
    return Item(
        id=row["id"],
        name=row["name"],
        category=row["category"],
        submitted_by=row["submitted_by"],
        submitted_at=row["submitted_at"],
        list_id=row["list_id"],
        checked=row["checked"]
    )


@app.post("/api/inbound-email")
async def inbound_email(
    payload: InboundEmail,
    x_worker_secret: str = Header(default="")
):
    if WORKER_SECRET and x_worker_secret != WORKER_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")

    items = categorize_items(payload.body, payload.sender, payload.subject)
    if not items:
        return {"success": True, "items_added": 0}

    sender_name = _extract_name(payload.sender)

    with get_connection() as conn:
        active = get_active_list(conn)
        insert_items(conn, items, active["id"], sender_name)

    return {"success": True, "items_added": len(items)}


@app.get("/api/list", response_model=ActiveList)
def get_list():
    with get_connection() as conn:
        active = get_active_list(conn)
        rows = get_items_for_list(conn, active["id"])
    return ActiveList(
        list_id=active["id"],
        created_at=active["created_at"],
        items=[_row_to_item(r) for r in rows]
    )


@app.post("/api/archive")
def archive(req: ArchiveRequest):
    with get_connection() as conn:
        archived_id = archive_active_list(conn, req.label)
    return {"success": True, "archived_list_id": archived_id}


@app.get("/api/archived", response_model=list[ArchivedListSummary])
def list_archived():
    with get_connection() as conn:
        rows = get_archived_lists(conn)
    return [
        ArchivedListSummary(
            list_id=r["id"],
            archived_at=r["archived_at"],
            label=r["label"],
            item_count=r["item_count"]
        )
        for r in rows
    ]


@app.get("/api/archived/{list_id}", response_model=ArchivedListDetail)
def get_archived(list_id: int):
    with get_connection() as conn:
        lst = get_archived_list(conn, list_id)
        if not lst:
            raise HTTPException(status_code=404, detail="Archived list not found")
        rows = get_items_for_list(conn, list_id)
    return ArchivedListDetail(
        list_id=lst["id"],
        archived_at=lst["archived_at"],
        label=lst["label"],
        items=[_row_to_item(r) for r in rows]
    )


@app.post("/api/restore/{list_id}")
def restore(list_id: int):
    with get_connection() as conn:
        lst = get_archived_list(conn, list_id)
        if not lst:
            raise HTTPException(status_code=404, detail="Archived list not found")
        source_ids = [r["id"] for r in get_items_for_list(conn, list_id)]
        count = copy_items_to_active(conn, source_ids) if source_ids else 0
    return {"success": True, "items_restored": count}


@app.post("/api/add-items")
def add_items(req: AddItemsRequest):
    if not req.item_ids:
        return {"success": True, "items_added": 0}
    with get_connection() as conn:
        count = copy_items_to_active(conn, req.item_ids)
    return {"success": True, "items_added": count}


@app.delete("/api/item/{item_id}")
def remove_item(item_id: int):
    with get_connection() as conn:
        ok = delete_item(conn, item_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Item not found in active list")
    return {"success": True}


# Serve frontend static files
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")


def _extract_name(email: str) -> str:
    local = email.split("@")[0]
    name = local.replace(".", " ").replace("_", " ").replace("+", " ").split()[0]
    return name.capitalize()
