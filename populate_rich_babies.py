import sqlite3
import datetime
import random

def populate_rich_babies():
    conn = sqlite3.connect('maatrisuraksha.db', timeout=30.0)
    c = conn.cursor()
    
    baby_mothers = [
        ("001", "Female", 110, "Sath"),
        ("002", "Male", 75, "Pink"),
        ("003", "Female", 45, "Vika"),
        ("004", "Male", 160, "Amu"),
        ("005", "Female", 90, "Sonu"),
        ("006", "Male", 30, "Priya"),
        ("007", "Female", 140, "Rosh"),
        ("008", "Male", 60, "Nithu"),
        ("009", "Female", 180, "Chikky"),
        ("010", "Male", 20, "Cherry"),
        ("011", "Female", 100, "Laddu"),
        ("012", "Male", 15, "Hasini"),
        ("013", "Female", 130, "Divya"),
        ("014", "Male", 50, "Sneha"),
        ("015", "Female", 65, "Swathi"),
        ("020", "Male", 85, "Zoya"),
        ("036", "Female", 35, "Gauri"),
        ("050", "Male", 120, "Sony"),
        ("082", "Female", 92, "Varsha"),
        ("095", "Male", 138, "Vaishnavi")
    ]
    
    now = datetime.datetime.now()
    
    vaccines = [
        ("BCG, OPV", 0), # Birth
        ("DPT, Hepatitis B", 42), # 6 weeks
        ("DPT", 70), # 10 weeks
        ("DPT", 98), # 14 weeks
        ("Measles", 270) # 9 months
    ]
    
    for uid, gender, days_ago, name in baby_mothers:
        delivery_dt = now - datetime.timedelta(days=days_ago)
        delivery_str = delivery_dt.strftime("%Y-%m-%d")
        created_at = now.strftime("%Y-%m-%d %H:%M:%S")
        
        c.execute("SELECT id FROM baby_profiles WHERE mother_id=?", (uid,))
        exists = c.fetchone()
        
        if not exists:
            c.execute("""
            INSERT INTO baby_profiles (mother_id, delivery_date, baby_gender, created_at)
            VALUES (?, ?, ?, ?)
            """, (uid, delivery_str, gender, created_at))
            print(f"Registered Baby for Mother ID: {uid} ({name}), Age: {days_ago} days, Gender: {gender}")
            
            for v_name, days_after in vaccines:
                due_dt = delivery_dt + datetime.timedelta(days=days_after)
                status = "Completed" if due_dt <= now else "Pending"
                c.execute("""
                INSERT INTO vaccinations (mother_id, vaccine_name, due_date, status)
                VALUES (?, ?, ?, ?)
                """, (uid, v_name, due_dt.strftime("%Y-%m-%d"), status))
        else:
            c.execute("UPDATE baby_profiles SET delivery_date=?, baby_gender=? WHERE mother_id=?", (delivery_str, gender, uid))
            
            # Update vaccinations
            c.execute("SELECT id, due_date FROM vaccinations WHERE mother_id=?", (uid,))
            vaxes = c.fetchall()
            for v_id, due_str in vaxes:
                due_dt = datetime.datetime.strptime(due_str, "%Y-%m-%d")
                status = "Completed" if due_dt <= now else "Pending"
                c.execute("UPDATE vaccinations SET status=? WHERE id=?", (status, v_id))
                
        # Clear old logs for clean history
        c.execute("DELETE FROM baby_logs WHERE mother_id=?", (uid,))
        
        # Add 5 historical growth logs
        start_wt = 3.0 if gender == "Female" else 3.2
        num_logs = 5
        for step in range(num_logs):
            log_days_ago = int(days_ago * (1 - step / (num_logs - 1)))
            log_dt = now - datetime.timedelta(days=log_days_ago)
            log_date_str = log_dt.strftime("%Y-%m-%d %H:%M:%S")
            
            curr_wt = round(start_wt + (days_ago - log_days_ago) * 0.025 + random.uniform(-0.05, 0.05), 2)
            fever = "No" if step != 2 or random.random() > 0.3 else "Yes"
            cough = "No" if step != 3 or random.random() > 0.3 else "Yes"
            feeding = random.choice(["Exclusive Breastfeeding", "Formula Milk", "Mixed Feeding", "Semi-Solids + Milk"])
            sleep = round(random.uniform(12.5, 16.0), 1)
            
            c.execute("""
            INSERT INTO baby_logs (mother_id, fever, cough, weight, feeding_pattern, sleep_hours, date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (uid, fever, cough, curr_wt, feeding, sleep, log_date_str))
            
    conn.commit()
    
    c.execute("SELECT count(*) FROM baby_profiles")
    total_babies = c.fetchone()[0]
    print(f"\nTotal Registered Baby Profiles: {total_babies}")
    
    conn.close()

if __name__ == "__main__":
    populate_rich_babies()
