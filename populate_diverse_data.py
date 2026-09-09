import sqlite3
import datetime
import random

def populate_diverse_data():
    conn = sqlite3.connect("maatrisuraksha.db")
    c = conn.cursor()

    # Get all unique IDs of mothers
    c.execute("SELECT unique_id FROM users WHERE role='Mother'")
    mother_ids = [row[0] for row in c.fetchall()]

    if not mother_ids:
        print("No mothers found. Run populate_mothers.py first.")
        return

    print(f"Found {len(mother_ids)} mothers.")

    # 1. Add some vaccinations (status='Pending', due_date today/tomorrow or next week)
    vaccines = ["TT-1", "TT-2", "IFA", "Calcium", "Iron"]
    today = datetime.datetime.now()
    
    print("Clearing old vaccinations...")
    c.execute("DELETE FROM vaccinations")

    print("Adding sample vaccinations...")
    for _ in range(25):
        m_id = random.choice(mother_ids)
        vax = random.choice(vaccines)
        # Randomly choose Today, Tomorrow, or next 7 days
        days_offset = random.randint(0, 10)
        due_date = (today + datetime.timedelta(days=days_offset)).strftime("%Y-%m-%d")
        
        c.execute("""
        INSERT INTO vaccinations (mother_id, vaccine_name, due_date, status)
        VALUES (?, ?, ?, 'Pending')
        """, (m_id, vax, due_date))

    # 2. Add some medium-risk daily logs to trigger routine check-ups
    # (risk_score between 31 and 70)
    print("Adding medium-risk logs for routine visits...")
    for _ in range(15):
        m_id = random.choice(mother_ids)
        # Get internal ID for this mother
        c.execute("SELECT id FROM users WHERE unique_id=?", (m_id,))
        user_row = c.fetchone()
        if not user_row: continue
        user_id = user_row[0]
        
        score = random.randint(35, 65)
        date_str = today.strftime("%Y-%m-%d %H:%M:%S")
        
        c.execute("""
        INSERT INTO daily_logs (user_id, symptoms, mood, nutrition, risk_score, risk_level, date)
        VALUES (?, 'mild fatigue', 'normal', 'moderate', ?, 'Medium', ?)
        """, (user_id, score, date_str))

    # 3. Add some recent high-risk alerts if not enough
    print("Adding fresh high-risk alerts...")
    for _ in range(5):
        m_id = random.choice(mother_ids)
        c.execute("SELECT id FROM users WHERE unique_id=?", (m_id,))
        user_row = c.fetchone()
        if not user_row: continue
        user_id = user_row[0]
        
        score = random.randint(75, 95)
        date_str = today.strftime("%Y-%m-%d %H:%M:%S")
        
        # Add to daily_logs
        c.execute("""
        INSERT INTO daily_logs (user_id, symptoms, mood, nutrition, risk_score, risk_level, date)
        VALUES (?, 'swelling, dizziness', 'stressed', 'poor', ?, 'High', ?)
        """, (user_id, score, date_str))
        
        # Add to alerts
        c.execute("""
        INSERT INTO alerts (user_id, risk_level, status, timestamp)
        VALUES (?, 'High', 'Active', ?)
        """, (m_id, date_str)) # Note: using unique_id here for alerts as per recent dashboard fixes

    conn.commit()
    conn.close()
    print("Diverse data population complete!")

if __name__ == "__main__":
    populate_diverse_data()
