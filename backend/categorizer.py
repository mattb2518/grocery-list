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


def categorize_items(body: str, sender: str) -> list[dict]:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    user_message = f"Categorize the grocery items in this message:\n{body}\n\nSender: {sender}"

    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1024,
        system=SYSTEM_PROMPT,
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
