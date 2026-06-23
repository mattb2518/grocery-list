import os
import email
import imaplib
import logging
from email.header import decode_header, make_header
from email.utils import parseaddr

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(os.getenv("IMAP_HOST") and os.getenv("IMAP_USER") and os.getenv("IMAP_PASSWORD"))


def _open_mailbox():
    """Connect, log in, and select the configured folder. Caller must logout."""
    host = os.getenv("IMAP_HOST")
    user = os.getenv("IMAP_USER")
    password = os.getenv("IMAP_PASSWORD")
    if not (host and user and password):
        raise RuntimeError(
            "Mailbox polling is not configured (set IMAP_HOST, IMAP_USER, IMAP_PASSWORD)"
        )
    port = int(os.getenv("IMAP_PORT", "993"))
    folder = os.getenv("IMAP_FOLDER", "INBOX")
    use_ssl = os.getenv("IMAP_SSL", "true").lower() != "false"
    M = imaplib.IMAP4_SSL(host, port) if use_ssl else imaplib.IMAP4(host, port)
    M.login(user, password)
    M.select(folder)
    return M


def _close(M):
    try:
        M.close()
    except Exception:
        pass
    try:
        M.logout()
    except Exception:
        pass


def fetch_unseen() -> list[dict]:
    """Read all unseen messages WITHOUT marking them seen, returning a list of
    {uid, sender, subject, body} dicts.

    Crucially, this PEEKs (BODY.PEEK) rather than consuming the messages, so a
    downstream failure (e.g. the categorizer being unavailable) leaves the mail
    unread and retryable. Marking seen is the caller's job via mark_seen(),
    done only after a message has been successfully ingested.
    """
    M = _open_mailbox()
    messages: list[dict] = []
    try:
        typ, data = M.uid("SEARCH", None, "UNSEEN")
        if typ != "OK" or not data or not data[0]:
            return []
        for uid in data[0].split():
            typ, msg_data = M.uid("FETCH", uid, "(BODY.PEEK[])")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            msg = email.message_from_bytes(msg_data[0][1])
            messages.append({
                "uid": uid.decode() if isinstance(uid, bytes) else uid,
                "sender": parseaddr(msg.get("From", ""))[1],
                "subject": _decode_header(msg.get("Subject", "")),
                "body": _extract_body(msg),
            })
    finally:
        _close(M)
    return messages


def mark_seen(uids: list[str]) -> None:
    """Mark the given message UIDs as \\Seen. Called after successful ingest so
    only mail we've actually processed is consumed."""
    if not uids:
        return
    M = _open_mailbox()
    try:
        for uid in uids:
            M.uid("STORE", uid, "+FLAGS", "(\\Seen)")
    finally:
        _close(M)


def _decode_header(value: str) -> str:
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value or ""


def _extract_body(msg) -> str:
    """Return the plain-text body, preferring text/plain parts."""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and "attachment" not in str(
                part.get("Content-Disposition", "")
            ):
                return _decode_payload(part)
        return ""
    return _decode_payload(msg)


def _decode_payload(part) -> str:
    payload = part.get_payload(decode=True)
    if payload is None:
        return ""
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace").strip()
    except (LookupError, UnicodeDecodeError):
        return payload.decode("utf-8", errors="replace").strip()
