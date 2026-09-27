import sqlite3

_db_initialized = False

def get_connection():
    """Returns a fast SQLite connection configured with WAL journal mode and memory caching."""
    conn = sqlite3.connect("maatrisuraksha.db", check_same_thread=False, timeout=10.0)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA cache_size = 10000;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    return conn

# ---------------- INITIALIZE DATABASE ----------------
def init_db():
    global _db_initialized
    if _db_initialized:
        return
    conn = get_connection()
    c = conn.cursor()

    # Users Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        unique_id TEXT UNIQUE,
        name TEXT,
        role TEXT,
        phone TEXT,
        village TEXT,
        latitude REAL,
        longitude REAL
    )
    """)

    # Migration for existing database
    try:
        c.execute("ALTER TABLE users ADD COLUMN unique_id TEXT UNIQUE")
    except sqlite3.OperationalError:
        pass
    try:
        c.execute("ALTER TABLE users ADD COLUMN latitude REAL")
        c.execute("ALTER TABLE users ADD COLUMN longitude REAL")
    except sqlite3.OperationalError:
        pass

    # Daily Logs Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS daily_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        symptoms TEXT,
        mood TEXT,
        nutrition TEXT,
        risk_score INTEGER,
        risk_level TEXT,
        date TEXT
    )
    """)

    # Alerts Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        risk_level TEXT,
        status TEXT,
        timestamp TEXT
    )
    """)

    # Mock SMS Logs Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS mock_sms_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mother_id TEXT,
        message TEXT,
        status TEXT,
        timestamp TEXT
    )
    """)

    # Live SMS Logs Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS sms_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mother_id TEXT,
        asha_phone TEXT,
        message TEXT,
        api_status TEXT,
        timestamp TEXT
    )
    """)
    # Call Logs Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS call_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mother_id TEXT,
        asha_phone TEXT,
        call_sid TEXT,
        status TEXT,
        timestamp TEXT
    )
    """)

    # Offline Sync Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS offline_sync (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        feature TEXT,
        payload TEXT,
        timestamp TEXT
    )
    """)

    # Baby Profiles Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS baby_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mother_id TEXT UNIQUE,
        delivery_date TEXT,
        baby_gender TEXT,
        created_at TEXT
    )
    """)

    # Baby Health Logs Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS baby_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mother_id TEXT,
        fever TEXT,
        cough TEXT,
        weight REAL,
        feeding_pattern TEXT,
        sleep_hours REAL,
        date TEXT
    )
    """)

    # Vaccinations Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS vaccinations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mother_id TEXT,
        vaccine_name TEXT,
        due_date TEXT,
        status TEXT,
        completed_date TEXT
    )
    """)

    # Exercise Logs Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS exercise_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mother_id TEXT,
        exercise_type TEXT,
        timestamp TEXT
    )
    """)

    # Case Actions & Workflow Status Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS case_actions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        mother_id TEXT,
        asha_id TEXT,
        status TEXT,
        action_taken TEXT,
        notes TEXT,
        followup_date TEXT,
        timestamp TEXT
    )
    """)

    # Community Health Screenings Table (for General Village Community Healthcare)
    c.execute("""
    CREATE TABLE IF NOT EXISTS community_screenings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_name TEXT,
        age INTEGER,
        gender TEXT,
        village TEXT,
        existing_conditions TEXT,
        current_medications TEXT,
        family_history TEXT,
        bp_systolic INTEGER,
        bp_diastolic INTEGER,
        blood_glucose REAL,
        glucose_type TEXT,
        spo2 REAL,
        temperature REAL,
        pulse INTEGER,
        weight REAL,
        height REAL,
        bmi REAL,
        screened_conditions TEXT,
        symptoms_json TEXT,
        overall_risk TEXT,
        condition_results_json TEXT,
        recommended_action TEXT,
        facility_referred TEXT,
        sync_status TEXT,
        followup_status TEXT,
        timestamp TEXT
    )
    """)

    # Community Doctor Consultations & Tele-Visits Table
    c.execute("""
    CREATE TABLE IF NOT EXISTS community_consultations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        patient_name TEXT,
        village TEXT,
        doctor_name TEXT,
        doctor_role TEXT,
        doctor_center TEXT,
        problem TEXT,
        advice_summary TEXT,
        medicines_json TEXT,
        facility_referred TEXT,
        referral_reason TEXT,
        referral_status TEXT,
        followup_date TEXT,
        followup_action TEXT,
        followup_status TEXT,
        sync_status TEXT,
        timestamp TEXT
    )
    """)

    # Performance indices to ensure instant query execution
    try:
        c.execute("CREATE INDEX IF NOT EXISTS idx_users_uid ON users(unique_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_daily_logs_uid ON daily_logs(user_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_alerts_uid ON alerts(user_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_baby_logs_mid ON baby_logs(mother_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_vax_mid ON vaccinations(mother_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_ex_mid ON exercise_logs(mother_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_case_actions_mid ON case_actions(mother_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_comm_scr_v ON community_screenings(village);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_comm_scr_r ON community_screenings(overall_risk);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_comm_con_v ON community_consultations(village);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_comm_con_p ON community_consultations(patient_name);")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()
    _db_initialized = True

    # Auto-seed initial demo records if table is fresh
    try:
        seed_community_screening_demo_data()
    except Exception:
        pass

    try:
        seed_community_consultations_demo_data()
    except Exception:
        pass

# ---------------- REGISTER MOTHER ----------------
def register_mother(unique_id, name, phone, village):
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute("""
        INSERT INTO users (unique_id, name, role, phone, village)
        VALUES (?, ?, 'Mother', ?, ?)
        """, (unique_id, name, phone, village))
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        # unique_id already exists
        success = False
    conn.close()
    return success

# ---------------- VERIFY MOTHER LOGIN ----------------
def verify_mother(unique_id, name):
    conn = get_connection()
    c = conn.cursor()
    # verify unique_id and name
    c.execute("SELECT * FROM users WHERE role='Mother' AND unique_id=? COLLATE NOCASE AND name=? COLLATE NOCASE", (unique_id, name))
    user = c.fetchone()
    conn.close()
    return user is not None

