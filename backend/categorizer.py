import os
import json
import logging
import anthropic

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"pantry", "produce", "meat", "dairy", "frozen", "deli"}

SYSTEM_PROMPT = """You are a grocery categorization assistant. Given a freeform message \
containing grocery items, extract each item and return a JSON array where each \
item has a "name" (cleaned, normalized) and "category" (one of: pantry, produce, \
meat, dairy, frozen, deli). Return ONLY valid JSON, no explanation, no markdown."""


def categorize_items(body: str, sender: str, subject: str = "", examples: list[dict] | None = None) -> list[dict]:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    system = SYSTEM_PROMPT
    if examples:
        mappings = "\n".join(f"- {e['name']} → {e['category']}" for e in examples)
        system += (
            "\n\nThis household has corrected past categorizations. Prefer these "
            "mappings, and apply the same reasoning to similar items:\n" + mappings
        )

    # Combine subject and body — items are often in the subject line
    parts = []
    if subject and subject.strip():
        parts.append(subject.strip())
    if body and body.strip():
        parts.append(body.strip())
    combined = "\n".join(parts) if parts else ""

    user_message = f"Categorize the grocery items in this message:\n{combined}\n\nSender: {sender}"

    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user_message}]
    )

    raw = message.content[0].text.strip()
    # Strip markdown code fences if the model added them despite instructions
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0].strip()

    try:
        items = json.loads(raw)
        result = []
        for item in items:
            name = str(item.get("name", "")).strip()
            category = str(item.get("category", "")).strip().lower()
            if not name:
                continue
            if category not in VALID_CATEGORIES:
                category = "pantry"
            result.append({"name": name, "category": category})
        return result
    except Exception:
        logger.error("Failed to parse categorizer response: %s", raw)
        return []
