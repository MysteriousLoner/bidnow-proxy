"""
Authentication module for admin access.
Handles password verification and session management.
"""

import secrets
import hashlib
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()
ADMIN_CONFIG_FILE = "admin_config.json"
SESSIONS_FILE = "sessions.json"
SESSION_DURATION_HOURS = 24


def _hash_password(password: str) -> str:
    """Hash password using SHA-256."""
    return hashlib.sha256(password.encode()).hexdigest()


def _load_admin_config() -> dict:
    """Load admin configuration from environment variables."""
    username = os.getenv("ADMIN_USERNAME", "admin")
    password = os.getenv("ADMIN_PASSWORD", "admin123")
    
    return {
        "username": username,
        "password_hash": _hash_password(password)
    }


def _save_admin_config(config: dict) -> None:
    """Admin config is now read-only from environment variables."""
    pass


def _load_sessions() -> dict:
    """Load active sessions."""
    if not os.path.exists(SESSIONS_FILE):
        return {}
    
    with open(SESSIONS_FILE, "r") as f:
        return json.load(f)


def _save_sessions(sessions: dict) -> None:
    """Save active sessions."""
    with open(SESSIONS_FILE, "w") as f:
        json.dump(sessions, f, indent=2)


def verify_login(username: str, password: str) -> tuple[bool, str]:
    """
    Verify login credentials.
    
    Returns:
        Tuple of (success: bool, session_token: str or error_message: str)
    """
    config = _load_admin_config()
    password_hash = _hash_password(password)
    
    if username != config["username"] or password_hash != config["password_hash"]:
        return False, "Invalid username or password"
    
    # Create session token
    token = secrets.token_urlsafe(32)
    sessions = _load_sessions()
    sessions[token] = {
        "username": username,
        "created_at": datetime.now().isoformat(),
        "expires_at": (datetime.now() + timedelta(hours=SESSION_DURATION_HOURS)).isoformat()
    }
    _save_sessions(sessions)
    
    return True, token


def verify_session(token: str) -> bool:
    """Check if session token is valid."""
    sessions = _load_sessions()
    
    if token not in sessions:
        return False
    
    session = sessions[token]
    expires_at = datetime.fromisoformat(session["expires_at"])
    
    if datetime.now() > expires_at:
        # Session expired, remove it
        del sessions[token]
        _save_sessions(sessions)
        return False
    
    return True


def logout(token: str) -> None:
    """Invalidate a session token."""
    sessions = _load_sessions()
    sessions.pop(token, None)
    _save_sessions(sessions)


def set_admin_password(new_password: str) -> None:
    """Update admin password."""
    config = _load_admin_config()
    config["password_hash"] = _hash_password(new_password)
    _save_admin_config(config)