# ---------------- GET ALL MOTHERS ----------------
def get_all_mothers():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT unique_id, name, phone, village, latitude, longitude FROM users WHERE role='Mother'")
    mothers = c.fetchall()
    conn.close()
    return mothers

# ---------------- GET ASHA PHONE ----------------
def get_asha_phone(village):
    """Retrieve an ASHA worker's phone number."""
    return os.environ.get("ASHA_WORKER_PHONE", "7075287040")


# ---------------- UPDATE LOCATION ----------------
def update_location(unique_id, lat, lon):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
    UPDATE users SET latitude=?, longitude=? WHERE unique_id=?
    """, (lat, lon, unique_id))
    conn.commit()
    conn.close()


# ---------------- GET MOTHERS WITH RISK AND LOCATION ----------------
def get_mothers_with_risk_and_location():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
    WITH LatestLogs AS (
        SELECT user_id, risk_level, risk_score, date
        FROM daily_logs
        WHERE id IN (
            SELECT MAX(id)
            FROM daily_logs
            GROUP BY user_id
        )
    )
    SELECT u.unique_id, u.name, u.village, u.latitude, u.longitude,
           l.risk_level, l.risk_score, l.date
    FROM users u
    LEFT JOIN LatestLogs l ON u.unique_id = l.user_id
    WHERE u.role='Mother'
    """)
    data = c.fetchall()
    conn.close()
    return data


# ---------------- SAVE DAILY LOG ----------------
def save_daily_log(user_id, symptoms, mood, nutrition, risk_score, risk_level, date):
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
    INSERT INTO daily_logs (user_id, symptoms, mood, nutrition, risk_score, risk_level, date)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, ",".join(symptoms), mood, nutrition, risk_score, risk_level, date))

    conn.commit()
    conn.close()


# ---------------- CREATE ALERT ----------------
def create_alert(user_id, risk_level, timestamp):
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
    INSERT INTO alerts (user_id, risk_level, status, timestamp)
    VALUES (?, ?, ?, ?)
    """, (user_id, risk_level, "Active", timestamp))

    conn.commit()
    conn.close()

# ---------------- MOCK SMS OPERATIONS ----------------
def log_mock_sms(mother_id, message, timestamp):
    """Log the simulated SMS to the database to prevent duplicates and keep audit records."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
    INSERT INTO mock_sms_logs (mother_id, message, status, timestamp)
    VALUES (?, ?, ?, ?)
    """, (mother_id, message, "Sent", timestamp))
    conn.commit()
    conn.close()

# ---------------- LIVE SMS OPERATIONS ----------------
def log_live_sms(mother_id, asha_phone, message, api_status, timestamp):
    """Log the live SMS API attempt, saving both successes and HTTP failure codes."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
    INSERT INTO sms_logs (mother_id, asha_phone, message, api_status, timestamp)
    VALUES (?, ?, ?, ?, ?)
    """, (mother_id, asha_phone, message, api_status, timestamp))
    conn.commit()
    conn.close()

def log_live_call(mother_id, asha_phone, call_sid, status, timestamp):
    """Log the live automated call attempt."""
    conn = sqlite3.connect("maatrisuraksha.db")
    c = conn.cursor()
    c.execute("""
    INSERT INTO call_logs (mother_id, asha_phone, call_sid, status, timestamp)
    VALUES (?, ?, ?, ?, ?)
    """, (mother_id, asha_phone, call_sid, status, timestamp))
    conn.commit()
    conn.close()

def has_recent_high_risk_sms(mother_id):
    """Check if a High Risk SMS was already sent recently (within last 12 hours) to avoid spam."""
    import datetime
    conn = get_connection()
    c = conn.cursor()
    
    # Check both live and mock logs to be thorough during transition
    c.execute("""
    SELECT timestamp FROM (
        SELECT timestamp FROM mock_sms_logs WHERE mother_id = ? AND status = 'Sent'
        UNION ALL
        SELECT timestamp FROM sms_logs WHERE mother_id = ? AND (api_status = 'Sent' OR api_status LIKE 'Success%')
    ) 
    ORDER BY timestamp DESC LIMIT 1
    """, (mother_id, mother_id))
    
    row = c.fetchone()
    conn.close()
    
    if row:
        last_time_str = row[0]
        try:
            last_time = datetime.datetime.strptime(last_time_str, "%Y-%m-%d %H:%M:%S")
            now = datetime.datetime.now()
            diff = now - last_time
            # If the last SMS was less than 12 hours ago, return True (prevent new SMS)
            if diff.total_seconds() < (12 * 3600):
                return True
        except Exception:
            # If timestamp parsing fails, play it safe and maybe don't block
            pass
            
    return False
# ---------------- GET ALL LOGS ----------------
def get_all_logs():
    import sqlite3
    conn = get_connection()
    c = conn.cursor()

    c.execute("SELECT * FROM daily_logs ORDER BY date DESC")
    rows = c.fetchall()

    conn.close()
    return rows

# ---------------- OFFLINE SYNC OPERATIONS ----------------
def save_offline_record(user_id, feature, payload):
    import datetime
    conn = get_connection()
    c = conn.cursor()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
    INSERT INTO offline_sync (user_id, feature, payload, timestamp)
    VALUES (?, ?, ?, ?)
    """, (user_id, feature, payload, timestamp))
    conn.commit()
    conn.close()

def get_pending_sync_records():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM offline_sync")
    records = c.fetchall()
    conn.close()
    return records

def delete_sync_record(record_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM offline_sync WHERE id = ?", (record_id,))
    conn.commit()
    conn.close()


# ---------------- CASE ACTIONS & STATUS MANAGEMENT ----------------
def update_case_status(mother_id, asha_id="ASHA-101", status="In Progress", action_taken="Clinical Review", notes="", followup_date=""):
    """
    Records an action taken by ASHA worker / healthcare provider and updates the case workflow status.
    Statuses: 'New', 'High Risk', 'Pending', 'In Progress', 'Referred to PHC', 'Urgent Referral', 'Follow-up Required', 'Resolved'
    """
    import datetime
    conn = get_connection()
    c = conn.cursor()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
    INSERT INTO case_actions (mother_id, asha_id, status, action_taken, notes, followup_date, timestamp)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (str(mother_id), str(asha_id), status, action_taken, notes, followup_date, timestamp))
    
    # If the case is marked Resolved, also update any active alerts in alerts table
    if status == "Resolved":
        c.execute("UPDATE alerts SET status = 'Resolved' WHERE (user_id = ? OR CAST(user_id AS TEXT) = ?) AND status = 'Active'", (mother_id, str(mother_id)))
        
    conn.commit()
    conn.close()
    return True

