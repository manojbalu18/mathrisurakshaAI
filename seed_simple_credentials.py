import sqlite3
import datetime
import random

def seed_database():
    conn = sqlite3.connect('maatrisuraksha.db')
    c = conn.cursor()
    
    # 1. Clear existing data
    tables = [
        'users', 'daily_logs', 'alerts', 'mock_sms_logs', 'sms_logs', 
        'call_logs', 'offline_sync', 'baby_profiles', 'baby_logs', 
        'vaccinations', 'exercise_logs', 'case_actions'
    ]
    for t in tables:
        try:
            c.execute(f"DELETE FROM {t}")
        except sqlite3.OperationalError:
            pass
            
    print("Cleaned tables for fresh seeding...")
    
    # 2. Patient Definitions (Simple ID & Simple Name)
    patients = [
        ("001", "Sath", "Rampur", 17.3850, 78.4867, "9876543201", "Low", 15),
        ("002", "Pink", "Sitapur", 17.4010, 78.4720, "9876543202", "Medium", 45),
        ("003", "Amu", "Chandrapur", 17.3700, 78.5000, "9876543203", "High", 85),
        ("004", "Sonu", "Bharatpur", 17.4200, 78.4500, "9876543204", "Low", 10),
        ("005", "Priya", "Janakpur", 17.3900, 78.5200, "9876543205", "Medium", 50),
        ("006", "Jula", "Rampur", 17.3800, 78.4900, "9876543206", "Low", 20),
        ("007", "Rosh", "Sitapur", 17.4100, 78.4600, "9876543207", "High", 90),
        ("008", "Nithu", "Chandrapur", 17.3650, 78.5100, "9876543208", "Low", 12),
        ("009", "Chikky", "Bharatpur", 17.4250, 78.4450, "9876543209", "Medium", 40),
        ("010", "Cherry", "Janakpur", 17.3950, 78.5250, "9876543210", "Low", 18),
        ("011", "Anita", "Rampur", 17.3820, 78.4880, "9876543211", "Low", 22),
        ("012", "Hasini", "Sitapur", 17.4050, 78.4680, "9876543212", "Medium", 55),
        ("013", "Radha", "Chandrapur", 17.3720, 78.4980, "9876543213", "High", 80),
        ("014", "Kavya", "Bharatpur", 17.4180, 78.4550, "9876543214", "Low", 10),
        ("015", "Meera", "Janakpur", 17.3920, 78.5180, "9876543215", "Low", 15),
        ("016", "Divya", "Rampur", 17.3870, 78.4830, "9876543216", "Medium", 42),
        ("017", "Sneha", "Sitapur", 17.4080, 78.4630, "9876543217", "Low", 14),
        ("018", "Swathi", "Chandrapur", 17.3680, 78.5050, "9876543218", "Low", 16),
        ("019", "Pooja", "Bharatpur", 17.4220, 78.4480, "9876543219", "High", 88),
        ("020", "Ritu", "Janakpur", 17.3980, 78.5220, "9876543220", "Low", 10)
    ]
    
    now = datetime.datetime.now()
    
    for uid, name, village, lat, lon, phone, risk_lvl, risk_score in patients:
        # Insert user
        c.execute("""
            INSERT INTO users (unique_id, name, role, phone, village, latitude, longitude)
            VALUES (?, ?, 'Mother', ?, ?, ?, ?)
        """, (uid, name, phone, village, lat, lon))
        
        # Insert 3 days of daily logs
        for d in range(2, -1, -1):
            log_dt = now - datetime.timedelta(days=d, hours=random.randint(1, 4))
            date_str = log_dt.strftime("%Y-%m-%d %H:%M:%S")
            
            symptoms = "Normal, Mild Nausea" if risk_lvl == "Low" else ("Moderate Fatigue, Backache" if risk_lvl == "Medium" else "High BP, Severe Swelling, Dizziness")
            mood = "Good" if risk_lvl == "Low" else ("Okay" if risk_lvl == "Medium" else "Anxious")
            nutrition = "Good" if risk_lvl == "Low" else ("Moderate" if risk_lvl == "Medium" else "Poor")
            cur_score = risk_score if d == 0 else max(10, risk_score - random.randint(0, 10))
            cur_lvl = risk_lvl if d == 0 else ("Low" if cur_score < 30 else ("Medium" if cur_score < 60 else "High"))
            
            c.execute("""
                INSERT INTO daily_logs (user_id, symptoms, mood, nutrition, risk_score, risk_level, date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (uid, symptoms, mood, nutrition, cur_score, cur_lvl, date_str))
            
        # If high risk, create an active alert
        if risk_lvl == "High":
            alert_dt = (now - datetime.timedelta(hours=random.randint(1, 6))).strftime("%Y-%m-%d %H:%M:%S")
            c.execute("""
                INSERT INTO alerts (user_id, risk_level, status, timestamp)
                VALUES (?, 'High', 'Active', ?)
            """, (uid, alert_dt))
            
            # Add a case action for follow up
            c.execute("""
                INSERT INTO case_actions (mother_id, asha_id, status, action_taken, notes, followup_date, timestamp)
                VALUES (?, 'ASHA-7075287040', 'Escalated', 'Telephonic Triage & Doctor Alerted', 'Immediate home visit scheduled', ?, ?)
            """, (uid, (now + datetime.timedelta(days=1)).strftime("%Y-%m-%d"), alert_dt))
            
    # 3. Seed Baby Profiles for selected mothers
    baby_mothers = [
        ("001", "Female", 60, "Sath"),
        ("002", "Male", 90, "Pink"),
        ("003", "Female", 30, "Amu"),
        ("004", "Male", 120, "Sonu"),
        ("005", "Female", 45, "Priya"),
        ("008", "Male", 75, "Nithu"),
        ("010", "Female", 15, "Cherry")
    ]
    
    vaccine_types = [
        ("BCG, OPV-0", 0),
        ("DPT-1, Hepatitis B-1, OPV-1", 42),
        ("DPT-2, OPV-2", 70),
        ("DPT-3, OPV-3", 98),
        ("Measles, Vitamin A", 270)
    ]
    
    for uid, gender, age_days, m_name in baby_mothers:
        delivery_dt = now - datetime.timedelta(days=age_days)
        delivery_str = delivery_dt.strftime("%Y-%m-%d")
        created_at = now.strftime("%Y-%m-%d %H:%M:%S")
        
        c.execute("""
            INSERT INTO baby_profiles (mother_id, delivery_date, baby_gender, created_at)
            VALUES (?, ?, ?, ?)
        """, (uid, delivery_str, gender, created_at))
        
        # Vaccinations
        for vname, voffset in vaccine_types:
            due_dt = delivery_dt + datetime.timedelta(days=voffset)
            status = "Completed" if due_dt <= now else "Pending"
            c.execute("""
                INSERT INTO vaccinations (mother_id, vaccine_name, due_date, status)
                VALUES (?, ?, ?, ?)
            """, (uid, vname, due_dt.strftime("%Y-%m-%d"), status))
            
        # Growth & Health Logs
        start_wt = 3.1 if gender == "Female" else 3.3
        for step in range(4):
            log_days_ago = int(age_days * (1 - step / 3))
            log_dt = now - datetime.timedelta(days=log_days_ago)
            curr_wt = round(start_wt + (age_days - log_days_ago) * 0.025, 2)
            c.execute("""
                INSERT INTO baby_logs (mother_id, fever, cough, weight, feeding_pattern, sleep_hours, date)
                VALUES (?, 'No', 'No', ?, 'Exclusive Breastfeeding', 14.5, ?)
            """, (uid, curr_wt, log_dt.strftime("%Y-%m-%d %H:%M:%S")))
            
    conn.commit()
    conn.close()
    print("Database successfully seeded with simple credentials & rich portal data!")

if __name__ == "__main__":
    seed_database()
