import sqlite3
import random
import datetime

# We need a set of realistic villages that will act as clusters
villages = [
    {"name": "Rampur", "lat": 17.3850, "lon": 78.4867, "risk_bias": "High"},
    {"name": "Sitapur", "lat": 17.4120, "lon": 78.4110, "risk_bias": "Medium"},
    {"name": "Kondapur", "lat": 17.4622, "lon": 78.3568, "risk_bias": "Low"}
]

names = ["Aarti", "Bhavna", "Chitra", "Divya", "Esha", "Falguni", "Gita", "Hema", "Isha", "Jaya", "Kavita", "Lata", "Meena", "Neha", "Pooja", "Rajani", "Sita", "Tara", "Uma", "Vandana"]

conn = sqlite3.connect("maatrisuraksha.db")
c = conn.cursor()

print("Injecting new village clusters for maternal risk analytics...")

for i in range(101, 131):  # Add 30 new mothers
    m_id = f"M-{i}"
    m_name = random.choice(names)
    v_data = random.choice(villages)
    
    # Generate lat/lon slightly off center from the village hub
    lat = v_data["lat"] + random.uniform(-0.01, 0.01)
    lon = v_data["lon"] + random.uniform(-0.01, 0.01)
    
    c.execute("""
    INSERT INTO users (unique_id, name, role, phone, village, latitude, longitude)
    VALUES (?, ?, 'Mother', '9876543210', ?, ?, ?)
    """, (m_id, f"{m_name} ({v_data['name']})", v_data["name"], lat, lon))
    user_id = c.lastrowid
    
    # Assign Risk Score based on village bias
    if v_data["risk_bias"] == "High":
        score = random.randint(71, 95)
        level = "High"
        symptoms = random.choice(["Swelling", "High BP", "Severe headache", "Bleeding"])
    elif v_data["risk_bias"] == "Medium":
        score = random.randint(31, 70)
        level = "Medium"
        symptoms = random.choice(["Mild fever", "Slight dizziness", "Fatigue"])
    else:
        score = random.randint(0, 30)
        level = "Low"
        symptoms = "None"
        
    date_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute("""
    INSERT INTO daily_logs (user_id, symptoms, mood, nutrition, risk_score, risk_level, date)
    VALUES (?, ?, 'Normal', 'Good', ?, ?, ?)
    """, (user_id, symptoms, score, level, date_str))

conn.commit()
conn.close()

print("Successfully generated 30 new mothers with clustered risk levels (Rampur=High, Sitapur=Med, Kondapur=Low).")