def get_case_status(mother_id):
    """
    Returns the latest case action status for a mother.
    If no explicit action taken yet, deduces status from active alerts and latest risk score.
    """
    conn = get_connection()
    c = conn.cursor()
    # Check latest case action
    c.execute("""
    SELECT status, action_taken, notes, followup_date, timestamp, asha_id
    FROM case_actions
    WHERE mother_id = ? OR CAST(mother_id AS TEXT) = ?
    ORDER BY id DESC LIMIT 1
    """, (mother_id, str(mother_id)))
    row = c.fetchone()
    
    if row:
        conn.close()
        return {
            "status": row[0],
            "action_taken": row[1],
            "notes": row[2],
            "followup_date": row[3],
            "timestamp": row[4],
            "asha_id": row[5]
        }
        
    # If no explicit case action exists, check active alerts / risk
    c.execute("""
    SELECT risk_level, status FROM alerts 
    WHERE (user_id = ? OR CAST(user_id AS TEXT) = ?) AND status = 'Active' 
    ORDER BY id DESC LIMIT 1
    """, (mother_id, str(mother_id)))
    alert = c.fetchone()
    
    if alert:
        conn.close()
        return {
            "status": "High Risk" if alert[0] == "High" else "Pending",
            "action_taken": "Pending ASHA Review",
            "notes": "Alert triggered. Immediate field evaluation recommended.",
            "followup_date": "",
            "timestamp": "",
            "asha_id": "ASHA-101"
        }
        
    # Check latest log
    c.execute("""
    SELECT risk_level, risk_score, date FROM daily_logs 
    WHERE (user_id = ? OR CAST(user_id AS TEXT) = ?)
    ORDER BY id DESC LIMIT 1
    """, (mother_id, str(mother_id)))
    log = c.fetchone()
    conn.close()
    
    if log:
        r_level = log[0] or "Low"
        if r_level == "High":
            st_val = "High Risk"
        elif r_level == "Medium":
            st_val = "Pending"
        else:
            st_val = "Resolved"
        return {
            "status": st_val,
            "action_taken": "Routine Monitoring",
            "notes": "Healthy pregnancy baseline.",
            "followup_date": "",
            "timestamp": log[2] if len(log) > 2 else "",
            "asha_id": "ASHA-101"
        }
        
    return {
        "status": "New",
        "action_taken": "Registered",
        "notes": "Awaiting initial ANC check-in.",
        "followup_date": "",
        "timestamp": "",
        "asha_id": "ASHA-101"
    }

def get_all_case_statuses():
    """Returns a dictionary mapping mother_id -> latest case action details."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
    SELECT mother_id, status, action_taken, notes, followup_date, timestamp, asha_id
    FROM case_actions
    WHERE id IN (
        SELECT MAX(id) FROM case_actions GROUP BY mother_id
    )
    """)
    rows = c.fetchall()
    conn.close()
    
    status_map = {}
    for r in rows:
        status_map[str(r[0])] = {
            "status": r[1],
            "action_taken": r[2],
            "notes": r[3],
            "followup_date": r[4],
            "timestamp": r[5],
            "asha_id": r[6]
        }
    return status_map

def get_case_history(mother_id):
    """Returns complete chronological audit history of actions taken on this mother."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
    SELECT id, asha_id, status, action_taken, notes, followup_date, timestamp
    FROM case_actions
    WHERE mother_id = ? OR CAST(mother_id AS TEXT) = ?
    ORDER BY timestamp DESC, id DESC
    """, (mother_id, str(mother_id)))
    rows = c.fetchall()
    conn.close()
    return rows

# ---------------- RESOLVE ALERT ----------------
def resolve_alert(mother_id, asha_id="ASHA-101", notes="Case reviewed and resolved."):
    """Mark all active alerts for a specific mother as Resolved and update case action."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE alerts SET status = 'Resolved' WHERE (user_id = ? OR CAST(user_id AS TEXT) = ?) AND status = 'Active'", (mother_id, str(mother_id)))
    conn.commit()
    conn.close()
    
    # Also log to case actions
    update_case_status(mother_id, asha_id=asha_id, status="Resolved", action_taken="Alert Resolved", notes=notes)

# ---------------- GET ACTIVE ALERTS ----------------
def get_active_alerts():
    import sqlite3
    conn = get_connection()
    c = conn.cursor()

    c.execute("SELECT * FROM alerts WHERE status='Active'")
    rows = c.fetchall()

    conn.close()
    return rows

# ---------------- BABY CARE OPERATIONS ----------------
def register_baby(mother_id, delivery_date, gender):
    import datetime
    conn = get_connection()
    c = conn.cursor()
    created_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        c.execute("""
        INSERT INTO baby_profiles (mother_id, delivery_date, baby_gender, created_at)
        VALUES (?, ?, ?, ?)
        """, (mother_id, delivery_date, gender, created_at))
        
        # Auto-populate initial vaccination schedule
        vaccines = [
            ("BCG, OPV", 0), # Birth
            ("DPT, Hepatitis B", 42), # 6 weeks (approx 42 days)
            ("DPT", 70), # 10 weeks
            ("DPT", 98), # 14 weeks
            ("Measles", 270) # 9 months
        ]
        
        delivery_dt = datetime.datetime.strptime(delivery_date, "%Y-%m-%d")
        for v_name, days_after in vaccines:
            due_dt = delivery_dt + datetime.timedelta(days=days_after)
            c.execute("""
            INSERT INTO vaccinations (mother_id, vaccine_name, due_date, status)
            VALUES (?, ?, ?, ?)
            """, (mother_id, v_name, due_dt.strftime("%Y-%m-%d"), 'Pending'))
            
        conn.commit()
        success = True
    except sqlite3.IntegrityError:
        # Profile already exists
        success = False
    conn.close()
    return success

def get_baby_profile(mother_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM baby_profiles WHERE mother_id=?", (mother_id,))
    profile = c.fetchone()
    conn.close()
    return profile

def get_baby_vaccinations(mother_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT * FROM vaccinations WHERE mother_id=? ORDER BY due_date ASC", (mother_id,))
    vaccines = c.fetchall()
    conn.close()
    return vaccines

def save_baby_log(mother_id, fever, cough, weight, feeding, sleep):
    import datetime
    conn = get_connection()
    c = conn.cursor()
    date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
    INSERT INTO baby_logs (mother_id, fever, cough, weight, feeding_pattern, sleep_hours, date)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (mother_id, fever, cough, weight, feeding, sleep, date))
    conn.commit()
    conn.close()

def get_baby_logs(mother_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT weight, feeding_pattern, sleep_hours, date FROM baby_logs WHERE mother_id=? ORDER BY date ASC", (mother_id,))
    logs = c.fetchall()
    conn.close()
    return logs


def get_all_babies():
    """For ASHA worker dashboard"""
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
    SELECT u.unique_id, u.name, u.village, b.delivery_date
    FROM users u
    JOIN baby_profiles b ON u.unique_id = b.mother_id
    WHERE u.role='Mother'
    """)
    babies = c.fetchall()
    conn.close()
    return babies

