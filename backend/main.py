import os
import re
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
    set_item_checked, update_item_name, update_item_category, get_archived_lists,
    get_archived_list, copy_items_to_active, delete_item,
    record_category_override, get_recent_overrides, apply_category_overrides,
    update_item_probably_have, insert_recipe, get_recipes_for_list,
    delete_recipe, archive_recipe_row, get_library_recipes,
)
from models import (
    InboundEmail, ArchiveRequest, AddItemsRequest, AddItemRequest, CheckRequest, EditRequest,
    CategoryRequest, ProbablyHaveRequest, ActiveList, ArchivedListSummary, ArchivedListDetail,
    Item, Recipe,
)
from categorizer import categorize_items
from mail_poller import fetch_unseen, mark_seen, is_configured as mailbox_configured
from recipe_parser import fetch_recipe_ingredients
from staples import is_staple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

WORKER_SECRET = os.getenv("WORKER_SECRET", "")
VALID_CATEGORIES = {"pantry", "produce", "meat", "dairy", "frozen", "deli"}
POLL_INTERVAL_MINUTES = int(os.getenv("POLL_INTERVAL_MINUTES", "15"))
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"

_SINGLE_URL_RE = re.compile(r'^https?://\S+$')


def _is_single_url(body: str) -> bool:
    return bool(_SINGLE_URL_RE.match(body.strip()))


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


def _ingest_freeform(conn, list_id: int, sender: str, subject: str, body: str) -> int:
    """Categorize one freeform email and add its items. Returns items added."""
    items = categorize_items(body, sender, subject, get_recent_overrides(conn))
    if not items:
        return 0
    apply_category_overrides(conn, items)
    return insert_items(conn, items, list_id, _extract_name(sender))


def _ingest_recipe(conn, list_id: int, sender: str, url: str) -> int:
    """Log URL, fetch and parse recipe, add ingredients. Returns items added."""
    submitter = _extract_name(sender)
    # Always log the URL first — recorded whether or not parsing succeeds
    insert_recipe(conn, list_id, url, submitter)

    result = fetch_recipe_ingredients(url)

    if not result["ingredients"]:
        # Visible notice item so the failure isn't silent
        notice = [{"name": f"Couldn't read recipe: {url}", "category": "pantry", "probably_have": 0}]
        return insert_items(conn, notice, list_id, submitter)

    # Categorize all ingredients in one call — same categorizer, unchanged prompt
    combined = "\n".join(result["ingredients"])
    items = categorize_items(combined, sender, "", get_recent_overrides(conn))
    if not items:
        return 0
    apply_category_overrides(conn, items)
    for item in items:
        item["probably_have"] = 1 if is_staple(item["name"]) else 0
    return insert_items(conn, items, list_id, submitter)


def _process_message(conn, list_id: int, sender: str, subject: str, body: str) -> int:
    """Route a message: recipe path if body is a bare URL, else freeform."""
    b = (body or "").strip()
    if _is_single_url(b):
        return _ingest_recipe(conn, list_id, sender, b)
    return _ingest_freeform(conn, list_id, sender, subject, b)


def ingest_unseen_mail() -> dict:
    """Pull all unseen mail from the mailbox and add its items. Blocking —
    call directly from sync request handlers or via asyncio.to_thread.

    Messages are only marked seen after they ingest successfully, so a transient
    failure (e.g. the categorizer being down) leaves them unread for retry
    instead of silently dropping the email."""
    messages = fetch_unseen()
    total = 0
    errors = 0
    processed_uids = []
    with get_connection() as conn:
        active = get_active_list(conn)
        for m in messages:
            try:
                total += _process_message(conn, active["id"], m["sender"], m["subject"], m["body"])
                processed_uids.append(m["uid"])
            except Exception:
                errors += 1
                logger.exception(
                    "Failed to ingest message uid=%s; leaving it unread to retry", m.get("uid")
                )
    if processed_uids:
        try:
            mark_seen(processed_uids)
        except Exception:
            logger.exception("Ingested %d message(s) but failed to mark them seen", len(processed_uids))
    return {"messages_processed": len(processed_uids), "items_added": total, "errors": errors}


def _row_to_item(row) -> Item:
    d = dict(row)
    return Item(
        id=d["id"],
        name=d["name"],
        category=d["category"],
        submitted_by=d["submitted_by"],
        submitted_at=d["submitted_at"],
        list_id=d["list_id"],
        checked=d["checked"],
        probably_have=d.get("probably_have", 0),
    )


def _row_to_recipe(row) -> Recipe:
    d = dict(row)
    return Recipe(
        id=d["id"],
        list_id=d["list_id"],
        url=d["url"],
        submitter=d["submitter"],
        archived=d["archived"],
        created_at=d["created_at"],
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
        added = _process_message(conn, active["id"], payload.sender, payload.subject, payload.body)

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
    if result["errors"] and not result["messages_processed"]:
        raise HTTPException(
            status_code=502,
            detail="Categorizer unavailable — emails left unread, try again shortly"
        )
    return {"success": True, **result}


@app.get("/api/list", response_model=ActiveList)
def get_list():
    with get_connection() as conn:
        active = get_active_list(conn)
        rows = get_items_for_list(conn, active["id"])
        recipe_rows = get_recipes_for_list(conn, active["id"])
    return ActiveList(
        list_id=active["id"],
        created_at=active["created_at"],
        items=[_row_to_item(r) for r in rows],
        recipes=[_row_to_recipe(r) for r in recipe_rows],
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


@app.post("/api/item/{item_id}/category")
def recategorize_item(item_id: int, req: CategoryRequest):
    category = req.category.strip().lower()
    if category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail="Invalid category")
    with get_connection() as conn:
        ok = update_item_category(conn, item_id, category)
        if not ok:
            raise HTTPException(status_code=404, detail="Item not found in active list")
        row = conn.execute("SELECT name FROM items WHERE id = ?", (item_id,)).fetchone()
        if row:
            record_category_override(conn, row["name"], category)
    return {"success": True}


@app.post("/api/item/{item_id}/probably-have")
def set_probably_have(item_id: int, req: ProbablyHaveRequest):
    with get_connection() as conn:
        ok = update_item_probably_have(conn, item_id, req.probably_have)
    if not ok:
        raise HTTPException(status_code=404, detail="Item not found in active list")
    return {"success": True}


@app.delete("/api/recipe/{recipe_id}")
def remove_recipe(recipe_id: int):
    with get_connection() as conn:
        ok = delete_recipe(conn, recipe_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Recipe not found")
    return {"success": True}


@app.get("/api/recipes/library", response_model=list[Recipe])
def get_recipe_library():
    with get_connection() as conn:
        rows = get_library_recipes(conn)
    return [_row_to_recipe(r) for r in rows]


@app.post("/api/recipe/{recipe_id}/archive")
def archive_recipe_entry(recipe_id: int):
    with get_connection() as conn:
        ok = archive_recipe_row(conn, recipe_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Recipe not found")
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


@app.post("/api/add-item")
def add_item(req: AddItemRequest):
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Item name is required")
    with get_connection() as conn:
        active = get_active_list(conn)
        items = categorize_items(name, req.submitted_by, "", get_recent_overrides(conn))
        if not items:
            items = [{"name": name, "category": "pantry"}]
        apply_category_overrides(conn, items)
        count = insert_items(conn, items, active["id"], req.submitted_by)
    return {"success": True, "items_added": count, "items": items}


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
