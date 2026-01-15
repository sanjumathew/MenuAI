import re
import unicodedata
from typing import List, Dict

# Heuristic-based extractor for menu item lines. Language-agnostic where possible.

# Price / currency patterns (handles Rs, $, €, £, numbers with decimals)
PRICE_RE = re.compile(r"(₹|Rs\.?|INR|Rs|\$|€|£)?\s*[0-9]+(?:[\.,][0-9]{1,2})?\s*(?:/-)?", re.IGNORECASE)

# Common section/header words (English) to filter out. These are heuristics only.
SECTION_KEYWORDS = [
    "veg", "non-veg", "vegetarian", "non vegetarian", "snacks", "beverages", "drinks",
    "rice", "dessert", "starters", "mains", "sides", "salads", "soups", "curries", "thali",
    "menu", "specials", "combo", "set", "kitchen"
]


def is_header_like(s: str) -> bool:
    # If short and mostly uppercase / alphabetic words like "VEG SNACKS" treat as header
    t = s.strip()
    if not t:
        return True
    words = [w for w in re.split(r"\s+", t) if w]
    if len(words) <= 4 and all((w.isupper() or w.isdigit() or len(w) <= 3) for w in words):
        return True
    # contains common section keywords
    lower = t.lower()
    for kw in SECTION_KEYWORDS:
        if kw in lower:
            return True
    return False


def strip_price(s: str) -> str:
    return PRICE_RE.sub("", s).strip()


def normalize_whitespace(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def proportion_letters(s: str) -> float:
    letters = sum(1 for ch in s if unicodedata.category(ch).startswith("L"))
    if not s:
        return 0.0
    return letters / len(s)


def extract_items(lines: List[str]) -> List[Dict]:
    """Extract probable food item names from OCR lines.

    Returns a list of {id, name, original, score}
    """
    candidates = []
    seen = set()
    idx = 0
    for raw in lines:
        if not raw or not raw.strip():
            continue
        s = raw.strip()
        # normalize unicode spaces
        s = normalize_whitespace(s)
        # drop obvious headers
        if is_header_like(s):
            continue
        # remove leading bullets/numbers (allow common bullet chars)
        s = re.sub(r"^[\-\u2022\*\d\)\.]+\s*", "", s)
        # remove parenthetical notes at end or start
        s = re.sub(r"^\(|\)$", "", s)
        s = re.sub(r"\(.*?\)", "", s).strip()
        # split on separators commonly used between name and price/desc
        parts = re.split(r"\s{2,}|\s[-–—:]\s|\s\|\s|\t", s)
        name_part = parts[0]
        # remove trailing price tokens
        name_part = strip_price(name_part)
        name_part = name_part.strip(". ,:-").strip()
        if not name_part:
            continue
        # ignore lines with too many digits/punct
        if proportion_letters(name_part) < 0.4:
            # could be numeric line or address/phone
            continue
        # split comma lists into separate items if short
        if "," in name_part:
            parts2 = [normalize_whitespace(p).strip(". ,:-") for p in name_part.split(",")]
        else:
            parts2 = [name_part]
        for p in parts2:
            p = p.strip()
            if not p:
                continue
            key = p.lower()
            if key in seen:
                continue
            seen.add(key)
            # heuristic score: longer than 2 chars and decent letter proportion
            score = min(1.0, max(0.0, proportion_letters(p)))
            candidates.append({"id": str(idx), "name": p, "original": raw, "score": round(score, 2)})
            idx += 1
    return candidates
