import sqlite3
import datetime

def get_connection():
    """Returns a fast SQLite connection configured with WAL journal mode and memory caching."""
    conn = sqlite3.connect("maatrisuraksha.db", check_same_thread=False, timeout=10.0)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA cache_size = 10000;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    return conn

# ---------------- VILLAGE HEALTH INTELLIGENCE QUERIES ----------------

def _user_id_match_clause(user_col="u.unique_id", log_col="l.user_id"):
    """Generates SQL condition to match user IDs across text, int, and zero-padded variants."""
    return f"""(
        CAST({user_col} AS TEXT) = CAST({log_col} AS TEXT)
        OR ({user_col} GLOB '[0-9]*' AND {log_col} GLOB '[0-9]*' AND CAST({user_col} AS INTEGER) = CAST({log_col} AS INTEGER))
        OR (CAST(u.id AS TEXT) = CAST({log_col} AS TEXT))
    )"""

def get_maternal_risk_distribution():
    """Returns count of all registered mothers categorized by current risk level (Low, Medium, High)."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
    WITH LatestLogs AS (
        SELECT user_id, risk_score, risk_level
        FROM daily_logs
        WHERE id IN (SELECT MAX(id) FROM daily_logs GROUP BY user_id)
    )
    SELECT 
        CASE 
            WHEN COALESCE(l.risk_score, 0) >= 60 OR l.risk_level = 'High' THEN 'High Risk'
            WHEN COALESCE(l.risk_score, 0) >= 30 OR l.risk_level = 'Medium' THEN 'Medium Risk'
            ELSE 'Low Risk'
        END as risk_category,
        COUNT(*) as count
    FROM users u
    LEFT JOIN LatestLogs l ON (
        CAST(u.unique_id AS TEXT) = CAST(l.user_id AS TEXT)
        OR (u.unique_id GLOB '[0-9]*' AND l.user_id GLOB '[0-9]*' AND CAST(u.unique_id AS INTEGER) = CAST(l.user_id AS INTEGER))
        OR CAST(u.id AS TEXT) = CAST(l.user_id AS TEXT)
    )
    WHERE u.role = 'Mother'
    GROUP BY risk_category
    """)
    distribution = c.fetchall()
    conn.close()
    
    res = {"Low Risk": 0, "Medium Risk": 0, "High Risk": 0}
    for row in distribution:
        if row[0] in res:
            res[row[0]] = row[1]
    return res

def get_village_risk_aggregations():
    """Returns aggregated avg risk score and location for each village from live database."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
    WITH LatestLogs AS (
        SELECT user_id, risk_score
        FROM daily_logs
        WHERE id IN (SELECT MAX(id) FROM daily_logs GROUP BY user_id)
    )
    SELECT u.village, 
           AVG(CASE WHEN u.latitude != 0.0 THEN u.latitude ELSE 17.3850 END) as avg_lat, 
           AVG(CASE WHEN u.longitude != 0.0 THEN u.longitude ELSE 78.4867 END) as avg_lon, 
           AVG(COALESCE(l.risk_score, 15)) as avg_score, 
           COUNT(u.id) as total_m
    FROM users u
    LEFT JOIN LatestLogs l ON (
        CAST(u.unique_id AS TEXT) = CAST(l.user_id AS TEXT)
        OR (u.unique_id GLOB '[0-9]*' AND l.user_id GLOB '[0-9]*' AND CAST(u.unique_id AS INTEGER) = CAST(l.user_id AS INTEGER))
        OR CAST(u.id AS TEXT) = CAST(l.user_id AS TEXT)
    )
    WHERE u.role = 'Mother' AND u.village IS NOT NULL AND u.village != ''
    GROUP BY u.village
    """)
    villages = c.fetchall()
    conn.close()
    
    results = []
    for v in villages:
        score = v[3] or 0
        if score >= 60:
            cat = "High Risk"
        elif score >= 30:
            cat = "Medium Risk"
        else:
            cat = "Low Risk"
            
        results.append({
            "Village": v[0],
            "Lat": v[1],
            "Lon": v[2],
            "AvgScore": round(float(score), 1),
            "Mothers": v[4],
            "Category": cat
        })
    return results

