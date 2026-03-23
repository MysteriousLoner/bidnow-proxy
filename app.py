"""
BidNow Property Management System
Backend API for property scraping, caching, custom photo uploads, and admin management.

Structure:
- api.py routes: Property data and filtering endpoints
- admin.py routes: Admin authentication and photo upload management
- Database: SQLite with property and custom image tracking
- Background worker: Automatic 24-hour refresh of all property listings
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

import threading
import time
from typing import Any

import requests
from flask import Flask, jsonify, request, Blueprint
from flask_cors import CORS

import db
import auth
import scraper

# Configuration
CACHE_TTL_SECONDS = 24 * 60 * 60
BACKGROUND_RECRAWL_SECONDS = 24 * 60 * 60
ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
MAX_IMAGE_SIZE_MB = 5

# Global state
_CACHE_LOCK = threading.Lock()
_LISTING_CACHE: dict[str, dict[str, Any]] = {}
_BACKGROUND_WORKER_STARTED = False

# Create Flask app
app = Flask(__name__)
CORS(app)

# Initialize database
db.init_db()

# Create blueprints
api_bp = Blueprint("api", __name__, url_prefix="/api")
admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# ===== Helper Functions =====

def _cache_key(state: str | None) -> str:
    """Generate cache key from state."""
    return (state or "ALL").strip().lower() or "ALL"


def _get_cached_items(state: str | None) -> tuple[list[dict[str, Any]] | None, bool]:
    """Get cached properties if valid."""
    key = _cache_key(state)
    now = time.time()
    with _CACHE_LOCK:
        entry = _LISTING_CACHE.get(key)
        if not entry:
            return None, False
        if now - float(entry.get("timestamp", 0.0)) > CACHE_TTL_SECONDS:
            _LISTING_CACHE.pop(key, None)
            return None, False
        return entry.get("items"), True


def _set_cached_items(state: str | None, items: list[dict[str, Any]]) -> None:
    """Cache properties."""
    key = _cache_key(state)
    with _CACHE_LOCK:
        _LISTING_CACHE[key] = {
            "timestamp": time.time(),
            "items": items,
        }


def _with_image_urls(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Add image URLs to property items (custom or default)."""
    result = []
    default_placeholder = f"{request.url_root.rstrip('/')}/api/asset/property-placeholder.svg"
    
    for item in items:
        cloned = dict(item)
        property_url = cloned.get("url", "")
        
        # Check if property has custom image
        custom_image = db.get_custom_image_filename(property_url)
        
        if custom_image:
            cloned["image"] = f"{request.url_root.rstrip('/')}/api/asset/custom/{custom_image}"
        else:
            cloned["image"] = default_placeholder
        
        result.append(cloned)
    
    return result


def _is_valid_session(token: str) -> bool:
    """Check if admin session is valid."""
    return auth.verify_session(token) if token else False


def _get_session_from_request() -> str | None:
    """Extract session token from request."""
    # Try from Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    
    # Try from query parameter
    return request.args.get("session")


# ===== API Routes =====

@api_bp.get("/health")
def api_health() -> Any:
    return jsonify({"ok": True, "message": "Property API is healthy"})


@api_bp.get("/bidnow-properties")
def api_bidnow_properties() -> Any:
    """
    Get all properties (cached or fresh).
    
    Query params:
    - state: Filter by state (optional)
    - refresh: Force refresh from BidNow (optional)
    - limit: Limit number of results (optional)
    """
    state_arg = (request.args.get("state") or "").strip()
    state = state_arg or None
    refresh = (request.args.get("refresh") or "").strip().lower() in {"1", "true", "yes"}
    limit = request.args.get("limit", type=int)
    
    if limit is not None:
        limit = max(1, min(limit, 10000))
    
    try:
        # Try cache first
        cached_items = None
        cache_hit = False
        if not refresh:
            cached_items, cache_hit = _get_cached_items(state)
        
        if cached_items is None:
            # Fetch from BidNow and save to database
            fresh_items, total_pages = scraper.fetch_all_pages(state=state)
            sync_result = db.upsert_properties(fresh_items)
            
            # Fetch all from database (includes existing entries)
            all_items = db.get_all_properties()
            
            # Filter by state if specified
            if state:
                all_items = [item for item in all_items if state.lower() in item.get("location", "").lower()]
            
            _set_cached_items(state, all_items)
            cache_hit = False
            items = all_items
        else:
            items = cached_items
        
        if limit is not None:
            items = items[:limit]
        
        # Add image URLs
        items_with_images = _with_image_urls(items)
    
    except requests.RequestException as exc:
        return jsonify({
            "ok": False,
            "error": "Failed to fetch from BidNow",
            "details": str(exc),
        }), 502
    
    return jsonify({
        "ok": True,
        "count": len(items_with_images),
        "items": items_with_images,
        "state": state,
        "cached": cache_hit,
        "cache_ttl_seconds": CACHE_TTL_SECONDS,
        "total_in_db": db.get_property_count(),
    })


