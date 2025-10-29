#!/usr/bin/env python3
"""
Settings Migration Script
Creates settings table and inserts defaults if missing
Idempotent - safe to run multiple times
"""
import os
import sys
import sqlite3
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

def run_migration():
    """Run the settings migration"""
    print("🔄 Running settings migration...")
    
    # Determine database path
    db_path = os.environ.get("RDWC_DB", 
                           os.path.join(os.path.dirname(__file__), "..", "data", "rdwc.db"))
    db_path = Path(db_path).resolve()
    
    print(f"📁 Database: {db_path}")
    
    # Ensure data directory exists
    db_path.parent.mkdir(exist_ok=True)
    
    try:
        with sqlite3.connect(str(db_path)) as conn:
            cursor = conn.cursor()
            
            print("📋 Creating settings table...")
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
            """)
            
            print("⚙️  Inserting default settings...")
            defaults = {
                'system_volume_liters': '25.0',
                'lights_on_time': '06:00', 
                'lights_duration_hours': '16'
            }
            
            for key, default_value in defaults.items():
                cursor.execute("""
                    INSERT OR IGNORE INTO settings (key, value) 
                    VALUES (?, ?)
                """, (key, default_value))
                print(f"   • {key}: {default_value}")
            
            conn.commit()
            
            print("✅ Settings migration completed successfully")
            
            # Verify settings
            print("\n📊 Current settings:")
            cursor.execute("SELECT key, value FROM settings ORDER BY key")
            for key, value in cursor.fetchall():
                print(f"   • {key}: {value}")
            
            return True
            
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return False


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)