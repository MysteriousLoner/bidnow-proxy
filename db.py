"""
Database module for property management.
Handles schema, CRUD operations, and property synchronization.
"""

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any

DATABASE_FILE = "properties.db"


def init_db() -> None:
    """Initialize database schema."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Properties table: stores scraped BidNow property data
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS properties (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT UNIQUE NOT NULL,
                location TEXT NOT NULL,
                price TEXT NOT NULL,
                auction_date TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        
        # Custom images table: stores user-uploaded photos for properties
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS custom_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                property_url TEXT UNIQUE NOT NULL,
                image_filename TEXT NOT NULL,
                uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(property_url) REFERENCES properties(url)
            )
            """
        )
        
        # Create indices for faster queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_properties_url ON properties(url)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_custom_images_url ON custom_images(property_url)")
        
        conn.commit()


@contextmanager
def get_connection():
    """Context manager for database connections."""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def upsert_properties(items: list[dict[str, str]]) -> dict[str, int]:
    """
    Insert or update properties. Returns counts of inserted and updated.
    
    Args:
        items: List of property dicts with keys: url, location, price, auction_date
        
    Returns:
        Dict with 'inserted', 'updated', 'deleted' counts
    """
    with get_connection() as conn:
        cursor = conn.cursor()
        
        inserted = 0
        updated = 0
        
        # Track URLs being synced
        new_urls = {item.get("url") for item in items if item.get("url")}
        
        # Update or insert each property
        for item in items:
            url = item.get("url", "")
            if not url:
                continue
            
            cursor.execute(
                "SELECT id FROM properties WHERE url = ?",
                (url,)
            )
            existing = cursor.fetchone()
            
            if existing:
                cursor.execute(
                    """
                    UPDATE properties 
                    SET location = ?, price = ?, auction_date = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE url = ?
                    """,
                    (item.get("location"), item.get("price"), item.get("auction_date"), url)
                )
                updated += 1
            else:
                cursor.execute(
                    """
                    INSERT INTO properties (url, location, price, auction_date)
                    VALUES (?, ?, ?, ?)
                    """,
                    (url, item.get("location"), item.get("price"), item.get("auction_date"))
                )
                inserted += 1
        
        # Delete properties that are no longer in the sync
        cursor.execute("SELECT url FROM properties")
        existing_urls = {row[0] for row in cursor.fetchall()}
        deleted_urls = existing_urls - new_urls
        deleted = 0
        
        for url in deleted_urls:
            # Also delete custom image if it exists
            cursor.execute("DELETE FROM custom_images WHERE property_url = ?", (url,))
            cursor.execute("DELETE FROM properties WHERE url = ?", (url,))
            deleted += 1
        
        conn.commit()
        return {"inserted": inserted, "updated": updated, "deleted": deleted}


def get_all_properties() -> list[dict[str, Any]]:
    """Fetch all properties with their custom image info."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT p.*, COALESCE(c.image_filename, '') as custom_image
            FROM properties p
            LEFT JOIN custom_images c ON p.url = c.property_url
            ORDER BY p.updated_at DESC
            """
        )
        return [dict(row) for row in cursor.fetchall()]


def get_property_by_url(url: str) -> dict[str, Any] | None:
    """Fetch a single property by URL."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT p.*, COALESCE(c.image_filename, '') as custom_image
            FROM properties p
            LEFT JOIN custom_images c ON p.url = c.property_url
            WHERE p.url = ?
            """,
            (url,)
        )
        row = cursor.fetchone()
        return dict(row) if row else None


def save_custom_image(property_url: str, image_filename: str) -> None:
    """Save or update custom image for a property."""
    with get_connection() as conn:
        cursor = conn.cursor()
        
        # Check if property exists
        cursor.execute("SELECT id FROM properties WHERE url = ?", (property_url,))
        if not cursor.fetchone():
            raise ValueError(f"Property URL {property_url} not found")
        
        # Upsert custom image
        cursor.execute(
            "SELECT id FROM custom_images WHERE property_url = ?",
            (property_url,)
        )
        
        if cursor.fetchone():
            cursor.execute(
                "UPDATE custom_images SET image_filename = ?, uploaded_at = CURRENT_TIMESTAMP WHERE property_url = ?",
                (image_filename, property_url)
            )
        else:
            cursor.execute(
                "INSERT INTO custom_images (property_url, image_filename) VALUES (?, ?)",
                (property_url, image_filename)
            )
        
        conn.commit()


def get_custom_image_filename(property_url: str) -> str | None:
    """Get custom image filename for property, or None if not set."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT image_filename FROM custom_images WHERE property_url = ?",
            (property_url,)
        )
        row = cursor.fetchone()
        return row[0] if row else None


def delete_custom_image(property_url: str) -> None:
    """Delete custom image for a property."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM custom_images WHERE property_url = ?", (property_url,))
        conn.commit()


def get_property_count() -> int:
    """Get total number of properties."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM properties")
        return cursor.fetchone()[0]
