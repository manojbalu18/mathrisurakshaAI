import sqlite3
import datetime
from database import register_baby, init_db

init_db()

conn = sqlite3.connect("maatrisuraksha.db")
c = conn.cursor()

# Get the first mother in the DB to attach to
c.execute("SELECT unique_id FROM users WHERE role='Mother' LIMIT 1")
row = c.fetchone()

if row:
    mother_id = row[0]
    # Set a delivery date 3 months ago (approx 90 days)
    delivery_date = (datetime.datetime.now() - datetime.timedelta(days=90)).strftime("%Y-%m-%d")
    
    success = register_baby(mother_id, delivery_date, "Female")
    if success:
        print(f"Successfully registered a 3-month-old baby for Mother {mother_id}")
    else:
        print(f"Baby already registered for Mother {mother_id}")
else:
    print("No mothers found in the database. Please run populate_mothers.py first.")
    
conn.close()
