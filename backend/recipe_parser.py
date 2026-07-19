import json
import logging
import os
import re
from html.parser import HTMLParser

import requests
import anthropic

logger = logging.getLogger(__name__)

_USER_AGENT = "Mozilla/5.0 (compatible; GroceryListBot/1.0)"
_FETCH_TIMEOUT = 10


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._chunks = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer", "header"):
            self._skip = True

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer", "header"):
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            t = data.strip()
            if t:
                self._chunks.append(t)

    def get_text(self):
        return "\n".join(self._chunks)


def _find_recipe_schemas(data) -> list:
    """Recursively collect all schema.org Recipe objects from JSON-LD data."""
    results = []
    if isinstance(data, list):
        for item in data:
            results.extend(_find_recipe_schemas(item))
    elif isinstance(data, dict):
        t = data.get("@type", "")
        types = t if isinstance(t, list) else [t]
        if any("Recipe" in str(tp) for tp in types):
            results.append(data)
        if "@graph" in data:
            results.extend(_find_recipe_schemas(data["@graph"]))
    return results


def _extract_json_ld_ingredients(html: str) -> list[str]:
    pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.DOTALL | re.IGNORECASE,
    )
    for m in pattern.finditer(html):
        try:
            data = json.loads(m.group(1))
        except Exception:
            continue
        for schema in _find_recipe_schemas(data):
            ingredients = schema.get("recipeIngredient", [])
            cleaned = [str(i).strip() for i in ingredients if str(i).strip()]
            if cleaned:
                return cleaned
    return []


def _extract_via_claude(page_text: str) -> list[str]:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    truncated = page_text[:8000]
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": (
                "Extract only the ingredient lines from this recipe page. "
                "Return a JSON array of strings, one ingredient per entry. "
                "If this is not a recipe page or no ingredients are found, return []. "
                "Return ONLY valid JSON, nothing else.\n\n"
                + truncated
            ),
        }],
    )
    raw = message.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        result = json.loads(raw)
        if isinstance(result, list):
            return [str(i).strip() for i in result if str(i).strip()]
    except Exception:
        pass
    return []


def fetch_recipe_ingredients(url: str) -> dict:
    """
    Fetch a URL and extract ingredient lines.
    Returns {"ingredients": [...], "error": None} on success,
    or {"ingredients": [], "error": "message"} on failure.
    """
    try:
        resp = requests.get(
            url,
            timeout=_FETCH_TIMEOUT,
            headers={"User-Agent": _USER_AGENT},
            allow_redirects=True,
        )
        resp.raise_for_status()
        html = resp.text
    except Exception as exc:
        logger.warning("Failed to fetch recipe URL %s: %s", url, exc)
        return {"ingredients": [], "error": str(exc)}

    # schema.org JSON-LD first
    ingredients = _extract_json_ld_ingredients(html)
    if ingredients:
        return {"ingredients": ingredients, "error": None}

    # Claude fallback
    try:
        extractor = _TextExtractor()
        extractor.feed(html)
        page_text = extractor.get_text()
        ingredients = _extract_via_claude(page_text)
        if ingredients:
            return {"ingredients": ingredients, "error": None}
        return {"ingredients": [], "error": "No ingredients found on page"}
    except Exception as exc:
        logger.warning("Claude extraction failed for %s: %s", url, exc)
        return {"ingredients": [], "error": str(exc)}
