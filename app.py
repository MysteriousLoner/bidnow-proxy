from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

BIDNOW_URL = "https://www.bidnow.my/properties/auction"
MAX_PAGES = 200
CACHE_TTL_SECONDS = 24 * 60 * 60
BACKGROUND_RECRAWL_SECONDS = 24 * 60 * 60

_CACHE_LOCK = threading.Lock()
_LISTING_CACHE: dict[str, dict[str, Any]] = {}
_BACKGROUND_WORKER_STARTED = False

app = Flask(__name__)
CORS(app)


def _build_bidnow_params(state: str | None, page: int) -> dict[str, str]:
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


def _extract_json_object_after_marker(source: str, marker: str) -> dict[str, Any] | None:
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


def _format_reserved_price(value: Any) -> str:
    if value in (None, ""):
        return "N/A"
    try:
        amount = float(str(value).replace(",", ""))
        return f"Reserved Price RM {amount:,.2f}"
    except ValueError:
        return f"Reserved Price RM {value}"


def _build_property_url(ap: dict[str, Any]) -> str:
    property_data = ap.get("property") or {}
    slug = property_data.get("slug_title") or ""
    ap_id = ap.get("id")
    if slug and ap_id:
        return f"https://www.bidnow.my/auction-property/{slug}/{ap_id}"
    return "#"


def _build_image_url(ap: dict[str, Any]) -> str:
    image = ap.get("image") or {}
    image_path = image.get("image_path") if isinstance(image, dict) else None
    if image_path:
        if str(image_path).startswith("http"):
            return str(image_path)
        return f"https://www.bidnow.my/{str(image_path).lstrip('/')}"

    property_data = ap.get("property") or {}
    primary_photo = property_data.get("primary_photo") or ""
    return primary_photo if isinstance(primary_photo, str) else ""


def _parse_properties(html: str, limit: int) -> list[dict[str, str]]:
    aps_payload = _extract_json_object_after_marker(html, "var aps =")
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
                "url": _build_property_url(ap),
                "location": str(location),
                "price": _format_reserved_price(ap.get("reserved_price")),
                "auction_date": auction_date_time,
                "image": _build_image_url(ap),
            }
        )

        if len(properties) >= limit:
            break

    return properties


def _extract_total_pages(html: str) -> int:
    # Prefer aps.last_page because it is in the same payload as listing data.
    aps_payload = _extract_json_object_after_marker(html, "var aps =") or {}
    aps_last_page = aps_payload.get("last_page")
    if isinstance(aps_last_page, int) and aps_last_page >= 1:
        return min(aps_last_page, MAX_PAGES)

    # Fallback to separate pagination object if available.
    pagination_payload = _extract_json_object_after_marker(html, "var pagination =") or {}
    pagination_last_page = pagination_payload.get("last_page")
    if isinstance(pagination_last_page, int) and pagination_last_page >= 1:
        return min(pagination_last_page, MAX_PAGES)

    return 1


def _cache_key(state: str | None) -> str:
    return (state or "ALL").strip().lower() or "ALL"


def _get_cached_items(state: str | None) -> tuple[list[dict[str, str]] | None, int | None, bool]:
    key = _cache_key(state)
    now = time.time()
    with _CACHE_LOCK:
        entry = _LISTING_CACHE.get(key)
        if not entry:
            return None, None, False
        if now - float(entry.get("timestamp", 0.0)) > CACHE_TTL_SECONDS:
            _LISTING_CACHE.pop(key, None)
            return None, None, False
        return entry.get("items"), entry.get("total_pages"), True


def _set_cached_items(state: str | None, items: list[dict[str, str]], total_pages: int) -> None:
    key = _cache_key(state)
    with _CACHE_LOCK:
        _LISTING_CACHE[key] = {
            "timestamp": time.time(),
            "items": items,
            "total_pages": total_pages,
        }


def _state_from_cache_key(key: str) -> str | None:
    return None if key == "ALL" else key


def _get_cached_keys() -> list[str]:
    with _CACHE_LOCK:
        keys = list(_LISTING_CACHE.keys())
    if not keys:
        # Always keep one warm cache for unfiltered requests.
        return ["ALL"]
    return keys


def _background_recrawl_worker() -> None:
    while True:
        time.sleep(BACKGROUND_RECRAWL_SECONDS)
        keys_to_refresh = _get_cached_keys()

        for key in keys_to_refresh:
            state = _state_from_cache_key(key)
            try:
                items, total_pages = _fetch_all_pages(state=state)
                _set_cached_items(state=state, items=items, total_pages=total_pages)
            except requests.RequestException:
                # Keep existing cache on transient upstream failures.
                continue


def _start_background_recrawl_worker() -> None:
    global _BACKGROUND_WORKER_STARTED
    if _BACKGROUND_WORKER_STARTED:
        return

    # Avoid duplicate workers under Flask debug reloader.
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return

    thread = threading.Thread(target=_background_recrawl_worker, daemon=True)
    thread.start()
    _BACKGROUND_WORKER_STARTED = True


# Start worker at import time for WSGI/container runs; guard prevents duplicates.
_start_background_recrawl_worker()


def _fetch_all_pages(state: str | None) -> tuple[list[dict[str, str]], int]:
    # Fetch page 1 first to discover total pages.
    first_html = _fetch_bidnow_page(state=state, page=1)
    total_pages = _extract_total_pages(first_html)

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

    add_items(_parse_properties(first_html, limit=10000))

    for page_num in range(2, total_pages + 1):
        html = _fetch_bidnow_page(state=state, page=page_num)
        parsed = _parse_properties(html, limit=10000)
        if not parsed:
            continue
        add_items(parsed)

    return items, total_pages


def _fetch_bidnow_page(state: str | None, page: int) -> str:
    params = _build_bidnow_params(state=state, page=page)
    resp = requests.get(
        BIDNOW_URL,
        params=params,
        timeout=20,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    resp.raise_for_status()
    return resp.text


@app.get("/health")
def health() -> Any:
    return jsonify({"ok": True})


@app.get("/api/bidnow-properties")
def bidnow_properties() -> Any:
    state_arg = (request.args.get("state") or "").strip()
    state = state_arg or None

    # page is accepted for backward compatibility but aggregation now always spans all pages.
    requested_page = request.args.get("page", type=int)
    if requested_page is not None and requested_page < 1:
        requested_page = 1

    refresh = (request.args.get("refresh") or "").strip().lower() in {"1", "true", "yes"}
    limit = request.args.get("limit", type=int)
    if limit is not None:
        limit = max(1, min(limit, 10000))

    try:
        cached_items: list[dict[str, str]] | None = None
        total_pages: int | None = None
        cache_hit = False
        if not refresh:
            cached_items, total_pages, cache_hit = _get_cached_items(state)

        if cached_items is None or total_pages is None:
            items, total_pages = _fetch_all_pages(state=state)
            _set_cached_items(state=state, items=items, total_pages=total_pages)
            cache_hit = False
        else:
            items = cached_items

        if limit is not None:
            items = items[:limit]
    except requests.RequestException as exc:
        return (
            jsonify(
                {
                    "ok": False,
                    "error": "Failed to fetch from BidNow",
                    "details": str(exc),
                }
            ),
            502,
        )

    return jsonify(
        {
            "ok": True,
            "count": len(items),
            "items": items,
            "state": state,
            "page": requested_page,
            "total_pages": total_pages,
            "cached": cache_hit,
            "cache_ttl_seconds": CACHE_TTL_SECONDS,
        }
    )


if __name__ == "__main__":
    _start_background_recrawl_worker()
    app.run(host="0.0.0.0", port=8090, debug=True)
