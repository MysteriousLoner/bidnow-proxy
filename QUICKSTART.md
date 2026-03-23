# Quick Start Guide

## 5-Minute Setup

### 1. Start the Server
```bash
cd "/Users/yanglee/Documents/code stuff/property-emily"
python3 app.py
```

Output should show:
```
[Background] Started 24-hour refresh worker
 * Running on http://0.0.0.0:8090
```

### 2. Initialize Database
First time setup - the database will auto-initialize. To manually init:
```bash
python3 -c "import db; db.init_db()"
```

### 3. Access Admin Panel
Open in browser: **`http://localhost:8090/api/admin`**

### 4. Login
- **Username**: `admin`
- **Password**: `admin123`

⚠️ Change password immediately! Edit `admin_config.json` or run:
```python
python3 -c "import auth; auth.set_admin_password('YOUR_NEW_PASSWORD')"
```

### 5. Test API
```bash
# Fetch properties
curl "http://localhost:8090/api/bidnow-properties?state=Kuala%20Lumpur"

# Force refresh
curl "http://localhost:8090/api/bidnow-properties?refresh=true"

# Check health
curl "http://localhost:8090/api/health"
```

## File Structure

```
property-emily/
├── app.py                    # Main Flask app (API + routes)
├── db.py                     # Database operations
├── auth.py                   # Authentication & login
├── scraper.py               # BidNow web scraping
├── admin.html               # Admin panel UI
├── properties.db            # SQLite database (created on first run)
├── admin_config.json        # Admin credentials (created on first run)
├── sessions.json            # Active session tokens
├── custom_images/           # Uploaded property photos
├── requirements.txt         # Python dependencies
├── README.md               # Full documentation
└── widget.html             # Optional: Embeddable widget
```

## How It Works

### 1. **Property Fetch Flow**
```
API Request
  ↓
Check Cache
  ↓
If expired → Fetch from BidNow
  ↓
Save to Database
  ↓
Cache results
  ↓
Return to client
```

### 2. **Background Refresh**
Every 24 hours:
- Fetches all properties from BidNow
- Compares with database
- Adds new properties
- Updates existing ones
- Removes properties no longer on BidNow
- Preserves custom images

### 3. **Photo Upload**
```
Select property
  ↓
Choose image file
  ↓
Upload to server
  ↓
Save with secure filename
  ↓
Store reference in database
  ↓
Cache invalidated (forces refresh)
```

## Key Endpoints

### Public API
| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health` | GET | Check if API is running |
| `/api/bidnow-properties` | GET | Fetch properties (with caching) |
| `/api/bidnow-properties?state=X` | GET | Filter by state |
| `/api/bidnow-properties?refresh=true` | GET | Force fresh fetch |
| `/api/asset/property-placeholder.svg` | GET | Default image |
| `/api/asset/custom/{filename}` | GET | Custom uploaded image |
| `/api/admin` | GET | Admin panel (HTML) |

### Admin API
| Endpoint | Method | Auth | Purpose |
|----------|--------|------|---------|
| `/admin/login` | POST | None | Get session token |
| `/admin/logout` | POST | Session | Logout |
| `/admin/properties` | GET | Session | List all properties |
| `/admin/upload-photo` | POST | Session | Upload image |
| `/admin/custom-image/{id}` | DELETE | Session | Delete image |

## Authentication

### Login Request
```bash
curl -X POST http://localhost:8090/admin/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'
```

Response:
```json
{
  "ok": true,
  "session_token": "abc123..."
}
```

### Login in Code
```python
import requests

response = requests.post("http://localhost:8090/admin/login", json={
    "username": "admin",
    "password": "admin123"
})
token = response.json()["session_token"]
```

### Using Session Token

**As query parameter**:
```bash
curl "http://localhost:8090/admin/properties?session=TOKEN"
```

**As Authorization header**:
```bash
curl -H "Authorization: Bearer TOKEN" \
  http://localhost:8090/admin/properties
```

## Database

### Check Properties
```bash
sqlite3 properties.db "SELECT COUNT(*) FROM properties;"
```

### View Custom Images
```bash
sqlite3 properties.db "SELECT property_url, image_filename FROM custom_images;"
```

### Reset Database
```bash
rm properties.db
python3 -c "import db; db.init_db()"
```

## Troubleshooting

### Properties not loading?
```bash
# Check BidNow is accessible
curl https://www.bidnow.my/properties/auction

# Force refresh
curl "http://localhost:8090/api/bidnow-properties?refresh=true"

# Check database
sqlite3 properties.db "SELECT COUNT(*) FROM properties;"
```

### Login failing?
```bash
# Reset admin credentials
rm admin_config.json sessions.json
python3 app.py

# Now use defaults: admin/admin123
```

### Photos not showing?
```bash
# Check files exist
ls custom_images/

# Check database references
sqlite3 properties.db "SELECT * FROM custom_images;"

# Reload admin panel (clear browser cache)
```

## Deploy to Production

For deployment behind Nginx reverse proxy (like you have):

1. **Update password** - CRITICAL!
```python
import auth
auth.set_admin_password("strong-random-password")
```

2. **Restart container/service**
```bash
systemctl restart property-emily
# or
docker restart property-emily
```

3. **Enable Nginx routing**
Add to Nginx config:
```nginx
location /api {
    proxy_pass http://127.0.0.1:8090;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
}

location /admin {
    proxy_pass http://127.0.0.1:8090;
    proxy_set_header Host $host;
}

location /custom_images {
    proxy_pass http://127.0.0.1:8090;
    proxy_cache_valid 200 24h;
}
```

4. **Test from browser**
```
https://your-domain.com/api/admin
https://your-domain.com/api/bidnow-properties
```

## Next Steps

1. ✅ Start server: `python3 app.py`
2. ✅ Open `http://localhost:8090/api/admin`
3. ✅ Login with `admin/admin123`
4. ✅ Change password immediately
5. ✅ Upload custom photos for properties
6. ✅ Test API endpoints
7. ✅ Integrate into production (Nginx)

## Architecture Overview

```
┌─────────────────┐
│   Admin Panel   │  (admin.html)
│  (HTML+JS)      │
└────────┬────────┘
         │
         ▼
┌─────────────────────┐
│   Flask Backend     │  (app.py)
│  ├─ /api routes    │
│  ├─ /admin routes  │
│  └─ Auth system    │
└────────┬────────────┘
         │
    ┌────┴────┐
    ▼         ▼
┌────────┐ ┌──────────┐
│  SQLite│ │  BidNow  │
│  DB    │ │ Scraper  │
└────────┘ └──────────┘
    │
    ▼
┌─────────────────┐
│  custom_images/ │
│  (uploaded      │
│   photos)       │
└─────────────────┘
```

## Code Organization Summary

| File | Lines | Purpose |
|------|-------|---------|
| app.py | ~450 | Flask app, API routes, background worker |
| db.py | ~200 | SQLite database layer, CRUD ops |
| auth.py | ~120 | Login system, sessions, password hashing |
| scraper.py | ~180 | BidNow parsing, JSON extraction |
| admin.html | ~600 | Web UI for admin panel |

**Total**: ~1550 lines of modular, maintainable code

## Need Help?

Check logs:
```bash
# If running in foreground
tail -f app.log

# If running in background
journalctl -u property-emily -f
```

Review database:
```bash
sqlite3 properties.db ".tables"
sqlite3 properties.db ".schema"
```

Test endpoints:
```bash
curl -v "http://localhost:8090/api/health"
```
