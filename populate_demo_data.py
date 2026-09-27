"""
Populate database with:
- 110 mothers (IDs 001-110, name = same as ID for password)
- 5 random baby profiles from those mothers
"""
import sqlite3
import datetime
import random

conn = sqlite3.connect("maatrisuraksha.db")
c = conn.cursor()

# Villages to distribute mothers across
villages = [
    "Anantapur", "Bellary", "Chitradurga", "Davangere", "Eluru",
    "Guntur", "Hubli", "Kurnool", "Mangalore", "Nellore",
    "Raichur", "Shimoga", "Tirupati", "Udupi", "Vijayapura"
]

# Register 110 mothers with ID as both unique_id and name (password)
print("Registering 110 mothers...")
for i in range(1, 111):
    uid = f"{i:03d}"  # 001, 002, ..., 110
    name = uid  # Name = same as ID (used as password for login)
    phone = f"90000{i:05d}"
    village = villages[i % len(villages)]
    
    try:
        c.execute("""
        INSERT INTO users (unique_id, name, role, phone, village)
        VALUES (?, ?, 'Mother', ?, ?)
        """, (uid, name, phone, village))
    except sqlite3.IntegrityError:
        pass  # Already exists

conn.commit()
print(f"  -> 110 mothers registered (IDs: 001 to 110)")
print(f"  -> Login: ID = 001, Name/Password = 001")

# Pick 5 random mother IDs for baby profiles
random.seed(42)
baby_mother_ids = random.sample(range(1, 111), 5)
baby_mother_ids_formatted = [f"{mid:03d}" for mid in baby_mother_ids]

print(f"\nCreating baby profiles for mothers: {baby_mother_ids_formatted}")

for mid in baby_mother_ids_formatted:
    # Random delivery date in last 1-6 months
    days_ago = random.randint(30, 180)
    delivery_date = (datetime.datetime.now() - datetime.timedelta(days=days_ago)).strftime("%Y-%m-%d")
    gender = random.choice(["Male", "Female"])
    created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    try:
        c.execute("""
        INSERT INTO baby_profiles (mother_id, delivery_date, baby_gender, created_at)
        VALUES (?, ?, ?, ?)
        """, (mid, delivery_date, gender, created_at))
        
        # Auto-populate vaccination schedule
        vaccines = [
            ("BCG, OPV", 0),
            ("DPT, Hepatitis B", 42),
            ("DPT", 70),
            ("DPT", 98),
            ("Measles", 270)
        ]
        
        delivery_dt = datetime.datetime.strptime(delivery_date, "%Y-%m-%d")
        for v_name, days_after in vaccines:
            due_dt = delivery_dt + datetime.timedelta(days=days_after)
            c.execute("""
            INSERT INTO vaccinations (mother_id, vaccine_name, due_date, status)
            VALUES (?, ?, ?, ?)
            """, (mid, v_name, due_dt.strftime("%Y-%m-%d"), 'Pending'))
        
        print(f"  -> Baby profile for Mother {mid}: Gender={gender}, Born={delivery_date}")
    except sqlite3.IntegrityError:
        print(f"  -> Baby profile for Mother {mid} already exists, skipping.")

conn.commit()
conn.close()

print("\n✅ Database populated successfully!")
print("\n--- LOGIN CREDENTIALS ---")
print("Mother Login: ID = 001 to 110, Name = same as ID (e.g., ID: 001, Name: 001)")
print("ASHA Worker Login: Phone = 7075287040, Password/OTP = 111")
print(f"Baby Care Login: Mother IDs = {baby_mother_ids_formatted}")