def get_vaccination_coverage():
    """Returns counts for Completed, Pending, and Overdue vaccines."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT due_date, status FROM vaccinations")
    rows = c.fetchall()
    conn.close()
    
    now_dt = datetime.datetime.now()
    completed = 0
    pending = 0
    overdue = 0
    
    for row in rows:
        if row[1] == 'Completed':
            completed += 1
        else:
            try:
                due_dt = datetime.datetime.strptime(str(row[0]), "%Y-%m-%d")
                if (due_dt - now_dt).days < 0:
                    overdue += 1
                else:
                    pending += 1
            except Exception:
                pending += 1
                
    return {"Vaccinated": completed, "Pending": pending, "Overdue": overdue}

def get_high_risk_mothers_alert():
    """Returns high risk mother records with active alerts or risk score >= 60."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
    WITH LatestLogs AS (
        SELECT user_id, risk_score, risk_level, symptoms, date
        FROM daily_logs
        WHERE id IN (SELECT MAX(id) FROM daily_logs GROUP BY user_id)
    ),
    ActiveAlerts AS (
        SELECT user_id, status, timestamp FROM alerts WHERE status = 'Active' GROUP BY user_id
    ),
    LatestActions AS (
        SELECT mother_id, status, action_taken, timestamp
        FROM case_actions
        WHERE id IN (SELECT MAX(id) FROM case_actions GROUP BY mother_id)
    )
    SELECT u.unique_id, u.name, u.village, 
           COALESCE(l.risk_score, 75) as risk_score, 
           COALESCE(l.symptoms, 'Severe symptoms reported') as symptoms,
           COALESCE(act.status, CASE WHEN a.user_id IS NOT NULL THEN 'High Risk' ELSE 'Pending' END) as current_status,
           COALESCE(act.action_taken, 'Requires Immediate Review') as action_taken,
           COALESCE(l.date, a.timestamp, 'Recent') as last_updated
    FROM users u
    LEFT JOIN LatestLogs l ON (
        CAST(u.unique_id AS TEXT) = CAST(l.user_id AS TEXT)
        OR (u.unique_id GLOB '[0-9]*' AND l.user_id GLOB '[0-9]*' AND CAST(u.unique_id AS INTEGER) = CAST(l.user_id AS INTEGER))
        OR CAST(u.id AS TEXT) = CAST(l.user_id AS TEXT)
    )
    LEFT JOIN ActiveAlerts a ON (
        CAST(u.unique_id AS TEXT) = CAST(a.user_id AS TEXT)
        OR (u.unique_id GLOB '[0-9]*' AND a.user_id GLOB '[0-9]*' AND CAST(u.unique_id AS INTEGER) = CAST(a.user_id AS INTEGER))
        OR CAST(u.id AS TEXT) = CAST(a.user_id AS TEXT)
    )
    LEFT JOIN LatestActions act ON (
        CAST(u.unique_id AS TEXT) = CAST(act.mother_id AS TEXT)
        OR (u.unique_id GLOB '[0-9]*' AND act.mother_id GLOB '[0-9]*' AND CAST(u.unique_id AS INTEGER) = CAST(act.mother_id AS INTEGER))
    )
    WHERE u.role = 'Mother' AND (l.risk_score >= 60 OR l.risk_level = 'High' OR a.user_id IS NOT NULL)
    ORDER BY l.risk_score DESC
    """)
    mothers = c.fetchall()
    conn.close()
    return mothers

def get_baby_health_alerts():
    """Returns babies with high fever or low weight logs."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
    SELECT b.mother_id, u.village, b.fever, b.weight, b.date
    FROM baby_logs b
    JOIN users u ON (
        CAST(b.mother_id AS TEXT) = CAST(u.unique_id AS TEXT) 
        OR (b.mother_id GLOB '[0-9]*' AND u.unique_id GLOB '[0-9]*' AND CAST(b.mother_id AS INTEGER) = CAST(u.unique_id AS INTEGER))
        OR CAST(b.mother_id AS TEXT) = CAST(u.id AS TEXT)
    )
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
    conn = get_connection()
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
        except Exception:
            pass
    return upcoming

