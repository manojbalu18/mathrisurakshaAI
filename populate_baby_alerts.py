import sqlite3
import datetime

conn = sqlite3.connect("maatrisuraksha.db")
c = conn.cursor()

# Get some mothers from the recently generated block
c.execute("SELECT unique_id, name FROM users WHERE unique_id LIKE 'M-1%' LIMIT 5")
mothers = c.fetchall()

# Close connection before calling register_baby (which handles its own conn)
conn.close()

from database import register_baby

print("Generating baby health alerts for testing...")

now = datetime.datetime.now()

for i, (mid, name) in enumerate(mothers):
    # Register a baby
    age_days = 20 + (i * 10)
    del_dt = (now - datetime.timedelta(days=age_days)).strftime("%Y-%m-%d")
    register_baby(mid, del_dt, "Male" if i % 2 == 0 else "Female")
    
    # Add a critical baby log inside a short-lived connection
    log_dt = now.strftime("%Y-%m-%d %H:%M:%S")
    fever = "High" if i % 2 == 0 else "No"
    weight = 2.0 if i % 2 != 0 else 5.0 # Low weight for odds
    
    sub_conn = sqlite3.connect("maatrisuraksha.db")
    sub_c = sub_conn.cursor()
    sub_c.execute("""
    INSERT INTO baby_logs (mother_id, fever, cough, weight, feeding_pattern, sleep_hours, date)
    VALUES (?, ?, 'Mild', ?, 'Every 2 hours', 10, ?)
    """, (mid, fever, weight, log_dt))
    sub_conn.commit()
    sub_conn.close()

print("Successfully injected critical baby health logs.")
