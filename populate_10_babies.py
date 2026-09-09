import sqlite3
import datetime
import random
from database import register_baby, init_db

init_db()

mothers = [
    ("M-041", "Indu", "Rampur"),
    ("M-042", "Kavya", "Sitapur"),
    ("M-043", "Radha", "Rampur"),
    ("M-044", "Lakshmi", "Vasant Kunj"),
    ("M-045", "Priya", "Sitapur"),
    ("M-046", "Meera", "Rampur"),
    ("M-047", "Anjali", "Vasant Kunj"),
    ("M-048", "Sunita", "Sitapur"),
    ("M-049", "Anita", "Rampur"),
    ("M-050", "Puja", "Vasant Kunj")
]

conn = sqlite3.connect("maatrisuraksha.db")
c = conn.cursor()

print("Registering 10 custom baby-mother profiles...")

now = datetime.datetime.now()

for mid, name, village in mothers:
    # Check if mother exists, if not insert
    c.execute("SELECT unique_id FROM users WHERE unique_id=?", (mid,))
    if not c.fetchone():
        c.execute("""
        INSERT INTO users (unique_id, name, role, phone, village, latitude, longitude)
        VALUES (?, ?, 'Mother', '9876543210', ?, 0.0, 0.0)
        """, (mid, name, village))
        conn.commit()
    
    # Generate a random age in days between 10 and 320 for the baby
    age_days = random.randint(10, 320)
    delivery_date = (now - datetime.timedelta(days=age_days)).strftime("%Y-%m-%d")
    gender = random.choice(["Male", "Female"])
    
    success = register_baby(mid, delivery_date, gender)
    if success:
        print(f"Registered baby for Mother {mid} ({name}): Age {age_days} days, Gender {gender}")
    else:
        print(f"Baby already exists for Mother {mid} ({name})")

conn.close()
print("Done!")