# Expose Village Health Intelligence Queries
from database_village_health import (
    get_maternal_risk_distribution,
    get_village_risk_aggregations,
    get_vaccination_coverage,
    get_high_risk_mothers_alert,
    get_baby_health_alerts,
    get_upcoming_vaccinations,
    generate_asha_daily_tasks,
    get_supervisor_metrics,
    get_asha_workload_breakdown,
    get_all_patient_cases_for_supervisor
)

# ---------------- PREGNANCY EXERCISE COACH OPERATIONS ----------------
def log_exercise(mother_id, exercise_type):
    import datetime
    conn = get_connection()
    c = conn.cursor()
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("""
    INSERT INTO exercise_logs (mother_id, exercise_type, timestamp)
    VALUES (?, ?, ?)
    """, (mother_id, exercise_type, timestamp))
    conn.commit()
    conn.close()

def get_mother_exercise_logs(mother_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
    SELECT exercise_type, timestamp 
    FROM exercise_logs 
    WHERE mother_id=? 
    ORDER BY timestamp DESC
    """, (mother_id,))
    logs = c.fetchall()
    conn.close()
    return logs

def get_latest_exercise_log_for_all_mothers():
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
    SELECT e.mother_id, u.name, e.exercise_type, e.timestamp
    FROM exercise_logs e
    JOIN users u ON e.mother_id = u.unique_id
    WHERE e.id IN (
        SELECT MAX(id)
        FROM exercise_logs
        GROUP BY mother_id
    )
    ORDER BY e.timestamp DESC
    """)
    logs = c.fetchall()
    conn.close()
    return logs


