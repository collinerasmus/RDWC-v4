#!/usr/bin/env python3
"""
RDWC CSV Backup Cleanup
Removes CSV files older than 30 days from backup directory
"""

import os
import time
import glob

BACKUP_DIR = "/home/pi/backups"
MAX_AGE_DAYS = 30
MAX_AGE_SECONDS = MAX_AGE_DAYS * 24 * 3600

def cleanup_old_csvs():
    """Remove CSV files older than MAX_AGE_DAYS"""
    if not os.path.exists(BACKUP_DIR):
        print(f"Backup directory {BACKUP_DIR} does not exist")
        return 0
    
    csv_pattern = os.path.join(BACKUP_DIR, "*.csv")
    csv_files = glob.glob(csv_pattern)
    
    if not csv_files:
        print("No CSV files found to clean up")
        return 0
    
    current_time = time.time()
    removed_count = 0
    kept_count = 0
    
    for csv_file in csv_files:
        try:
            file_age = current_time - os.path.getmtime(csv_file)
            
            if file_age > MAX_AGE_SECONDS:
                os.remove(csv_file)
                removed_count += 1
                days_old = int(file_age / (24 * 3600))
                print(f"Removed: {os.path.basename(csv_file)} ({days_old} days old)")
            else:
                kept_count += 1
        except OSError as e:
            print(f"Error processing {csv_file}: {e}")
    
    print(f"Cleanup complete: {removed_count} removed, {kept_count} kept")
    return 0

def main():
    """Main function"""
    print(f"Cleaning up CSV files older than {MAX_AGE_DAYS} days from {BACKUP_DIR}")
    return cleanup_old_csvs()

if __name__ == "__main__":
    import sys
    sys.exit(main())