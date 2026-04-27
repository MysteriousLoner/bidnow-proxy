#!/usr/bin/env python3
"""
System integration test script.
Verifies database, authentication, and API endpoints.
"""

import json
import os
import sys
import sqlite3
from pathlib import Path

def test_imports():
    """Test all modules can be imported."""
    print("Testing imports...")
    try:
        import db
        import auth
        import scraper
        print("  ✓ All modules import successfully")
        return True
    except ImportError as e:
        print(f"  ✗ Import failed: {e}")
        return False


def test_database():
    """Test database initialization and operations."""
    print("\nTesting database...")
    
    try:
        import db
        
        # Initialize
        db.init_db()
        print("  ✓ Database initialized")
        
        # Check tables exist
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = {row[0] for row in cursor.fetchall()}
        
        expected = {"properties", "custom_images"}
        if expected.issubset(tables):
            print(f"  ✓ Tables exist: {tables}")
        else:
            print(f"  ✗ Missing tables. Found: {tables}, Expected: {expected}")
            return False
        
        # Test property operations
        test_props = [
            {
                "url": "https://example.com/prop1",
                "location": "Test Location 1",
                "price": "RM 100,000",
                "auction_date": "2024-03-25 (10:00 AM)",
                "property_type": "House"
            }
        ]
        
        result = db.upsert_properties(test_props)
        print(f"  ✓ Property insert: {result}")
        
        # Test retrieval
        props = db.get_all_properties()
        if len(props) > 0:
            print(f"  ✓ Retrieved {len(props)} properties")
        else:
            print("  ✗ No properties retrieved")
            return False
        
        # Cleanup test property
        db.upsert_properties([])
        
        return True
        
    except Exception as e:
        print(f"  ✗ Database test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_authentication():
    """Test authentication system."""
    print("\nTesting authentication...")
    
    try:
        import auth
        
        # Test login success
        success, result = auth.verify_login("admin", "admin123")
        if success:
            token = result
            print(f"  ✓ Login successful, token created")
        else:
            print(f"  ✗ Login failed: {result}")
            return False
        
        # Test session verification
        if auth.verify_session(token):
            print(f"  ✓ Session verified")
        else:
            print(f"  ✗ Session verification failed")
            return False
        
        # Test invalid login
        success, result = auth.verify_login("admin", "wrong_password")
        if not success:
            print(f"  ✓ Invalid password rejected")
        else:
            print(f"  ✗ Invalid password accepted")
            return False
        
        # Test logout
        auth.logout(token)
        if not auth.verify_session(token):
            print(f"  ✓ Logout successful")
        else:
            print(f"  ✗ Session not invalidated after logout")
            return False
        
        return True
        
    except Exception as e:
        print(f"  ✗ Authentication test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_scraper():
    """Test scraper module functions."""
    print("\nTesting scraper...")
    
    try:
        import scraper
        
        # Test JSON extraction
        test_html = """
        <script>
        var aps = {"data": [{"property": {"title": "Test"}, "id": 123, "reserved_price": 100000}]};
        </script>
        """
        
        payload = scraper.extract_json_object_after_marker(test_html, "var aps =")
        if payload and "data" in payload:
            print(f"  ✓ JSON extraction works")
        else:
            print(f"  ✗ JSON extraction failed")
            return False
        
        # Test utility functions
        result = scraper.format_reserved_price(100000)
        if "100,000" in result:
            print(f"  ✓ Price formatting works")
        else:
            print(f"  ✗ Price formatting failed")
            return False
        
        return True
        
    except Exception as e:
        print(f"  ✗ Scraper test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_flask_app():
    """Test Flask app initialization."""
    print("\nTesting Flask app...")
    
    try:
        import app as flask_app
        
        # Check blueprints registered
        if hasattr(flask_app.app, "blueprints"):
            blueprints = set(flask_app.app.blueprints.keys())
            expected = {"api", "admin"}
            if expected.issubset(blueprints):
                print(f"  ✓ Blueprints registered: {blueprints}")
            else:
                print(f"  ✗ Missing blueprints. Found: {blueprints}, Expected: {expected}")
                return False
        
        # Check app config
        if flask_app.app.config:
            print(f"  ✓ App configured")
        else:
            print(f"  ✗ App config empty")
            return False
        
        return True
        
    except Exception as e:
        print(f"  ✗ Flask app test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_file_structure():
    """Test required files exist."""
    print("\nTesting file structure...")
    
    required_files = [
        "app.py",
        "db.py",
        "auth.py",
        "scraper.py",
        "admin.html",
        "requirements.txt",
        "README.md",
        "QUICKSTART.md"
    ]
    
    missing = []
    for filename in required_files:
        if not Path(filename).exists():
            missing.append(filename)
    
    if not missing:
        print(f"  ✓ All required files present")
        return True
    else:
        print(f"  ✗ Missing files: {missing}")
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("BidNow Property System - Integration Tests")
    print("=" * 60)
    
    tests = [
        test_file_structure,
        test_imports,
        test_database,
        test_authentication,
        test_scraper,
        test_flask_app,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append((test.__name__, result))
        except Exception as e:
            print(f"  ✗ Test crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((test.__name__, False))
    
    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All tests passed! System is ready to use.")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Check output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