# ---------------- COMMUNITY HEALTH SCREENING (GENERAL ADULT/GERIATRIC/COMMUNITY) ----------------
def save_community_screening(record: dict) -> int:
    """Save a community health screening record to the database."""
    import datetime, json
    conn = get_connection()
    c = conn.cursor()
    
    timestamp = record.get("timestamp") or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    symptoms_json = json.dumps(record.get("symptoms", []), ensure_ascii=False) if isinstance(record.get("symptoms"), (list, dict)) else str(record.get("symptoms", ""))
    condition_results_json = json.dumps(record.get("condition_results", {}), ensure_ascii=False) if isinstance(record.get("condition_results"), (list, dict)) else str(record.get("condition_results", ""))
    screened_conditions = json.dumps(record.get("screened_conditions", []), ensure_ascii=False) if isinstance(record.get("screened_conditions"), list) else str(record.get("screened_conditions", ""))

    c.execute("""
    INSERT INTO community_screenings (
        patient_name, age, gender, village, existing_conditions, current_medications,
        family_history, bp_systolic, bp_diastolic, blood_glucose, glucose_type,
        spo2, temperature, pulse, weight, height, bmi, screened_conditions,
        symptoms_json, overall_risk, condition_results_json, recommended_action,
        facility_referred, sync_status, followup_status, timestamp
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        record.get("patient_name", "Anonymous"),
        record.get("age"),
        record.get("gender", "Other"),
        record.get("village", "General Community"),
        record.get("existing_conditions", "None"),
        record.get("current_medications", "None"),
        record.get("family_history", "None"),
        record.get("bp_systolic"),
        record.get("bp_diastolic"),
        record.get("blood_glucose"),
        record.get("glucose_type", "Random"),
        record.get("spo2"),
        record.get("temperature"),
        record.get("pulse"),
        record.get("weight"),
        record.get("height"),
        record.get("bmi"),
        screened_conditions,
        symptoms_json,
        record.get("overall_risk", "Low Risk"),
        condition_results_json,
        record.get("recommended_action", "Routine monitoring"),
        record.get("facility_referred", ""),
        record.get("sync_status", "Synced"),
        record.get("followup_status", "Pending"),
        timestamp
    ))
    row_id = c.lastrowid
    conn.commit()
    conn.close()
    return row_id

def get_community_screenings(village: str = None, limit: int = 50):
    """Retrieve recent community health screenings, optionally filtered by village."""
    conn = get_connection()
    c = conn.cursor()
    if village and village != "All Villages":
        c.execute("""
        SELECT id, patient_name, age, gender, village, overall_risk, 
               recommended_action, facility_referred, sync_status, followup_status, 
               timestamp, condition_results_json, bp_systolic, bp_diastolic, blood_glucose, bmi
        FROM community_screenings
        WHERE village = ?
        ORDER BY id DESC
        LIMIT ?
        """, (village, limit))
    else:
        c.execute("""
        SELECT id, patient_name, age, gender, village, overall_risk, 
               recommended_action, facility_referred, sync_status, followup_status, 
               timestamp, condition_results_json, bp_systolic, bp_diastolic, blood_glucose, bmi
        FROM community_screenings
        ORDER BY id DESC
        LIMIT ?
        """, (limit,))
    rows = c.fetchall()
    conn.close()
    
    results = []
    for r in rows:
        results.append({
            "id": r[0],
            "patient_name": r[1],
            "age": r[2],
            "gender": r[3],
            "village": r[4],
            "overall_risk": r[5],
            "recommended_action": r[6],
            "facility_referred": r[7],
            "sync_status": r[8],
            "followup_status": r[9],
            "timestamp": r[10],
            "condition_results_json": r[11],
            "bp_systolic": r[12],
            "bp_diastolic": r[13],
            "blood_glucose": r[14],
            "bmi": r[15]
        })
    return results

def get_community_screening_stats(village: str = None):
    """Calculate aggregated community health statistics for overview cards."""
    import json
    conn = get_connection()
    c = conn.cursor()
    
    where_clause = ""
    params = ()
    if village and village != "All Villages":
        where_clause = "WHERE village = ?"
        params = (village,)
        
    c.execute(f"SELECT COUNT(*) FROM community_screenings {where_clause}", params)
    total_screened = c.fetchone()[0] or 0
    
    c.execute(f"SELECT COUNT(*) FROM community_screenings {where_clause} {'AND' if where_clause else 'WHERE'} overall_risk = 'Needs Medical Review'", params)
    needs_review = c.fetchone()[0] or 0
    
    c.execute(f"SELECT COUNT(*) FROM community_screenings {where_clause} {'AND' if where_clause else 'WHERE'} overall_risk = 'Urgent'", params)
    urgent_cases = c.fetchone()[0] or 0
    
    c.execute(f"SELECT COUNT(*) FROM community_screenings {where_clause} {'AND' if where_clause else 'WHERE'} overall_risk = 'Low Risk'", params)
    low_risk = c.fetchone()[0] or 0
    
    c.execute(f"SELECT COUNT(*) FROM community_screenings {where_clause} {'AND' if where_clause else 'WHERE'} followup_status = 'Pending'", params)
    pending_followups = c.fetchone()[0] or 0

    # Risk breakdown by condition
    risk_counts = {
        "Hypertension": 0,
        "Diabetes": 0,
        "Anemia": 0,
        "Respiratory Problems": 0,
        "Musculoskeletal Problems": 0,
        "Heart Health": 0,
        "Cancer Warning Signs": 0,
        "Mental Health": 0,
        "Eye Health": 0,
        "Elderly Health": 0
    }
    
    c.execute(f"SELECT condition_results_json FROM community_screenings {where_clause}", params)
    rows = c.fetchall()
    conn.close()
    
    for row in rows:
        if row[0]:
            try:
                res_dict = json.loads(row[0])
                if isinstance(res_dict, dict):
                    for cond, info in res_dict.items():
                        status = info.get("status") if isinstance(info, dict) else str(info)
                        if status in ["Needs Medical Review", "Urgent", "Needs Review"]:
                            if "Hypertension" in cond or "Blood Pressure" in cond:
                                risk_counts["Hypertension"] += 1
                            elif "Diabetes" in cond or "Blood Sugar" in cond:
                                risk_counts["Diabetes"] += 1
                            elif "Anemia" in cond:
                                risk_counts["Anemia"] += 1
                            elif "Respiratory" in cond:
                                risk_counts["Respiratory Problems"] += 1
                            elif "Musculoskeletal" in cond or "Joint" in cond or "Back" in cond:
                                risk_counts["Musculoskeletal Problems"] += 1
                            elif "Heart" in cond or "Cardio" in cond:
                                risk_counts["Heart Health"] += 1
                            elif "Cancer" in cond:
                                risk_counts["Cancer Warning Signs"] += 1
                            elif "Mental" in cond:
                                risk_counts["Mental Health"] += 1
                            elif "Eye" in cond:
                                risk_counts["Eye Health"] += 1
                            elif "Elderly" in cond or "Geriatric" in cond:
                                risk_counts["Elderly Health"] += 1
            except Exception:
                pass
                
    return {
        "people_screened": total_screened,
        "needs_review": needs_review,
        "urgent_cases": urgent_cases,
        "low_risk": low_risk,
        "pending_followups": pending_followups,
        "risk_breakdown": risk_counts
    }

def update_screening_followup(screening_id: int, followup_status: str, facility_referred: str = None, notes: str = None):
    """Update follow-up and facility referral for a community screening."""
    conn = get_connection()
    c = conn.cursor()
    if facility_referred:
        c.execute("""
        UPDATE community_screenings 
        SET followup_status = ?, facility_referred = ?
        WHERE id = ?
        """, (followup_status, facility_referred, screening_id))
    else:
        c.execute("""
        UPDATE community_screenings 
        SET followup_status = ?
        WHERE id = ?
        """, (followup_status, screening_id))
    conn.commit()
    conn.close()

def seed_community_screening_demo_data():
    """Populate realistic baseline community health screening records if none exist."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM community_screenings")
    count = c.fetchone()[0]
    conn.close()
    
    if count > 0:
        return
        
    demo_screenings = [
        {
            "patient_name": "Mohammad Ismail",
            "age": 58,
            "gender": "Male",
            "village": "Hyderabad (Old City)",
            "existing_conditions": "Hypertension",
            "current_medications": "Amlodipine 5mg",
            "family_history": "Heart Disease, High BP",
            "bp_systolic": 154,
            "bp_diastolic": 96,
            "blood_glucose": 168.0,
            "glucose_type": "Random",
            "spo2": 97.0,
            "temperature": 98.4,
            "pulse": 82,
            "weight": 74.0,
            "height": 168.0,
            "bmi": 26.2,
            "screened_conditions": ["Hypertension / High BP", "Diabetes / Blood Sugar", "Heart & Cardiovascular Risk"],
            "symptoms": ["Occasional dizziness", "Mild breathlessness on climbing stairs"],
            "overall_risk": "Needs Medical Review",
            "condition_results": {
                "Hypertension": {"status": "Needs Medical Review", "explanation": "Systolic BP 154 mmHg is elevated above normal threshold (140 mmHg)."},
                "Diabetes": {"status": "Needs Medical Review", "explanation": "Random blood glucose 168 mg/dL warrants formal fasting blood sugar evaluation at PHC."},
                "Heart & Cardiovascular": {"status": "Low Risk", "explanation": "No acute cardiac symptoms reported."}
            },
            "recommended_action": "Consult Primary Health Centre (PHC) for BP titration & fasting glucose check",
            "facility_referred": "Moinabad 24/7 Primary Health Centre (PHC)",
            "sync_status": "Synced",
            "followup_status": "Pending",
            "timestamp": "2026-09-25 10:15:00"
        },
        {
            "patient_name": "Fatima Begum",
            "age": 49,
            "gender": "Female",
            "village": "Hyderabad (Old City)",
            "existing_conditions": "None",
            "current_medications": "None",
            "family_history": "Diabetes",
            "bp_systolic": 132,
            "bp_diastolic": 84,
            "blood_glucose": 242.0,
            "glucose_type": "Fasting",
            "spo2": 98.0,
            "temperature": 98.6,
            "pulse": 76,
            "weight": 68.0,
            "height": 156.0,
            "bmi": 27.9,
            "screened_conditions": ["Diabetes / Blood Sugar", "Eye Health", "Kidney Health"],
            "symptoms": ["Excessive thirst", "Frequent urination at night", "Blurred vision"],
            "overall_risk": "Needs Medical Review",
            "condition_results": {
                "Diabetes": {"status": "Needs Medical Review", "explanation": "Fasting blood sugar 242 mg/dL with classic osmotic symptoms indicates need for physician evaluation."},
                "Eye Health": {"status": "Needs Medical Review", "explanation": "Blurred vision accompanied by elevated sugar warrants diabetic retinopathy screening."},
                "Kidney Health": {"status": "Low Risk", "explanation": "No flank pain or abnormal urinary discomfort reported."}
            },
            "recommended_action": "Consult PHC / CHC for diabetes confirmation and dietary counselling",
            "facility_referred": "Kondapur Community Health Centre & Maternity Wing",
            "sync_status": "Synced",
            "followup_status": "Pending",
            "timestamp": "2026-09-25 11:30:00"
        },
        {
            "patient_name": "Abdul Qadeer",
            "age": 67,
            "gender": "Male",
            "village": "Hyderabad (Old City)",
            "existing_conditions": "Heart condition, High BP",
            "current_medications": "Atenolol, Sorbitrate",
            "family_history": "Heart Disease, Stroke",
            "bp_systolic": 182,
            "bp_diastolic": 112,
            "blood_glucose": 140.0,
            "glucose_type": "Random",
            "spo2": 93.0,
            "temperature": 98.2,
            "pulse": 104,
            "weight": 62.0,
            "height": 165.0,
            "bmi": 22.8,
            "screened_conditions": ["Heart & Cardiovascular Risk", "Hypertension / High BP", "Respiratory Health"],
            "symptoms": ["Chest discomfort or tightness", "Severe breathlessness at rest", "Swelling in feet/ankles"],
            "overall_risk": "Urgent",
            "condition_results": {
                "Heart & Cardiovascular": {"status": "Urgent", "explanation": "Chest discomfort combined with resting breathlessness and peripheral swelling requires prompt emergency hospital evaluation."},
                "Hypertension": {"status": "Urgent", "explanation": "BP 182/112 mmHg represents Stage 2 Hypertensive Urgency."},
                "Respiratory": {"status": "Needs Medical Review", "explanation": "Shortness of breath likely secondary to cardiovascular congestion."}
            },
            "recommended_action": "Seek immediate emergency evaluation / Dial 108 Ambulance",
            "facility_referred": "Chevella Area Sub-District Hospital (CEmOC Apex)",
            "sync_status": "Synced",
            "followup_status": "Referred",
            "timestamp": "2026-09-26 09:10:00"
        },
        {
            "patient_name": "Kavitha Reddy",
            "age": 32,
            "gender": "Female",
            "village": "Hyderabad (Old City)",
            "existing_conditions": "None",
            "current_medications": "None",
            "family_history": "Anemia",
            "bp_systolic": 106,
            "bp_diastolic": 68,
            "blood_glucose": 94.0,
            "glucose_type": "Random",
            "spo2": 99.0,
            "temperature": 98.4,
            "pulse": 88,
            "weight": 46.0,
            "height": 154.0,
            "bmi": 19.4,
            "screened_conditions": ["Anemia & Nutritional Deficiencies", "Thyroid Disorders", "Mental Health & Well-being"],
            "symptoms": ["Chronic fatigue & weakness", "Extreme paleness of inner eyelids", "Frequent dizziness"],
            "overall_risk": "Needs Medical Review",
            "condition_results": {
                "Anemia & Nutrition": {"status": "Needs Medical Review", "explanation": "Physical signs of conjunctival pallor and persistent dizziness suggest possible clinical anemia."},
                "Thyroid": {"status": "Low Risk", "explanation": "No neck swelling or cold intolerance detected."},
                "Mental Health": {"status": "Low Risk", "explanation": "Fatigue appears primarily nutritional/somatic."}
            },
            "recommended_action": "Consult PHC for Complete Blood Count (CBC) and therapeutic Iron-Folic Acid supplementation",
            "facility_referred": "Chilkur Rural Maternity Sub-Centre",
            "sync_status": "Synced",
            "followup_status": "Pending",
            "timestamp": "2026-09-26 12:45:00"
        },
        {
            "patient_name": "Ramulu Naidu",
            "age": 64,
            "gender": "Male",
            "village": "Hyderabad (Old City)",
            "existing_conditions": "Joint pain",
            "current_medications": "Pain balms",
            "family_history": "None",
            "bp_systolic": 126,
            "bp_diastolic": 80,
            "blood_glucose": 110.0,
            "glucose_type": "Random",
            "spo2": 98.0,
            "temperature": 98.6,
            "pulse": 72,
            "weight": 70.0,
            "height": 162.0,
            "bmi": 26.7,
            "screened_conditions": ["Musculoskeletal Problems", "Elderly / Geriatric Health"],
            "symptoms": ["Severe knee joint pain", "Chronic lower back pain", "Morning joint stiffness >30 mins", "Difficulty climbing stairs"],
            "overall_risk": "Needs Medical Review",
            "condition_results": {
                "Musculoskeletal": {"status": "Needs Medical Review", "explanation": "Bilateral knee joint pain, morning stiffness and functional limitation consistent with degenerative osteoarthritis."},
                "Elderly Health": {"status": "Needs Medical Review", "explanation": "Mobility restriction and joint stiffness increase fall risk."}
            },
            "recommended_action": "Consult CHC Physiotherapy unit & Orthopedic Medical Officer for non-pharmacological joint management",
            "facility_referred": "Kondapur Community Health Centre & Maternity Wing",
            "sync_status": "Synced",
            "followup_status": "Pending",
            "timestamp": "2026-09-26 14:20:00"
        },
        {
            "patient_name": "Shaheen Sultana",
            "age": 28,
            "gender": "Female",
            "village": "Hyderabad (Old City)",
            "existing_conditions": "None",
            "current_medications": "None",
            "family_history": "None",
            "bp_systolic": 118,
            "bp_diastolic": 76,
            "blood_glucose": 96.0,
            "glucose_type": "Fasting",
            "spo2": 99.0,
            "temperature": 98.4,
            "pulse": 72,
            "weight": 54.0,
            "height": 158.0,
            "bmi": 21.6,
            "screened_conditions": ["Diabetes / Blood Sugar", "Hypertension / High BP", "Thyroid Disorders", "Mental Health & Well-being"],
            "symptoms": [],
            "overall_risk": "Low Risk",
            "condition_results": {
                "Diabetes": {"status": "Low Risk", "explanation": "Fasting blood sugar 96 mg/dL is within healthy normal limits."},
                "Blood Pressure": {"status": "Low Risk", "explanation": "Blood pressure 118/76 mmHg is optimal."},
                "Thyroid": {"status": "Low Risk", "explanation": "No symptoms or warning signs detected."},
                "Mental Health": {"status": "Low Risk", "explanation": "Positive mental well-being reported."}
            },
            "recommended_action": "Continue routine healthy lifestyle & annual community health screening",
            "facility_referred": "",
            "sync_status": "Synced",
            "followup_status": "Completed",
            "timestamp": "2026-09-26 16:00:00"
        },
        {
            "patient_name": "Narasimha Rao",
            "age": 52,
            "gender": "Male",
            "village": "Secunderabad",
            "existing_conditions": "Asthma",
            "current_medications": "Salbutamol inhaler",
            "family_history": "Asthma",
            "bp_systolic": 136,
            "bp_diastolic": 86,
            "blood_glucose": 118.0,
            "glucose_type": "Random",
            "spo2": 94.0,
            "temperature": 99.1,
            "pulse": 84,
            "weight": 66.0,
            "height": 170.0,
            "bmi": 22.8,
            "screened_conditions": ["Respiratory Health", "Infectious Disease Warning Signs"],
            "symptoms": ["Persistent cough >2 weeks", "Wheezing / noisy breathing", "Night sweats"],
            "overall_risk": "Needs Medical Review",
            "condition_results": {
                "Respiratory": {"status": "Needs Medical Review", "explanation": "Cough lasting over 2 weeks with wheezing and mild fever requires TB warning-sign evaluation and chest auscultation."},
                "Infectious Disease": {"status": "Needs Medical Review", "explanation": "Low-grade fever and cough >14 days warrants Sputum Smear / NAAT test under National TB Elimination Programme (NTEP)."}
            },
            "recommended_action": "Consult nearest PHC / NTEP testing centre for sputum examination and chest X-ray",
            "facility_referred": "Chevella Area Sub-District Hospital",
            "sync_status": "Synced",
            "followup_status": "Pending",
            "timestamp": "2026-09-26 17:15:00"
        },
        {
            "patient_name": "Anuradha Bai",
            "age": 73,
            "gender": "Female",
            "village": "Hyderabad (Old City)",
            "existing_conditions": "Hypertension, Osteoarthritis",
            "current_medications": "Telmisartan 40mg, Calcium",
            "family_history": "Hypertension",
            "bp_systolic": 144,
            "bp_diastolic": 86,
            "blood_glucose": 130.0,
            "glucose_type": "Random",
            "spo2": 96.0,
            "temperature": 98.4,
            "pulse": 78,
            "weight": 58.0,
            "height": 150.0,
            "bmi": 25.8,
            "screened_conditions": ["Elderly / Geriatric Health", "Musculoskeletal Problems", "Eye Health"],
            "symptoms": ["Frequent unsteadiness / difficulty balancing", "Difficulty reading & blurred vision", "Morning joint pain"],
            "overall_risk": "Needs Medical Review",
            "condition_results": {
                "Elderly Health": {"status": "Needs Medical Review", "explanation": "Postural instability in a 73-year-old indicates elevated fall risk; environmental safety and walking support advised."},
                "Eye Health": {"status": "Needs Medical Review", "explanation": "Blurred vision and reading difficulty consistent with age-related cataract or presbyopia."},
                "Musculoskeletal": {"status": "Needs Medical Review", "explanation": "Chronic joint pain managed with regular gentle mobility and calcium."}
            },
            "recommended_action": "Consult PHC Medical Officer for geriatric vision check and fall prevention counselling",
            "facility_referred": "Himayath Sagar Maternal & Child Welfare Centre",
            "sync_status": "Synced",
            "followup_status": "Pending",
            "timestamp": "2026-09-27 08:30:00"
        }
    ]
    
    for item in demo_screenings:
        save_community_screening(item)


