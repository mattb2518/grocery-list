import os
import asyncio
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
    insert_items, archive_active_list, archive_checked_items,
    set_item_checked, update_item_name, get_archived_lists,
    get_archived_list, copy_items_to_active, delete_item
)
from models import (
    InboundEmail, ArchiveRequest, AddItemsRequest, CheckRequest, EditRequest,
    ActiveList, ArchivedListSummary, ArchivedListDetail, Item
)
from categorizer import categorize_items
from mail_poller import fetch_unseen, is_configured as mailbox_configured

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WORKER_SECRET = os.getenv("WORKER_SECRET", "")
POLL_INTERVAL_MINUTES = int(os.getenv("POLL_INTERVAL_MINUTES", "15"))
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"


async def _mailbox_poll_loop():
    """Pull mechanism: periodically poll the mailbox so emails show up even
    though the primary path is push (Cloudflare Worker → /inbound-email)."""
    while True:
        await asyncio.sleep(POLL_INTERVAL_MINUTES * 60)
        try:
            result = await asyncio.to_thread(ingest_unseen_mail)
            if result["items_added"]:
                logger.info(
                    "Scheduled poll added %d item(s) from %d message(s)",
                    result["items_added"], result["messages_processed"]
                )
        except Exception:
            logger.exception("Scheduled mailbox poll failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    poll_task = None
    if mailbox_configured() and POLL_INTERVAL_MINUTES > 0:
        poll_task = asyncio.create_task(_mailbox_poll_loop())
        logger.info("Mailbox pull enabled — polling every %d min", POLL_INTERVAL_MINUTES)
    else:
        logger.info("Mailbox pull disabled (IMAP not configured or interval=0)")
    yield
    if poll_task:
        poll_task.cancel()
        try:
            await poll_task
        except asyncio.CancelledError:
            pass


app = FastAPI(lifespan=lifespan)


def _ingest_message(conn, list_id: int, sender: str, subject: str, body: str) -> int:
    """Categorize one email and add its items to a list. Returns items added."""
    items = categorize_items(body, sender, subject)
    if not items:
        return 0
    return insert_items(conn, items, list_id, _extract_name(sender))


def ingest_unseen_mail() -> dict:
    """Pull all unseen mail from the mailbox and add its items. Blocking —
    call directly from sync request handlers or via asyncio.to_thread."""
    messages = fetch_unseen()
    total = 0
    with get_connection() as conn:
        active = get_active_list(conn)
        for m in messages:
            total += _ingest_message(conn, active["id"], m["sender"], m["subject"], m["body"])
    return {"messages_processed": len(messages), "items_added": total}


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

    with get_connection() as conn:
        active = get_active_list(conn)
        added = _ingest_message(conn, active["id"], payload.sender, payload.subject, payload.body)

    return {"success": True, "items_added": added}


@app.post("/api/check-mail")
def check_mail():
    """Pull the grocery mailbox on demand instead of waiting for the next
    scheduled poll. Reads unseen messages, categorizes, and adds items."""
    if not mailbox_configured():
        raise HTTPException(status_code=503, detail="Mailbox polling is not configured")
    try:
        result = ingest_unseen_mail()
    except Exception as e:
        logger.exception("Mailbox poll failed")
        raise HTTPException(status_code=502, detail=f"Could not read mailbox: {e}")
    return {"success": True, **result}


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
        if req.checked_only:
            archived_id = archive_checked_items(conn, req.label)
            if archived_id is None:
                raise HTTPException(status_code=400, detail="No checked items to archive")
        else:
            archived_id = archive_active_list(conn, req.label)
    return {"success": True, "archived_list_id": archived_id}


@app.post("/api/item/{item_id}/check")
def check_item(item_id: int, req: CheckRequest):
    with get_connection() as conn:
        ok = set_item_checked(conn, item_id, req.checked)
    if not ok:
        raise HTTPException(status_code=404, detail="Item not found in active list")
    return {"success": True}


@app.post("/api/item/{item_id}/edit")
def edit_item(item_id: int, req: EditRequest):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name cannot be empty")
    with get_connection() as conn:
        ok = update_item_name(conn, item_id, name)
    if not ok:
        raise HTTPException(status_code=404, detail="Item not found in active list")
    return {"success": True}


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
