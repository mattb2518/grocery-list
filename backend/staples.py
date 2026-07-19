STAPLES = [
    "salt", "pepper", "black pepper", "kosher salt", "sea salt",
    "olive oil", "vegetable oil", "canola oil", "cooking oil",
    "butter", "flour", "all-purpose flour",
    "sugar", "granulated sugar", "brown sugar",
    "water", "baking soda", "baking powder",
    "garlic powder", "onion powder",
]

_STAPLES_LOWER = {s.lower() for s in STAPLES}


def is_staple(ingredient_line: str) -> bool:
    """True if any staple keyword appears in the ingredient line (case-insensitive)."""
    line = ingredient_line.lower()
    return any(s in line for s in _STAPLES_LOWER)
