# BidNow Property Management System

A comprehensive property management system that scrapes BidNow Malaysia properties, stores them in a SQLite database, and provides a web interface for managing custom property photos.

## Architecture

### Project Structure

```
property-emily/
├── app.py              # Main Flask application with API routes
├── db.py              # Database models and CRUD operations
├── auth.py            # Authentication and session management
├── scraper.py         # BidNow property scraping logic
├── admin.html         # Admin panel for photo upload and management
├── properties.db      # SQLite database (auto-created)
├── admin_config.json  # Admin credentials (auto-created with defaults)
├── sessions.json      # Active session tokens
├── custom_images/     # Uploaded custom property photos
└── requirements.txt   # Python dependencies
```

### Module Responsibilities

**app.py** - Main Flask application
- API routes for property fetching
- Admin panel file serving
- Background worker for 24-hour refresh cycles
- Blueprint organization for API and Admin routes

**db.py** - Database layer
- SQLite schema initialization
- CRUD operations for properties
- Custom image tracking
- Property sync with automatic insertion/update/deletion

**auth.py** - Authentication system
- Password-based login
- Session token generation and validation
- Token expiration (24 hours)
- Admin credential management

**scraper.py** - Data extraction
- BidNow HTML parsing
- JSON object extraction from script tags
- Multi-page property aggregation
- URL deduplication

**admin.html** - Admin interface
- Password-protected login
- Property browsing and filtering
- Custom photo upload per property
- Photo deletion
- Statistics dashboard

## Features

### 1. Property Scraping
- Automatically fetches properties from BidNow Malaysia
- Extracts JSON data from HTML script tags
- Discovers and scrapes all pages automatically
- Deduplicates by property URL

### 2. Database Management
- SQLite backend for persistent storage
- Properties table with location, price, auction date
- Custom images table linking to properties
- Automatic sync with add/update/delete on each refresh

### 3. Photo Management
- Upload custom photos per property
- Fallback to default placeholder if no custom photo
- Secure file handling with size and format validation
- File hashing for safe storage

### 4. Admin Panel
- Password-protected web interface
- Property browse and search
- Drag-and-drop photo upload
- View custom vs default photos
- Delete custom photos
- Statistics on photo coverage

### 5. Background Refresh
- 24-hour automatic sync cycles
- Removes properties no longer on BidNow
- Adds new properties
- Updates existing properties
- Preserves custom images across refreshes

### 6. API Endpoints

**Public API**
- `GET /api/health` - Health check
- `GET /api/bidnow-properties?state=<STATE>` - Get properties (cached)
- `GET /api/asset/property-placeholder.svg` - Default placeholder
- `GET /api/asset/custom/<FILENAME>` - Custom uploaded image

**Admin API**
- `POST /admin/login` - Login with credentials
- `POST /admin/logout` - Logout
- `GET /admin/properties` - List all properties (session required)
- `POST /admin/upload-photo` - Upload photo for property
- `DELETE /admin/custom-image/<ID>` - Delete custom photo

## Installation & Setup

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Initialize Database
```bash
python3 app.py
```
Or directly:
```python
import db
db.init_db()
```

### 3. Change Default Admin Password
Edit `admin_config.json` after first run or use:
```python
import auth
auth.set_admin_password("your-new-password")
```

### 4. Run the Server
```bash
python3 app.py
```

Server runs on `http://localhost:8090`

### 5. Access Admin Panel
Visit `http://localhost:8090/api/admin`
- Default username: `admin`
- Default password: `admin123` (change immediately!)

## Usage Examples

### Fetch Properties via API
```bash
# Get all properties (Kuala Lumpur)
curl "http://localhost:8090/api/bidnow-properties?state=Kuala%20Lumpur"

# Force refresh from BidNow
curl "http://localhost:8090/api/bidnow-properties?refresh=true"

# Limit results
curl "http://localhost:8090/api/bidnow-properties?limit=10"
```