@api_bp.get("/asset/property-placeholder.svg")
def api_placeholder_svg() -> Any:
    """Serve default placeholder image."""
    from flask import Response
    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="800" height="450" viewBox="0 0 800 450" role="img" aria-label="No photo available">
  <rect width="800" height="450" fill="#f1f1f1"/>
  <g fill="none" stroke="#9a9a9a" stroke-width="20" stroke-linecap="round" stroke-linejoin="round">
    <path d="M160 220 L400 70 L640 220"/>
    <path d="M220 205 V360 H580 V205"/>
    <rect x="305" y="245" width="95" height="75"/>
    <rect x="450" y="235" width="85" height="125"/>
    <path d="M230 170 V95"/>
  </g>
  <rect x="170" y="380" width="460" height="8" fill="#a6a6a6"/>
  <text x="400" y="420" text-anchor="middle" font-family="Arial, Helvetica, sans-serif" font-size="44" font-weight="700" fill="#7f7f7f">NO PHOTO AVAILABLE</text>
</svg>"""
    
    return Response(svg, mimetype="image/svg+xml")


@api_bp.get("/asset/custom/<filename>")
def api_custom_image(filename: str) -> Any:
    """Serve custom uploaded property image."""
    from flask import send_from_directory
    
    # Security: prevent directory traversal
    if ".." in filename or "/" in filename:
        return jsonify({"error": "Invalid filename"}), 400
    
    try:
        return send_from_directory("custom_images", filename)
    except FileNotFoundError:
        return jsonify({"error": "Image not found"}), 404


# ===== Admin Routes =====

@admin_bp.get("/")
def serve_admin_panel() -> Any:
    """Serve admin panel HTML."""
    from flask import send_file
    try:
        admin_path = os.path.join(os.path.dirname(__file__), "admin.html")
        return send_file(admin_path)
    except FileNotFoundError:
        return jsonify({"error": "Admin panel not found"}), 404


@admin_bp.post("/login")
def admin_login() -> Any:
    """
    Admin login endpoint.
    
    JSON body: {"username": "...", "password": "..."}
    Returns: {"ok": true, "session_token": "..."}
    """
    data = request.get_json() or {}
    username = data.get("username", "")
    password = data.get("password", "")
    
    if not username or not password:
        return jsonify({"ok": False, "error": "Username and password required"}), 400
    
    success, result = auth.verify_login(username, password)
    if not success:
        return jsonify({"ok": False, "error": result}), 401
    
    return jsonify({"ok": True, "session_token": result}), 200


@admin_bp.post("/logout")
def admin_logout() -> Any:
    """Logout and invalidate session token."""
    token = _get_session_from_request()
    if token:
        auth.logout(token)
    
    return jsonify({"ok": True})


@admin_bp.post("/upload-photo")
def admin_upload_photo() -> Any:
    """
    Upload custom photo for a property.
    
    Form data:
    - session: Admin session token
    - property_url: URL of the property
    - photo: Image file
    """
    token = _get_session_from_request()
    if not _is_valid_session(token):
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    
    property_url = request.form.get("property_url", "").strip()
    if not property_url:
        return jsonify({"ok": False, "error": "property_url required"}), 400
    
    # Check property exists in database
    property_data = db.get_property_by_url(property_url)
    if not property_data:
        return jsonify({"ok": False, "error": "Property not found"}), 404
    
    # Validate file upload
    if "photo" not in request.files:
        return jsonify({"ok": False, "error": "No photo provided"}), 400
    
    file = request.files["photo"]
    if file.filename == "":
        return jsonify({"ok": False, "error": "No file selected"}), 400
    
    # Validate file extension
    filename_lower = file.filename.lower()
    ext = filename_lower.rsplit(".", 1)[-1] if "." in filename_lower else ""
    if ext not in ALLOWED_IMAGE_EXTENSIONS:
        return jsonify({
            "ok": False,
            "error": f"Invalid image format. Allowed: {', '.join(ALLOWED_IMAGE_EXTENSIONS)}"
        }), 400
    
    # Validate file size
    file.seek(0, 2)  # Seek to end
    file_size_mb = file.tell() / (1024 * 1024)
    file.seek(0)  # Reset
    
    if file_size_mb > MAX_IMAGE_SIZE_MB:
        return jsonify({
            "ok": False,
            "error": f"File too large. Maximum {MAX_IMAGE_SIZE_MB}MB"
        }), 400
    
    # Create custom_images directory if needed
    os.makedirs("custom_images", exist_ok=True)
    
    # Generate safe filename (use property URL hash)
    import hashlib
    url_hash = hashlib.md5(property_url.encode()).hexdigest()
    safe_filename = f"{url_hash}.{ext}"
    
    filepath = os.path.join("custom_images", safe_filename)
    file.save(filepath)
    
    # Save to database
    db.save_custom_image(property_url, safe_filename)
    
    # Invalidate cache to reflect new images
    with _CACHE_LOCK:
        _LISTING_CACHE.clear()
    
    return jsonify({
        "ok": True,
        "message": "Photo uploaded successfully",
        "filename": safe_filename
    }), 200


@admin_bp.get("/properties")
def admin_get_properties() -> Any:
    """
    Admin panel: get all properties with custom image info.
    Requires valid session.
    """
    token = _get_session_from_request()
    if not _is_valid_session(token):
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    
    properties = db.get_all_properties()
    return jsonify({
        "ok": True,
        "count": len(properties),
        "properties": properties
    })


@admin_bp.delete("/custom-image/<property_id>")
def admin_delete_custom_image(property_id: str) -> Any:
    """Delete custom image for a property."""
    token = _get_session_from_request()
    if not _is_valid_session(token):
        return jsonify({"ok": False, "error": "Unauthorized"}), 401
    
    # Note: property_id is the property URL (passed as base64 or similar in real implementation)
    # For now, we'll just support URL-based deletion
    property_url = request.args.get("url", "")
    
    if not property_url:
        return jsonify({"ok": False, "error": "property URL required"}), 400
    
    try:
        db.delete_custom_image(property_url)
        
        # Invalidate cache
        with _CACHE_LOCK:
            _LISTING_CACHE.clear()
        
        return jsonify({"ok": True, "message": "Custom image deleted"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ===== Background Worker =====

def _initial_sync() -> None:
    """Perform initial sync when application starts."""
    try:
        print("[Startup] Starting initial property sync...")
        items, _ = scraper.fetch_all_pages(state=None)
        sync_result = db.upsert_properties(items)
        
        # Cache the results
        all_items = db.get_all_properties()
        _set_cached_items(None, all_items)
        
        print(f"[Startup] Initial sync complete: "
              f"+{sync_result['inserted']} ~{sync_result['updated']} -{sync_result['deleted']}")
    except requests.RequestException as e:
        print(f"[Startup] Error during initial sync: {e}")


def _background_recrawl_worker() -> None:
    """Background worker that refreshes cache every 24 hours."""
    while True:
        time.sleep(BACKGROUND_RECRAWL_SECONDS)
        
        states_to_refresh = list(_LISTING_CACHE.keys())
        if not states_to_refresh:
            states_to_refresh = ["ALL"]
        
        for cache_key in states_to_refresh:
            state = None if cache_key == "ALL" else cache_key
            
            try:
                items, _ = scraper.fetch_all_pages(state=state)
                sync_result = db.upsert_properties(items)
                
                # Get all from database
                all_items = db.get_all_properties()
                if state:
                    all_items = [item for item in all_items if state.lower() in item.get("location", "").lower()]
                
                _set_cached_items(state, all_items)
                print(f"[Background] Refreshed {state or 'ALL'}: "
                      f"+{sync_result['inserted']} ~{sync_result['updated']} -{sync_result['deleted']}")
            except requests.RequestException as e:
                print(f"[Background] Error refreshing {state or 'ALL'}: {e}")
                continue


def _start_background_worker() -> None:
    """Start background worker thread and perform initial sync."""
    global _BACKGROUND_WORKER_STARTED
    if _BACKGROUND_WORKER_STARTED:
        return
    
    # Prevent duplicate workers under Flask debug reloader
    # Only run after reloader has initialized (or in production when debug is off)
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        return
    
    # Perform initial sync on startup
    _initial_sync()
    
    thread = threading.Thread(target=_background_recrawl_worker, daemon=True)
    thread.start()
    _BACKGROUND_WORKER_STARTED = True
    print("[Background] Started 24-hour refresh worker")


# Register blueprints
app.register_blueprint(api_bp)
app.register_blueprint(admin_bp)

# Start background worker at import time
_start_background_worker()


# ===== Entry Point =====

if __name__ == "__main__":
    _start_background_worker()
    # Disable debug mode in production/Docker, enable only for local development
    debug_mode = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=8090, debug=debug_mode)
