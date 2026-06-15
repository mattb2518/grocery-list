import sqlite3
import os
from datetime import datetime, timezone

DATABASE_PATH = os.getenv("DATABASE_PATH", "./data/grocery.db")


def get_connection():
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    with get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS lists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT NOT NULL,
                created_at DATETIME NOT NULL,
                archived_at DATETIME,
                label TEXT
            );

            CREATE TABLE IF NOT EXISTS items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                submitted_by TEXT NOT NULL,
                submitted_at DATETIME NOT NULL,
                list_id INTEGER NOT NULL,
                checked INTEGER DEFAULT 0
            );
        """)
        # Ensure there is always one active list
        active = conn.execute(
            "SELECT id FROM lists WHERE status = 'active' LIMIT 1"
        ).fetchone()
        if not active:
            conn.execute(
                "INSERT INTO lists (status, created_at) VALUES ('active', ?)",
                (datetime.now(timezone.utc).isoformat(),)
            )
        conn.commit()


def get_active_list(conn):
    return conn.execute(
        "SELECT * FROM lists WHERE status = 'active' LIMIT 1"
    ).fetchone()


def get_items_for_list(conn, list_id: int):
    return conn.execute(
        "SELECT * FROM items WHERE list_id = ? ORDER BY submitted_at ASC",
        (list_id,)
    ).fetchall()


def insert_items(conn, items: list[dict], list_id: int, submitted_by: str):
    now = datetime.now(timezone.utc).isoformat()
    # Fetch existing item names on this list for deduplication (case-insensitive)
    existing = {
        row["name"].lower()
        for row in conn.execute(
            "SELECT name FROM items WHERE list_id = ?", (list_id,)
        ).fetchall()
    }
    new_items = [
        i for i in items if i["name"].lower() not in existing
    ]
    if new_items:
        conn.executemany(
            "INSERT INTO items (name, category, submitted_by, submitted_at, list_id) VALUES (?, ?, ?, ?, ?)",
            [(i["name"], i["category"], submitted_by, now, list_id) for i in new_items]
        )
        conn.commit()
    return len(new_items)


def archive_active_list(conn, label: str | None = None):
    active = get_active_list(conn)
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        "UPDATE lists SET status = 'archived', archived_at = ?, label = ? WHERE id = ?",
        (now, label, active["id"])
    )
    conn.execute(
        "INSERT INTO lists (status, created_at) VALUES ('active', ?)",
        (now,)
    )
    conn.commit()
    return active["id"]


def archive_checked_items(conn, label: str | None = None):
    """Archive only the checked items from the active list into a new archived
    list, leaving the unchecked items on the active list. Returns the new
    archived list id, or None if there were no checked items."""
    active = get_active_list(conn)
    now = datetime.now(timezone.utc).isoformat()
    checked = conn.execute(
        "SELECT COUNT(*) AS c FROM items WHERE list_id = ? AND checked = 1",
        (active["id"],)
    ).fetchone()["c"]
    if not checked:
        return None
    cur = conn.execute(
        "INSERT INTO lists (status, created_at, archived_at, label) VALUES ('archived', ?, ?, ?)",
        (now, now, label)
    )
    archived_id = cur.lastrowid
    conn.execute(
        "UPDATE items SET list_id = ? WHERE list_id = ? AND checked = 1",
        (archived_id, active["id"])
    )
    conn.commit()
    return archived_id


def set_item_checked(conn, item_id: int, checked: bool):
    active = get_active_list(conn)
    result = conn.execute(
        "UPDATE items SET checked = ? WHERE id = ? AND list_id = ?",
        (1 if checked else 0, item_id, active["id"])
    )
    conn.commit()
    return result.rowcount > 0


def get_archived_lists(conn):
    rows = conn.execute(
        """
        SELECT l.id, l.archived_at, l.label, COUNT(i.id) AS item_count
        FROM lists l
        LEFT JOIN items i ON i.list_id = l.id
        WHERE l.status = 'archived'
        GROUP BY l.id
        ORDER BY l.archived_at DESC
        """
    ).fetchall()
    return rows


def get_archived_list(conn, list_id: int):
    return conn.execute(
        "SELECT * FROM lists WHERE id = ? AND status = 'archived'",
        (list_id,)
    ).fetchone()


def copy_items_to_active(conn, item_ids: list[int]):
    active = get_active_list(conn)
    now = datetime.now(timezone.utc).isoformat()
    placeholders = ",".join("?" * len(item_ids))
    source_items = conn.execute(
        f"SELECT name, category, submitted_by FROM items WHERE id IN ({placeholders})",
        item_ids
    ).fetchall()
    conn.executemany(
        "INSERT INTO items (name, category, submitted_by, submitted_at, list_id) VALUES (?, ?, ?, ?, ?)",
        [(r["name"], r["category"], r["submitted_by"], now, active["id"]) for r in source_items]
    )
    conn.commit()
    return len(source_items)


def delete_item(conn, item_id: int):
    active = get_active_list(conn)
    result = conn.execute(
        "DELETE FROM items WHERE id = ? AND list_id = ?",
        (item_id, active["id"])
    )
    conn.commit()
    return result.rowcount > 0