def generate_asha_daily_tasks():
    """Generates dynamic daily task list for ASHA worker."""
    tasks = []
    
    # 1. High Risk Follow-ups
    high_risk = get_high_risk_mothers_alert()
    for hm in high_risk:
        tasks.append({
            "type": "followup_high_risk",
            "args": (hm[0], hm[3])
        })
        
    # 2. Vaccinations Today
    vax = get_upcoming_vaccinations(days=1)
    for v in vax:
        if v["Time"] in ["Today", "Tomorrow"]:
            tasks.append({
                "type": "vax_today",
                "args": (v['Mother ID'], v['Vaccine'], v['Time'])
            })
            
    # 3. Third Trimester / Moderate Risk Visits
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
    SELECT u.unique_id, u.name 
    FROM users u
    JOIN daily_logs d ON (
        CAST(u.id AS TEXT) = CAST(d.user_id AS TEXT) 
        OR CAST(u.unique_id AS TEXT) = CAST(d.user_id AS TEXT)
        OR (u.unique_id GLOB '[0-9]*' AND d.user_id GLOB '[0-9]*' AND CAST(u.unique_id AS INTEGER) = CAST(d.user_id AS INTEGER))
    )
    WHERE d.id IN (SELECT MAX(id) FROM daily_logs GROUP BY user_id)
    AND d.risk_score >= 30 AND d.risk_score < 60 AND u.role = 'Mother'
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

# ---------------- SUPERVISOR & ASHA METRICS ENGINE ----------------

def get_supervisor_metrics():
    """
    Computes 100% live database metrics for the Supervisor Portal:
    Total Cases, High Risk, Medium Risk, Safe, Pending, In Progress, Referred, Follow-up, Resolved.
    """
    conn = get_connection()
    c = conn.cursor()
    
    c.execute("""
    WITH LatestLogs AS (
        SELECT user_id, risk_score, risk_level, date
        FROM daily_logs
        WHERE id IN (SELECT MAX(id) FROM daily_logs GROUP BY user_id)
    ),
    ActiveAlerts AS (
        SELECT user_id, status FROM alerts WHERE status = 'Active' GROUP BY user_id
    ),
    LatestActions AS (
        SELECT mother_id, status, action_taken, followup_date, timestamp
        FROM case_actions
        WHERE id IN (SELECT MAX(id) FROM case_actions GROUP BY mother_id)
    )
    SELECT u.unique_id,
           COALESCE(l.risk_score, 0) as risk_score,
           COALESCE(l.risk_level, 'Low') as risk_level,
           CASE WHEN aa.user_id IS NOT NULL THEN 1 ELSE 0 END as has_active_alert,
           act.status as explicit_status
    FROM users u
    LEFT JOIN LatestLogs l ON (
        CAST(u.unique_id AS TEXT) = CAST(l.user_id AS TEXT) 
        OR (u.unique_id GLOB '[0-9]*' AND l.user_id GLOB '[0-9]*' AND CAST(u.unique_id AS INTEGER) = CAST(l.user_id AS INTEGER))
        OR CAST(u.id AS TEXT) = CAST(l.user_id AS TEXT)
    )
    LEFT JOIN ActiveAlerts aa ON (
        CAST(u.unique_id AS TEXT) = CAST(aa.user_id AS TEXT) 
        OR (u.unique_id GLOB '[0-9]*' AND aa.user_id GLOB '[0-9]*' AND CAST(u.unique_id AS INTEGER) = CAST(aa.user_id AS INTEGER))
        OR CAST(u.id AS TEXT) = CAST(aa.user_id AS TEXT)
    )
    LEFT JOIN LatestActions act ON (
        CAST(u.unique_id AS TEXT) = CAST(act.mother_id AS TEXT)
        OR (u.unique_id GLOB '[0-9]*' AND act.mother_id GLOB '[0-9]*' AND CAST(u.unique_id AS INTEGER) = CAST(act.mother_id AS INTEGER))
    )
    WHERE u.role = 'Mother'
    """)
    rows = c.fetchall()
    conn.close()
    
    total = len(rows)
    high = 0
    med = 0
    safe = 0
    pending = 0
    in_prog = 0
    referred = 0
    followup = 0
    resolved = 0
    
    for r in rows:
        uid, score, r_level, has_alert, exp_status = r
        
        # Risk classification
        if score >= 60 or r_level == "High" or has_alert:
            high += 1
        elif score >= 30 or r_level == "Medium":
            med += 1
        else:
            safe += 1
            
        # Status classification
        if exp_status:
            st_clean = exp_status.lower()
            if "referred" in st_clean:
                referred += 1
            elif "follow" in st_clean:
                followup += 1
            elif "progress" in st_clean:
                in_prog += 1
            elif "resolved" in st_clean:
                resolved += 1
            elif "pending" in st_clean:
                pending += 1
            elif "high" in st_clean:
                if has_alert:
                    pending += 1
                else:
                    in_prog += 1
            else:
                pending += 1
        else:
            if has_alert or score >= 60:
                pending += 1
            elif score >= 30:
                in_prog += 1
            else:
                resolved += 1
                
    return {
        "total_cases": total,
        "high_risk": high,
        "medium_risk": med,
        "safe": safe,
        "pending": pending,
        "in_progress": in_prog,
        "referred": referred,
        "followup": followup,
        "resolved": resolved
    }