# ---------------- COMMUNITY DOCTOR CONSULTATIONS & FOLLOW-UPS ----------------
def save_community_consultation(record: dict) -> int:
    """Save a doctor consultation / tele-visit to the database."""
    import datetime, json
    conn = get_connection()
    c = conn.cursor()

    timestamp = record.get("timestamp") or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meds_json = json.dumps(record.get("medicines", []), ensure_ascii=False) if isinstance(record.get("medicines"), list) else str(record.get("medicines", ""))

    c.execute("""
    INSERT INTO community_consultations (
        patient_name, village, doctor_name, doctor_role, doctor_center,
        problem, advice_summary, medicines_json, facility_referred,
        referral_reason, referral_status, followup_date, followup_action,
        followup_status, sync_status, timestamp
    )
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        record.get("patient_name", "Community Member"),
        record.get("village", "Hyderabad (Old City)"),
        record.get("doctor_name", "Doctor"),
        record.get("doctor_role", "Medical Officer"),
        record.get("doctor_center", "Govt. PHC"),
        record.get("problem", "General Consultation"),
        record.get("advice_summary", ""),
        meds_json,
        record.get("facility_referred", ""),
        record.get("referral_reason", ""),
        record.get("referral_status", "Pending"),
        record.get("followup_date", ""),
        record.get("followup_action", ""),
        record.get("followup_status", "Pending"),
        record.get("sync_status", "Synced"),
        timestamp
    ))
    row_id = c.lastrowid
    conn.commit()
    conn.close()
    return row_id

def get_community_consultations(village: str = None, patient_name: str = None, limit: int = 50):
    """Retrieve community doctor consultations, optionally filtered by village or patient."""
    conn = get_connection()
    c = conn.cursor()

    conditions = []
    params = []
    if village and village != "All Villages":
        conditions.append("village = ?")
        params.append(village)
    if patient_name and patient_name not in ["All Patients", "Community Member"]:
        conditions.append("patient_name LIKE ?")
        params.append(f"%{patient_name}%")

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    c.execute(f"""
    SELECT id, patient_name, village, doctor_name, doctor_role, doctor_center,
           problem, advice_summary, medicines_json, facility_referred,
           referral_reason, referral_status, followup_date, followup_action,
           followup_status, sync_status, timestamp
    FROM community_consultations
    {where_clause}
    ORDER BY id DESC
    LIMIT ?
    """, tuple(params))

    rows = c.fetchall()
    conn.close()

    results = []
    for r in rows:
        results.append({
            "id": r[0],
            "patient_name": r[1],
            "village": r[2],
            "doctor_name": r[3],
            "doctor_role": r[4],
            "doctor_center": r[5],
            "problem": r[6],
            "advice_summary": r[7],
            "medicines_json": r[8],
            "facility_referred": r[9],
            "referral_reason": r[10],
            "referral_status": r[11],
            "followup_date": r[12],
            "followup_action": r[13],
            "followup_status": r[14],
            "sync_status": r[15],
            "timestamp": r[16]
        })
    return results

def update_consultation_followup(consultation_id: int, followup_status: str, referral_status: str = None):
    """Update follow-up status and optionally referral status for a consultation."""
    conn = get_connection()
    c = conn.cursor()
    if referral_status:
        c.execute("""
        UPDATE community_consultations
        SET followup_status = ?, referral_status = ?
        WHERE id = ?
        """, (followup_status, referral_status, consultation_id))
    else:
        c.execute("""
        UPDATE community_consultations
        SET followup_status = ?
        WHERE id = ?
        """, (followup_status, consultation_id))
    conn.commit()
    conn.close()

def seed_community_consultations_demo_data():
    """Populate baseline realistic consultation records if none exist."""
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM community_consultations")
    count = c.fetchone()[0]
    conn.close()
    if count > 0:
        return

    demo_consultations = [
        {
            "patient_name": "Mohammad Ismail",
            "village": "Hyderabad (Old City)",
            "doctor_name": "Dr. Srinivas Rao",
            "doctor_role": "Senior Medical Officer, MD General Medicine",
            "doctor_center": "Govt. General Hospital & CHC Cluster",
            "problem": "High blood pressure (154/96) and dizziness on stairs",
            "advice_summary": "Please take Amlodipine 5mg daily after breakfast. Reduce salt in food. Check BP again after 1 week at the local PHC.",
            "medicines": ["Tab. Amlodipine 5mg (1-0-0) after food", "ORS hydration fluids if dizzy"],
            "facility_referred": "Moinabad 24/7 Primary Health Centre (PHC)",
            "referral_reason": "BP titration and fasting blood glucose test",
            "referral_status": "Pending",
            "followup_date": "02 Oct 2026",
            "followup_action": "Check BP with ASHA worker or PHC nurse",
            "followup_status": "Pending",
            "sync_status": "Synced",
            "timestamp": "2026-09-25 11:00:00"
        },
        {
            "patient_name": "Fatima Begum",
            "village": "Hyderabad (Old City)",
            "doctor_name": "Dr. Farhana Yasmeen",
            "doctor_role": "Civil Assistant Surgeon (MBBS, DGO)",
            "doctor_center": "Govt. Community Health Centre",
            "problem": "Excessive thirst, frequent urination, blurred vision, sugar 242 mg/dL",
            "advice_summary": "High blood glucose observed. Avoid sweets and white rice. Visit Kondapur CHC for fasting blood sugar and eye checkup.",
            "medicines": ["Tab. Metformin 500mg as directed at PHC", "Drink 3 liters clean boiled water daily"],
            "facility_referred": "Kondapur Community Health Centre & Maternity Wing",
            "referral_reason": "Diabetes confirmation and diabetic retinopathy screening",
            "referral_status": "Pending",
            "followup_date": "29 Sep 2026",
            "followup_action": "Fasting blood sugar test and eye checkup at CHC",
            "followup_status": "Pending",
            "sync_status": "Synced",
            "timestamp": "2026-09-25 12:15:00"
        },
        {
            "patient_name": "Abdul Qadeer",
            "village": "Hyderabad (Old City)",
            "doctor_name": "Dr. Srinivas Rao",
            "doctor_role": "Senior Medical Officer, MD General Medicine",
            "doctor_center": "Govt. General Hospital & CHC Cluster",
            "problem": "Chest tightness and severe breathlessness, urgent BP 172/104",
            "advice_summary": "Immediate referral issued for ECG and cardiac evaluation. Emergency transport arranged.",
            "medicines": ["Emergency Sorbitrate under tongue as prescribed by emergency physician"],
            "facility_referred": "Osmania General Hospital - 24/7 Emergency Wing",
            "referral_reason": "Urgent ECG, Cardiac Markers & Cardiology Evaluation",
            "referral_status": "Referred",
            "followup_date": "28 Sep 2026",
            "followup_action": "Cardiology post-admission review & BP monitoring",
            "followup_status": "Pending",
            "sync_status": "Synced",
            "timestamp": "2026-09-26 10:00:00"
        }
    ]

    for item in demo_consultations:
        save_community_consultation(item)