### Upload Custom Photo (Python)
```python
import requests

# Login first
response = requests.post("http://localhost:8090/admin/login", json={
    "username": "admin",
    "password": "admin123"
})
token = response.json()["session_token"]

# Upload photo
files = {"photo": open("photo.jpg", "rb")}
data = {
    "property_url": "https://www.bidnow.my/auction-property/...",
    "session": token
}
requests.post("http://localhost:8090/admin/upload-photo", 
              files=files, data=data)
```

## Database Schema

### Properties Table
```sql
CREATE TABLE properties (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    url TEXT UNIQUE NOT NULL,
    location TEXT NOT NULL,
    price TEXT NOT NULL,
    auction_date TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Custom Images Table
```sql
CREATE TABLE custom_images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    property_url TEXT UNIQUE NOT NULL,
    image_filename TEXT NOT NULL,
    uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(property_url) REFERENCES properties(url)
);
```

## Configuration

**Cache TTL**: 24 hours (86400 seconds)
- Automatically refreshes after this period
- Can be overridden with `?refresh=true` parameter

**Image Upload Limits**:
- Max file size: 5MB
- Allowed formats: jpg, jpeg, png, gif, webp

**Session Duration**: 24 hours
- Sessions expire and require re-login after this period

**Background Worker**:
- Runs every 24 hours
- Keeps track of sync updates (inserted/updated/deleted)

## Security Notes

⚠️ **IMPORTANT**: Change default admin credentials before deployment!

1. Change admin password:
```python
import auth
auth.set_admin_password("strong-new-password")
```

2. Use HTTPS in production
3. Session tokens are stored in JSON file (use secure backend in production)
4. File upload directory should allow read access only
5. Implement rate limiting before deployment to production

## Troubleshooting

**Properties not showing**:
1. Check if database has properties: `SELECT COUNT(*) FROM properties;`
2. Run refresh: `GET /api/bidnow-properties?refresh=true`
3. Check background worker output in logs

**Custom photos not displaying**:
1. Check if `custom_images` folder exists
2. Verify file permissions: `ls -la custom_images/`
3. Check database: `SELECT * FROM custom_images;`
4. Verify image file exists and is readable

**Login fails**:
1. Check `admin_config.json` exists
2. Reset credentials: Delete file and restart app
3. Verify `sessions.json` is writable

**BidNow API errors**:
1. Check internet connectivity
2. BidNow may have changed HTML structure - update scraper.py
3. Check logs for detailed error messages

## Performance Optimization

**In Production**:
1. Use gunicorn instead of Flask dev server: `gunicorn app:app`
2. Use PostgreSQL instead of SQLite for better concurrency
3. Implement Redis caching layer
4. Add image CDN for custom images
5. Use background job queue (Celery) instead of threads
6. Configure connection pooling
7. Add request rate limiting

**Database Optimization**:
1. Create indices on frequently queried columns (already done)
2. Archive old properties to separate table
3. Use pagination for large result sets
4. Schedule VACUUM during off-hours

## API Response Format

### Success Response
```json
{
  "ok": true,
  "count": 150,
  "items": [
    {
      "url": "https://www.bidnow.my/auction-property/...",
      "location": "Kuala Lumpur, Wilayah Persekutuan",
      "price": "Reserved Price RM 450,000.00",
      "auction_date": "2024-03-25 (10:00 AM)",
      "image": "http://localhost:8090/api/asset/custom/abc123.jpg"
    }
  ],
  "state": "Kuala Lumpur",
  "cached": true,
  "cache_ttl_seconds": 86400,
  "total_in_db": 2150
}
```

### Error Response
```json
{
  "ok": false,
  "error": "Failed to fetch from BidNow",
  "details": "Connection timeout"
}
```

## Development

### Running Tests
```bash
# Syntax check
python3 -m py_compile app.py db.py auth.py scraper.py

# Manual testing
python3 -c "import db; db.init_db(); print('Database initialized')"
```

### Adding New States
The system automatically discovers all available states from BidNow. Specify any state in the query:
```
GET /api/bidnow-properties?state=Selangor
GET /api/bidnow-properties?state=Johor
GET /api/bidnow-properties?state=Penang
```

## License

Internal use only. Property data scraped from BidNow Malaysia.

## Support

For issues or feature requests, check the logs or review the code structure above.