def get_asha_workload_breakdown():
    """
    Computes live per-ASHA / per-village performance metrics for Supervisor 'ASHA Worker Tracking'.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
    WITH LatestLogs AS (
        SELECT user_id, risk_score, risk_level
        FROM daily_logs
        WHERE id IN (SELECT MAX(id) FROM daily_logs GROUP BY user_id)
    ),
    ActiveAlerts AS (
        SELECT user_id FROM alerts WHERE status = 'Active' GROUP BY user_id
    ),
    LatestActions AS (
        SELECT mother_id, status, action_taken
        FROM case_actions
        WHERE id IN (SELECT MAX(id) FROM case_actions GROUP BY mother_id)
    )
    SELECT u.village,
           u.unique_id,
           COALESCE(l.risk_score, 0) as risk_score,
           COALESCE(l.risk_level, 'Low') as risk_level,
           CASE WHEN aa.user_id IS NOT NULL THEN 1 ELSE 0 END as has_active_alert,
           act.status as explicit_status
    FROM users u
    LEFT JOIN LatestLogs l ON (
        CAST(u.unique_id AS TEXT) = CAST(l.user_id AS TEXT) 
        OR (u.unique_id GLOB '[0-9]*' AND l.user_id GLOB '[0-9]*' AND CAST(u.unique_id AS INTEGER) = CAST(l.user_id AS INTEGER))
        OR CAST(u.id AS TEXT) = CAST(l.user_id AS TEXT)
    )
    LEFT JOIN ActiveAlerts aa ON (
        CAST(u.unique_id AS TEXT) = CAST(aa.user_id AS TEXT) 
        OR (u.unique_id GLOB '[0-9]*' AND aa.user_id GLOB '[0-9]*' AND CAST(u.unique_id AS INTEGER) = CAST(aa.user_id AS INTEGER))
        OR CAST(u.id AS TEXT) = CAST(aa.user_id AS TEXT)
    )
    LEFT JOIN LatestActions act ON (
        CAST(u.unique_id AS TEXT) = CAST(act.mother_id AS TEXT)
        OR (u.unique_id GLOB '[0-9]*' AND act.mother_id GLOB '[0-9]*' AND CAST(u.unique_id AS INTEGER) = CAST(act.mother_id AS INTEGER))
    )
    WHERE u.role = 'Mother' AND u.village IS NOT NULL AND u.village != ''
    """)
    rows = c.fetchall()
    conn.close()
    
    village_map = {}
    for r in rows:
        v_name, uid, score, r_level, has_alert, exp_status = r
        if v_name not in village_map:
            village_map[v_name] = {
                "Village": v_name,
                "ASHA Worker": f"ASHA ({v_name})",
                "Total Cases": 0,
                "High Risk": 0,
                "Medium Risk": 0,
                "Safe Cases": 0,
                "Pending": 0,
                "In Progress": 0,
                "Referred": 0,
                "Resolved": 0
            }
        vm = village_map[v_name]
        vm["Total Cases"] += 1
        
        if score >= 60 or r_level == "High" or has_alert:
            vm["High Risk"] += 1
        elif score >= 30 or r_level == "Medium":
            vm["Medium Risk"] += 1
        else:
            vm["Safe Cases"] += 1
            
        if exp_status:
            st_clean = exp_status.lower()
            if "referred" in st_clean:
                vm["Referred"] += 1
            elif "progress" in st_clean:
                vm["In Progress"] += 1
            elif "resolved" in st_clean:
                vm["Resolved"] += 1
            else:
                vm["Pending"] += 1
        else:
            if has_alert or score >= 60:
                vm["Pending"] += 1
            elif score >= 30:
                vm["In Progress"] += 1
            else:
                vm["Resolved"] += 1
                
    return list(village_map.values())

