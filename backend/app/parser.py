import re
from typing import List, Dict

CURRENCY_RE = re.compile(r"[\$£€]\s*\d+|\d+\s*(?:USD|EUR|GBP)")

def strip_price(s: str) -> str:
    return CURRENCY_RE.sub("", s).strip()


def parse_lines(lines: List[str]) -> List[Dict]:
    items = []
    seen = set()
    for i, line in enumerate(lines):
        # remove lines that are too short or look like prices
        if len(line) < 2:
            continue
        if CURRENCY_RE.search(line):
            # possibly "Pizza Margherita 12.99" -> split and keep left side
            cleaned = strip_price(line)
            if cleaned:
                line = cleaned
            else:
                continue
        # remove lines with too many commas (likely descriptions) but keep title-like
        candidate = line
        # dedupe
        key = candidate.lower()
        if key in seen:
            continue
        seen.add(key)
        items.append({"id": str(i), "text": candidate})
    return items
