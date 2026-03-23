"""
BidNow property scraper module.
Handles fetching and parsing property listings from BidNow.
"""

import json
import requests
from typing import Any

BIDNOW_URL = "https://www.bidnow.my/properties/auction"
MAX_PAGES = 200
REQUEST_TIMEOUT = 20


def build_bidnow_params(state: str | None, page: int) -> dict[str, str]:
    """Build query parameters for BidNow requests."""
    params: dict[str, str] = {
        "listing_type": "Bank Auction",
        "sort": "new",
        "listing": "active",
        "listing-modal": "active",
        "page": str(page),
    }
    if state:
        params["state"] = state
        params["stateModal"] = state
    return params


def fetch_bidnow_page(state: str | None, page: int) -> str:
    """Fetch HTML from BidNow for a specific page."""
    params = build_bidnow_params(state=state, page=page)
    resp = requests.get(
        BIDNOW_URL,
        params=params,
        timeout=REQUEST_TIMEOUT,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    resp.raise_for_status()
    return resp.text


def extract_json_object_after_marker(source: str, marker: str) -> dict[str, Any] | None:
    """
    Extract JSON object from HTML source after a specific marker.
    Handles escaped strings and nested braces correctly.
    """
    marker_idx = source.find(marker)
    if marker_idx < 0:
        return None

    start = source.find("{", marker_idx)
    if start < 0:
        return None

    depth = 0
    in_string = False
    escaped = False
    end = -1

    for i in range(start, len(source)):
        ch = source[i]

        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break

    if end < 0:
        return None

    raw = source[start : end + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def extract_total_pages(html: str) -> int:
    """Extract total number of pages from BidNow response."""
    aps_payload = extract_json_object_after_marker(html, "var aps =") or {}
    aps_last_page = aps_payload.get("last_page")
    if isinstance(aps_last_page, int) and aps_last_page >= 1:
        return min(aps_last_page, MAX_PAGES)

    pagination_payload = extract_json_object_after_marker(html, "var pagination =") or {}
    pagination_last_page = pagination_payload.get("last_page")
    if isinstance(pagination_last_page, int) and pagination_last_page >= 1:
        return min(pagination_last_page, MAX_PAGES)

    return 1


def format_reserved_price(value: Any) -> str:
    """Format price value for display."""
    if value in (None, ""):
        return "N/A"
    try:
        amount = float(str(value).replace(",", ""))
        return f"Reserved Price RM {amount:,.2f}"
    except ValueError:
        return f"Reserved Price RM {value}"


def build_property_url(ap: dict[str, Any]) -> str:
    """Build full property URL from listing data."""
    property_data = ap.get("property") or {}
    slug = property_data.get("slug_title") or ""
    ap_id = ap.get("id")
    if slug and ap_id:
        return f"https://www.bidnow.my/auction-property/{slug}/{ap_id}"
    return "#"


def parse_properties(html: str, limit: int = 10000) -> list[dict[str, str]]:
    """Parse property listings from HTML."""
    aps_payload = extract_json_object_after_marker(html, "var aps =")
    if not aps_payload:
        return []

    rows = aps_payload.get("data") or []
    if not isinstance(rows, list):
        return []

    properties: list[dict[str, str]] = []

    for ap in rows:
        if not isinstance(ap, dict):
            continue

        property_data = ap.get("property") or {}
        location = (
            property_data.get("title")
            or property_data.get("full_address")
            or "No location"
        )

        auction_date = ap.get("auction_date") or "-"
        auction_time = ap.get("auction_time") or "-"
        auction_date_time = f"{auction_date} ({auction_time})"

        properties.append(
            {
                "url": build_property_url(ap),
                "location": str(location),
                "price": format_reserved_price(ap.get("reserved_price")),
                "auction_date": auction_date_time,
            }
        )

        if len(properties) >= limit:
            break

    return properties


def fetch_all_pages(state: str | None = None) -> tuple[list[dict[str, str]], int]:
    """
    Fetch all properties from all pages.
    Deduplicates by URL.
    """
    # Fetch page 1 first to discover total pages
    first_html = fetch_bidnow_page(state=state, page=1)
    total_pages = extract_total_pages(first_html)

    seen_urls: set[str] = set()
    items: list[dict[str, str]] = []

    def add_items(parsed_items: list[dict[str, str]]) -> None:
        for item in parsed_items:
            url = item.get("url", "")
            if not url:
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)
            items.append(item)

    add_items(parse_properties(first_html, limit=10000))

    # Fetch remaining pages
    for page_num in range(2, total_pages + 1):
        html = fetch_bidnow_page(state=state, page=page_num)
        parsed = parse_properties(html, limit=10000)
        if not parsed:
            continue
        add_items(parsed)

    return items, total_pages