def get_all_patient_cases_for_supervisor():
    """
    Returns full patient directory with complete risk, symptom, ASHA action, and status details.
    """
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
    WITH LatestLogs AS (
        SELECT user_id, symptoms, mood, nutrition, risk_score, risk_level, date
        FROM daily_logs
        WHERE id IN (SELECT MAX(id) FROM daily_logs GROUP BY user_id)
    ),
    ActiveAlerts AS (
        SELECT user_id, status FROM alerts WHERE status = 'Active' GROUP BY user_id
    ),
    LatestActions AS (
        SELECT mother_id, asha_id, status, action_taken, notes, followup_date, timestamp
        FROM case_actions
        WHERE id IN (SELECT MAX(id) FROM case_actions GROUP BY mother_id)
    )
    SELECT u.unique_id, u.name, u.village, u.phone,
           COALESCE(l.risk_score, 10) as risk_score,
           COALESCE(l.risk_level, 'Low') as risk_level,
           COALESCE(l.symptoms, 'None') as symptoms,
           COALESCE(l.mood, 'Normal') as mood,
           COALESCE(l.nutrition, 'Good') as nutrition,
           COALESCE(act.asha_id, 'ASHA (' || u.village || ')') as asha_assigned,
           COALESCE(act.action_taken, CASE WHEN aa.user_id IS NOT NULL THEN 'Alert Active - Pending ASHA Visit' ELSE 'Routine Monitoring' END) as action_taken,
           COALESCE(act.status, CASE WHEN aa.user_id IS NOT NULL THEN 'High Risk' WHEN l.risk_score >= 60 THEN 'Pending' ELSE 'Resolved' END) as current_status,
           COALESCE(act.notes, '') as notes,
           COALESCE(act.followup_date, '') as followup_date,
           COALESCE(act.timestamp, l.date, 'Initial Baseline') as last_updated
    FROM users u
    LEFT JOIN LatestLogs l ON (
        CAST(u.unique_id AS TEXT) = CAST(l.user_id AS TEXT) 
        OR (u.unique_id GLOB '[0-9]*' AND l.user_id GLOB '[0-9]*' AND CAST(u.unique_id AS INTEGER) = CAST(l.user_id AS INTEGER))
        OR CAST(u.id AS TEXT) = CAST(l.user_id AS TEXT)
    )
    LEFT JOIN ActiveAlerts aa ON (
        CAST(u.unique_id AS TEXT) = CAST(aa.user_id AS TEXT) 
        OR (u.unique_id GLOB '[0-9]*' AND aa.user_id GLOB '[0-9]*' AND CAST(u.unique_id AS INTEGER) = CAST(aa.user_id AS INTEGER))
        OR CAST(u.id AS TEXT) = CAST(aa.user_id AS TEXT)
    )
    LEFT JOIN LatestActions act ON (
        CAST(u.unique_id AS TEXT) = CAST(act.mother_id AS TEXT)
        OR (u.unique_id GLOB '[0-9]*' AND act.mother_id GLOB '[0-9]*' AND CAST(u.unique_id AS INTEGER) = CAST(act.mother_id AS INTEGER))
    )
    WHERE u.role = 'Mother'
    ORDER BY l.risk_score DESC, u.id ASC
    """)
    cases = c.fetchall()
    conn.close()
    
    case_list = []
    for row in cases:
        case_list.append({
            "Mother ID": row[0],
            "Name": row[1],
            "Village": row[2],
            "Phone": row[3],
            "Risk Score": row[4],
            "Risk Level": row[5],
            "Symptoms": row[6],
            "Mood": row[7],
            "Nutrition": row[8],
            "ASHA Assigned": row[9],
            "Action Taken": row[10],
            "Status": row[11],
            "Notes": row[12],
            "Follow-up Date": row[13],
            "Last Updated": row[14]
        })
    return case_list
