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

    # Performance indices to ensure instant query execution
    try:
        c.execute("CREATE INDEX IF NOT EXISTS idx_users_uid ON users(unique_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_daily_logs_uid ON daily_logs(user_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_alerts_uid ON alerts(user_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_baby_logs_mid ON baby_logs(mother_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_vax_mid ON vaccinations(mother_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_ex_mid ON exercise_logs(mother_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_case_actions_mid ON case_actions(mother_id);")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()
    _db_initialized = True


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