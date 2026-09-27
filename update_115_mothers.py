import sqlite3
import random

def update_115_mothers():
    conn = sqlite3.connect('maatrisuraksha.db')
    c = conn.cursor()
    
    # 115 Simple, friendly, realistic names
    simple_names = [
        "Sath", "Pink", "Vika", "Amu", "Sonu", "Priya", "Rosh", "Nithu", "Chikky", "Cherry",
        "Laddu", "Hasini", "Divya", "Sneha", "Swathi", "Kavya", "Anu", "Rani", "Pooja", "Bhavani",
        "Deepa", "Geetha", "Jyothi", "Meena", "Radha", "Rupa", "Suma", "Tanvi", "Uma", "Vani",
        "Yamuna", "Asha", "Chitra", "Durga", "Esha", "Gauri", "Hema", "Indu", "Jaya", "Kiran",
        "Lata", "Mona", "Neha", "Pallavi", "Rekha", "Sarita", "Tara", "Usha", "Vidya", "Zoya",
        "Bhanu", "Chinnu", "Bujji", "Kanna", "Chitti", "Lucky", "Pinnu", "Sweety", "Sony", "Dolly",
        "Ritu", "Mahi", "Siya", "Rhea", "Dia", "Aditi", "Keerthi", "Navya", "Harini", "Sirisha",
        "Sravani", "Teju", "Madhu", "Roopa", "Shilpa", "Sandhya", "Archana", "Lavanya", "Sunitha", "Bindu",
        "Aparna", "Varsha", "Padma", "Sailaja", "Leela", "Sujatha", "Kalyani", "Manasa", "Sowmya", "Sindhu",
        "Preethi", "Deepthi", "Pranathi", "Sahithi", "Vaishnavi", "Ananya", "Akshara", "Ishita", "Rithika", "Pavani",
        "Vasantha", "Revathi", "Sharada", "Gayathri", "Sushma", "Prameela", "Pushpa", "Kusuma", "Sumathi", "Lalitha",
        "Amala", "Kanakam", "Syamala", "Nandini", "Vasundhara"
    ]

    villages = [
        ("Hyderabad (Old City)", 17.3616, 78.4747),
        ("Secunderabad", 17.4399, 78.4983),
        ("Gachibowli", 17.4401, 78.3489),
        ("Kukatpally", 17.4849, 78.4138),
        ("Medchal", 17.6294, 78.4814),
        ("Shamshabad", 17.2483, 78.4299),
        ("Ghatkesar", 17.4528, 78.6837),
        ("Warangal", 17.9784, 79.5941),
        ("Karimnagar", 18.4386, 79.1288),
        ("Nizamabad", 18.6725, 78.0941),
        ("Khammam", 17.2473, 80.1514),
        ("Mahabubnagar", 16.7488, 78.0035),
        ("Nalgonda", 17.0575, 79.2684),
        ("Siddipet", 18.1018, 78.8520),
        ("Chevella (Rangareddy)", 17.3079, 78.1363)
    ]

    print(f"Total simple names configured: {len(simple_names)}")

    for i in range(1, 116):
        uid = f"{i:03d}"
        name = simple_names[i - 1]
        phone = f"900000{i:04d}"
        v_name, v_lat, v_lon = villages[(i - 1) % len(villages)]
        lat = round(v_lat + random.uniform(-0.02, 0.02), 4)
        lon = round(v_lon + random.uniform(-0.02, 0.02), 4)

        # Check if record exists
        c.execute("SELECT id FROM users WHERE unique_id = ?", (uid,))
        existing = c.fetchone()
        
        if existing:
            c.execute("""
            UPDATE users 
            SET name = ?, phone = ?, village = ?, latitude = ?, longitude = ?, role = 'Mother'
            WHERE unique_id = ?
            """, (name, phone, v_name, lat, lon, uid))
        else:
            c.execute("""
            INSERT INTO users (unique_id, name, role, phone, village, latitude, longitude)
            VALUES (?, ?, 'Mother', ?, ?, ?, ?)
            """, (uid, name, phone, v_name, lat, lon))
            print(f"Inserted new Mother ID: {uid} - {name}")

    conn.commit()
    
    # Verify count and sample
    c.execute("SELECT count(*) FROM users WHERE role='Mother'")
    count = c.fetchone()[0]
    print(f"\nTotal Mothers in database now: {count}")
    
    c.execute("SELECT unique_id, name, phone, village FROM users WHERE role='Mother' ORDER BY CAST(unique_id AS INTEGER) ASC LIMIT 15")
    sample = c.fetchall()
    print("\nSample first 15 records:")
    for row in sample:
        print(f"ID: {row[0]} | Name: {row[1]} | Phone: {row[2]} | Village: {row[3]}")

    c.execute("SELECT unique_id, name, phone, village FROM users WHERE role='Mother' ORDER BY CAST(unique_id AS INTEGER) DESC LIMIT 10")
    last_sample = c.fetchall()
    print("\nSample last 10 records:")
    for row in last_sample:
        print(f"ID: {row[0]} | Name: {row[1]} | Phone: {row[2]} | Village: {row[3]}")

    # Ensure baby profiles exist for testing
    from database import register_baby
    c.execute("SELECT mother_id FROM baby_profiles WHERE mother_id IN ('001', '002')")
    existing_babies = [row[0] for row in c.fetchall()]
    if '001' not in existing_babies:
        register_baby('001', '2026-05-15', 'Female')
        print("Baby registered for 001 (Sath)")
    if '002' not in existing_babies:
        register_baby('002', '2026-06-20', 'Male')
        print("Baby registered for 002 (Pink)")

    conn.close()

if __name__ == "__main__":
    update_115_mothers()
