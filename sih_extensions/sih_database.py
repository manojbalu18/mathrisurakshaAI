"""
SIH Foundation Database Layer.
Safely adds new SIH tables to the existing database without modifying existing records.
"""

import sqlite3
import logging
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DB_PATH = "maatrisuraksha.db"

@contextmanager
def get_sih_connection(db_path=DB_PATH):
    """Provides a transactional database connection for SIH operations."""
    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=10.0)
    # Enable WAL mode for performance
    conn.execute("PRAGMA journal_mode = WAL;")
    try:
        yield conn
    finally:
        conn.close()

def init_sih_db(db_path=DB_PATH):
    """
    Idempotent initialization of new SIH tables.
    Uses CREATE TABLE IF NOT EXISTS safely.
    Never drops or alters legacy tables.
    """
    with get_sih_connection(db_path) as conn:
        c = conn.cursor()
        
        # 1. Facility Directory Table
        c.execute("""
        CREATE TABLE IF NOT EXISTS sih_facilities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            facility_id TEXT UNIQUE,
            name TEXT,
            type TEXT,
            address TEXT,
            latitude REAL,
            longitude REAL,
            contact_number TEXT,
            operating_hours TEXT,
            emergency_available INTEGER DEFAULT 0,
            services TEXT,
            status TEXT DEFAULT 'Active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Add additive columns for sih_facilities
        c.execute("PRAGMA table_info(sih_facilities)")
        fac_columns = [col[1] for col in c.fetchall()]
        for col, col_type in [
            ('address', 'TEXT'),
            ('operating_hours', 'TEXT'),
            ('emergency_available', 'INTEGER DEFAULT 0'),
            ('services', 'TEXT')
        ]:
            if col not in fac_columns:
                c.execute(f"ALTER TABLE sih_facilities ADD COLUMN {col} {col_type}")

        # 2. Inventory (Medicine/Diagnostics) Table
        c.execute("""
        CREATE TABLE IF NOT EXISTS sih_inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            facility_id TEXT,
            item_type TEXT,
            item_name TEXT,
            quantity INTEGER,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(facility_id) REFERENCES sih_facilities(facility_id)
        )
        """)

        # Add additive columns for sih_inventory
        c.execute("PRAGMA table_info(sih_inventory)")
        inv_columns = [col[1] for col in c.fetchall()]
        
        for col, col_type in [
            ('item_id', 'TEXT'),
            ('generic_name', 'TEXT'),
            ('category', 'TEXT'),
            ('department', 'TEXT'),
            ('unit', 'TEXT'),
            ('status', 'TEXT'),
            ('source', 'TEXT'),
            ('verification_status', 'TEXT'),
            ('active', 'INTEGER DEFAULT 1')
        ]:
            if col not in inv_columns:
                c.execute(f"ALTER TABLE sih_inventory ADD COLUMN {col} {col_type}")


        # 3. Appointments Table
        c.execute("""
        CREATE TABLE IF NOT EXISTS sih_appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            appointment_id TEXT UNIQUE,
            patient_id TEXT, 
            facility_id TEXT,
            doctor_id TEXT,
            doctor_name TEXT,
            consultation_type TEXT DEFAULT 'In-Person',
            reason TEXT,
            time_slot TEXT,
            pregnancy_week INTEGER,
            trimester TEXT,
            reminder_enabled INTEGER DEFAULT 1,
            appointment_time TIMESTAMP,
            status TEXT DEFAULT 'Confirmed',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP
        )
        """)

        # Add additive columns for sih_appointments
        c.execute("PRAGMA table_info(sih_appointments)")
        appt_columns = [col[1] for col in c.fetchall()]
        for col, col_type in [
            ('doctor_name', 'TEXT'),
            ('consultation_type', "TEXT DEFAULT 'In-Person'"),
            ('reason', 'TEXT'),
            ('time_slot', 'TEXT'),
            ('pregnancy_week', 'INTEGER'),
            ('trimester', 'TEXT'),
            ('reminder_enabled', 'INTEGER DEFAULT 1'),
            ('updated_at', 'TIMESTAMP')
        ]:
            if col not in appt_columns:
                c.execute(f"ALTER TABLE sih_appointments ADD COLUMN {col} {col_type}")

        # 4. Queue Management Table
        c.execute("""
        CREATE TABLE IF NOT EXISTS sih_queue (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            facility_id TEXT,
            patient_id TEXT,
            token_number TEXT,
            status TEXT DEFAULT 'Waiting',
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Add additive columns for sih_queue
        c.execute("PRAGMA table_info(sih_queue)")
        queue_columns = [col[1] for col in c.fetchall()]
        if 'appointment_id' not in queue_columns:
            c.execute("ALTER TABLE sih_queue ADD COLUMN appointment_id TEXT")
        if 'department' not in queue_columns:
            c.execute("ALTER TABLE sih_queue ADD COLUMN department TEXT")
        if 'priority' not in queue_columns:
            c.execute("ALTER TABLE sih_queue ADD COLUMN priority INTEGER DEFAULT 0")
        if 'called_at' not in queue_columns:
            c.execute("ALTER TABLE sih_queue ADD COLUMN called_at TIMESTAMP")
        if 'consultation_start_at' not in queue_columns:
            c.execute("ALTER TABLE sih_queue ADD COLUMN consultation_start_at TIMESTAMP")
        if 'completed_at' not in queue_columns:
            c.execute("ALTER TABLE sih_queue ADD COLUMN completed_at TIMESTAMP")
        if 'updated_at' not in queue_columns:
            c.execute("ALTER TABLE sih_queue ADD COLUMN updated_at TIMESTAMP")

        # 5. Closed-Loop Referrals Table
        c.execute("""
        CREATE TABLE IF NOT EXISTS sih_referrals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            referral_id TEXT UNIQUE,
            patient_id TEXT,
            referred_by TEXT,
            referred_to_facility TEXT,
            reason TEXT,
            status TEXT DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            closed_at TIMESTAMP
        )
        """)
        
        # Add additive columns for sih_referrals
        c.execute("PRAGMA table_info(sih_referrals)")
        ref_columns = [col[1] for col in c.fetchall()]
        if 'source_facility' not in ref_columns:
            c.execute("ALTER TABLE sih_referrals ADD COLUMN source_facility TEXT")
        if 'priority' not in ref_columns:
            c.execute("ALTER TABLE sih_referrals ADD COLUMN priority INTEGER DEFAULT 0")
        if 'clinical_context' not in ref_columns:
            c.execute("ALTER TABLE sih_referrals ADD COLUMN clinical_context TEXT")
        if 'appointment_id' not in ref_columns:
            c.execute("ALTER TABLE sih_referrals ADD COLUMN appointment_id TEXT")
        if 'queue_id' not in ref_columns:
            c.execute("ALTER TABLE sih_referrals ADD COLUMN queue_id TEXT")
        if 'consultation_id' not in ref_columns:
            c.execute("ALTER TABLE sih_referrals ADD COLUMN consultation_id TEXT")
        if 'follow_up_info' not in ref_columns:
            c.execute("ALTER TABLE sih_referrals ADD COLUMN follow_up_info TEXT")
        if 'notes' not in ref_columns:
            c.execute("ALTER TABLE sih_referrals ADD COLUMN notes TEXT")
        if 'accepted_at' not in ref_columns:
            c.execute("ALTER TABLE sih_referrals ADD COLUMN accepted_at TIMESTAMP")
        if 'completed_at' not in ref_columns:
            c.execute("ALTER TABLE sih_referrals ADD COLUMN completed_at TIMESTAMP")
        if 'updated_at' not in ref_columns:
            c.execute("ALTER TABLE sih_referrals ADD COLUMN updated_at TIMESTAMP")

        # 6. Teleconsultation Table
        c.execute("""
        CREATE TABLE IF NOT EXISTS sih_consultations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            consultation_id TEXT UNIQUE,
            patient_id TEXT,
            doctor_id TEXT,
            status TEXT DEFAULT 'Scheduled',
            meeting_url TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        # Add additive columns for sih_consultations
        c.execute("PRAGMA table_info(sih_consultations)")
        cons_columns = [col[1] for col in c.fetchall()]
        
        for col, col_type in [
            ('requesting_user_id', 'TEXT'),
            ('facility_id', 'TEXT'),
            ('referral_id', 'TEXT'),
            ('appointment_id', 'TEXT'),
            ('reason', 'TEXT'),
            ('symptoms', 'TEXT'),
            ('priority', 'INTEGER DEFAULT 0'),
            ('requested_at', 'TIMESTAMP'),
            ('accepted_at', 'TIMESTAMP'),
            ('started_at', 'TIMESTAMP'),
            ('completed_at', 'TIMESTAMP'),
            ('cancelled_at', 'TIMESTAMP'),
            ('notes', 'TEXT'),
            ('assessment', 'TEXT'),
            ('advice', 'TEXT'),
            ('outcome', 'TEXT'),
            ('follow_up_date', 'TIMESTAMP'),
            ('follow_up_instructions', 'TEXT'),
            ('provider_notes', 'TEXT'),
            ('updated_at', 'TIMESTAMP')
        ]:
            if col not in cons_columns:
                c.execute(f"ALTER TABLE sih_consultations ADD COLUMN {col} {col_type}")

        # 7. FHIR/ABDM Records Table
        c.execute("""
        CREATE TABLE IF NOT EXISTS sih_fhir_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT,
            record_type TEXT,
            payload TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # 8. SIH Offline Sync Queue
        c.execute("""
        CREATE TABLE IF NOT EXISTS sih_offline_sync (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_id TEXT UNIQUE,
            operation_type TEXT,
            payload TEXT,
            status TEXT DEFAULT 'PENDING',
            retry_count INTEGER DEFAULT 0,
            last_attempt TIMESTAMP,
            error_msg TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            synced_at TIMESTAMP
        )
        """)

        # 9. Patient Prescriptions Table
        c.execute("""
        CREATE TABLE IF NOT EXISTS sih_prescriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prescription_id TEXT UNIQUE,
            patient_id TEXT,
            medicine_name TEXT,
            purpose TEXT,
            dosage TEXT,
            frequency TEXT,
            duration TEXT,
            food_instruction TEXT,
            schedule_time TEXT,
            taken_status TEXT DEFAULT 'Pending',
            doctor_name TEXT,
            facility_name TEXT,
            prescribed_date DATE,
            is_current INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # 10. Patient Diagnostics Table
        c.execute("""
        CREATE TABLE IF NOT EXISTS sih_diagnostics_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            test_id TEXT UNIQUE,
            patient_id TEXT,
            test_name TEXT,
            reason TEXT,
            recommended_date DATE,
            status TEXT DEFAULT 'Pending',
            doctor_name TEXT,
            facility_id TEXT,
            facility_name TEXT,
            report_file_name TEXT,
            result_summary TEXT,
            completed_date DATE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """)

        # Create basic indexes for performance
        c.execute("CREATE INDEX IF NOT EXISTS idx_sih_fac_id ON sih_facilities(facility_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sih_app_pat ON sih_appointments(patient_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sih_ref_pat ON sih_referrals(patient_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sih_queue_fac ON sih_queue(facility_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sih_offline_status ON sih_offline_sync(status);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sih_presc_pat ON sih_prescriptions(patient_id);")
        c.execute("CREATE INDEX IF NOT EXISTS idx_sih_diag_pat ON sih_diagnostics_records(patient_id);")

        conn.commit()
