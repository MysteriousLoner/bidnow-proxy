from __future__ import annotations

import json
from typing import Any

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

BIDNOW_URL = "https://www.bidnow.my/properties/auction"
MAX_PAGES = 200

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

    page = request.args.get("page", type=int)
    if page is not None and page < 1:
        page = 1

    limit = request.args.get("limit", type=int)
    if limit is not None:
        limit = max(1, min(limit, 10000))

    try:
        items: list[dict[str, str]] = []
        seen_urls: set[str] = set()

        # If page is provided, return data for that page only.
        if page is not None:
            html = _fetch_bidnow_page(state=state, page=page)
            parsed = _parse_properties(html, limit=limit or 10000)
            for item in parsed:
                url = item.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    items.append(item)
            if limit is not None:
                items = items[:limit]
        else:
            # No args/page: crawl pages and return all entries (deduplicated).
            for page_num in range(1, MAX_PAGES + 1):
                html = _fetch_bidnow_page(state=state, page=page_num)
                parsed = _parse_properties(html, limit=10000)

                if not parsed:
                    break

                added = 0
                for item in parsed:
                    url = item.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        items.append(item)
                        added += 1

                        if limit is not None and len(items) >= limit:
                            break

                if limit is not None and len(items) >= limit:
                    break

                # Stop if page produced only duplicates.
                if added == 0:
                    break
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

    return jsonify({"ok": True, "count": len(items), "items": items, "state": state, "page": page})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8090, debug=True)
