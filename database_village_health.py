import sqlite3

# ---------------- VILLAGE HEALTH INTELLIGENCE QUERIES ----------------

def get_maternal_risk_distribution():
    """Returns count of mothers by risk level (Low, Medium, High)."""
    conn = sqlite3.connect("maatrisuraksha.db")
    c = conn.cursor()
    # We take the latest log for each mother to determine current risk
    c.execute("""
    SELECT 
        CASE 
            WHEN risk_score >= 71 THEN 'High Risk'
            WHEN risk_score >= 31 THEN 'Medium Risk'
            ELSE 'Low Risk'
        END as risk_category,
        COUNT(*) as count
    FROM (
        SELECT user_id, risk_score
        FROM daily_logs
        WHERE id IN (
            SELECT MAX(id) FROM daily_logs GROUP BY user_id
        )
    )
    GROUP BY risk_category
    """)
    distribution = c.fetchall()
    conn.close()
    
    # Format into dict
    res = {"Low Risk": 0, "Medium Risk": 0, "High Risk": 0}
    for row in distribution:
        res[row[0]] = row[1]
    return res

def get_village_risk_aggregations():
    """Returns aggregated avg risk score and location for each village."""
    conn = sqlite3.connect("maatrisuraksha.db")
    c = conn.cursor()
    c.execute("""
    SELECT u.village, AVG(u.latitude), AVG(u.longitude), AVG(d.risk_score), COUNT(u.id)
    FROM users u
    JOIN (
        SELECT user_id, risk_score
        FROM daily_logs
        WHERE id IN (SELECT MAX(id) FROM daily_logs GROUP BY user_id)
    ) d ON u.id = d.user_id
    WHERE u.role = 'Mother' AND u.latitude != 0.0 AND u.longitude != 0.0
    GROUP BY u.village
    """)
    villages = c.fetchall()
    conn.close()
    
    results = []
    for v in villages:
        score = v[3] or 0
        if score >= 71:
            cat = "High Risk"
        elif score >= 31:
            cat = "Medium Risk"
        else:
            cat = "Low Risk"
            
        results.append({
            "Village": v[0],
            "Lat": v[1],
            "Lon": v[2],
            "AvgScore": round(score, 1),
            "Mothers": v[4],
            "Category": cat
        })
    return results

def get_vaccination_coverage():
    """Returns counts for Completed, Pending, and Overdue vaccines."""
    import datetime
    conn = sqlite3.connect("maatrisuraksha.db")
    c = conn.cursor()
    c.execute("SELECT due_date, status FROM vaccinations")
    rows = c.fetchall()
    conn.close()
    
    now_dt = datetime.datetime.now()
    completed = int(0)
    pending = int(0)
    overdue = int(0)
    
    for row in rows:
        if row[1] == 'Completed':
            completed = completed + 1
        else:
            try:
                due_dt = datetime.datetime.strptime(str(row[0]), "%Y-%m-%d")
                if (due_dt - now_dt).days < 0:
                    overdue = overdue + 1
                else:
                    pending = pending + 1
            except:
                pending = pending + 1
                
    return {"Vaccinated": completed, "Pending": pending, "Overdue": overdue}

def get_high_risk_mothers_alert():
    """Returns recent high risk mother records."""
    conn = sqlite3.connect("maatrisuraksha.db")
    c = conn.cursor()
    c.execute("""
    SELECT u.unique_id, u.village, d.risk_score, d.symptoms
    FROM users u
    JOIN daily_logs d ON u.id = d.user_id
    WHERE d.id IN (SELECT MAX(id) FROM daily_logs GROUP BY user_id)
    AND d.risk_score >= 71 AND u.role = 'Mother'
    ORDER BY d.risk_score DESC
    """)
    mothers = c.fetchall()
    conn.close()
    return mothers

def get_baby_health_alerts():
    """Returns babies with high fever or low weight logs."""
    import datetime
    conn = sqlite3.connect("maatrisuraksha.db")
    c = conn.cursor()
    # Looking at logs in the last 7 days roughly
    c.execute("""
    SELECT b.mother_id, u.village, b.fever, b.weight, b.date
    FROM baby_logs b
    JOIN users u ON b.mother_id = u.unique_id
    WHERE (b.fever = 'High' OR b.weight < 2.5)
    ORDER BY b.date DESC
    LIMIT 10
    """)
    alerts = c.fetchall()
    conn.close()
    
    res = []
    for a in alerts:
        res.append({
            "Mother ID": a[0],
            "Village": a[1],
            "Issue": f"Fever: {a[2]}, Weight: {a[3]}kg"
        })
    return res

def get_upcoming_vaccinations(days=7):
    """Returns vaccines due in the next X days."""
    import datetime
    conn = sqlite3.connect("maatrisuraksha.db")
    c = conn.cursor()
    c.execute("""
    SELECT mother_id, vaccine_name, due_date 
    FROM vaccinations 
    WHERE status = 'Pending'
    ORDER BY due_date ASC
    """)
    rows = c.fetchall()
    conn.close()
    
    now_dt = datetime.datetime.now()
    upcoming = []
    for r in rows:
        try:
            due_dt = datetime.datetime.strptime(r[2], "%Y-%m-%d")
            delta = (due_dt - now_dt).days
            if 0 <= delta <= days:
                if delta == 0:
                    time_str = "Today"
                elif delta == 1:
                    time_str = "Tomorrow"
                else:
                    time_str = f"in {delta} days"
                upcoming.append({
                    "Mother ID": r[0],
                    "Vaccine": r[1],
                    "Time": time_str
                })
        except:
            pass
    return upcoming

def generate_asha_daily_tasks():
    """Generates a dynamic daily task string list for ASHA worker."""
    tasks = []
    
    # 1. High Risk Follow-ups
    high_risk = get_high_risk_mothers_alert()
    for hm in high_risk:
        tasks.append({
            "type": "followup_high_risk",
            "args": (hm[0], hm[1])
        })
        
    # 2. Vaccinations Today
    vax = get_upcoming_vaccinations(days=1)
    for v in vax:
        if v["Time"] in ["Today", "Tomorrow"]:
            tasks.append({
                "type": "vax_today",
                "args": (v['Mother ID'], v['Vaccine'], v['Time'])
            })
            
    # 3. Third Trimester / Late Pregnancy Visits
    conn = sqlite3.connect("maatrisuraksha.db")
    c = conn.cursor()
    c.execute("""
    SELECT u.unique_id, u.name 
    FROM users u
    JOIN daily_logs d ON u.id = d.user_id
    WHERE d.id IN (SELECT MAX(id) FROM daily_logs GROUP BY user_id)
    AND d.risk_score >= 31 AND d.risk_score < 71 AND u.role = 'Mother'
    LIMIT 3
    """)
    med_risk = c.fetchall()
    conn.close()
    
    for mr in med_risk:
        tasks.append({
            "type": "routine_visit",
            "args": (mr[1], mr[0])
        })
        
    if not tasks:
        tasks.append({
            "type": "no_critical",
            "args": ()
        })
        
    return tasks
