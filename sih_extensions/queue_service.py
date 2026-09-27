"""
SIH Queue Management Service.
Handles persistent facility queueing, token generation, and wait time calculation.
"""
import uuid
import datetime
from typing import List, Dict, Any, Optional
from .sih_database import get_sih_connection, DB_PATH

class QueueService:
    @staticmethod
    def generate_token(facility_id: str, department: str, db_path: str = DB_PATH) -> str:
        """
        Safely generates a sequential token number for the given facility, department, and date.
        Uses a transaction and max query.
        """
        prefix = f"{department[:3].upper() if department else 'GEN'}"
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("BEGIN EXCLUSIVE TRANSACTION")
            try:
                c.execute("""
                    SELECT COUNT(*) FROM sih_queue 
                    WHERE facility_id = ? AND department = ? AND DATE(joined_at) = DATE('now')
                """, (facility_id, department))
                count = c.fetchone()[0]
                token_num = f"{prefix}-{count + 1:03d}"
                c.execute("COMMIT")
                return token_num
            except Exception:
                c.execute("ROLLBACK")
                raise

    @staticmethod
    def add_patient(facility_id: str, patient_id: str, department: str = "", appointment_id: str = "", priority: int = 0, db_path: str = DB_PATH) -> Dict[str, Any]:
        try:
            token_number = QueueService.generate_token(facility_id, department, db_path)
            with get_sih_connection(db_path) as conn:
                c = conn.cursor()
                c.execute("""
                    INSERT INTO sih_queue (
                        facility_id, patient_id, token_number, department, appointment_id, priority, status
                    ) VALUES (?, ?, ?, ?, ?, ?, 'WAITING')
                """, (facility_id, patient_id, token_number, department, appointment_id, priority))
                queue_id = c.lastrowid
                conn.commit()
            return {"success": True, "queue_id": queue_id, "token_number": token_number}
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def get_queue_entry(queue_id: int, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT id, facility_id, patient_id, token_number, department, appointment_id, priority, status,
                       joined_at, called_at, consultation_start_at, completed_at, updated_at
                FROM sih_queue WHERE id = ?
            """, (queue_id,))
            r = c.fetchone()
            if r:
                return {
                    "queue_id": r[0], "facility_id": r[1], "patient_id": r[2], "token_number": r[3],
                    "department": r[4], "appointment_id": r[5], "priority": r[6], "status": r[7],
                    "joined_at": r[8], "called_at": r[9], "consultation_start_at": r[10],
                    "completed_at": r[11], "updated_at": r[12]
                }
        return None

    @staticmethod
    def get_facility_queue(facility_id: str, date: str = None, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            query = """
                SELECT id, patient_id, token_number, department, priority, status, joined_at
                FROM sih_queue 
                WHERE facility_id = ? 
            """
            params = [facility_id]
            if date:
                query += " AND DATE(joined_at) = ?"
                params.append(date)
            else:
                query += " AND DATE(joined_at) = DATE('now')"
                
            query += " ORDER BY priority DESC, joined_at ASC"
            c.execute(query, tuple(params))
            rows = c.fetchall()
            return [
                {"queue_id": r[0], "patient_id": r[1], "token_number": r[2], "department": r[3],
                 "priority": r[4], "status": r[5], "joined_at": r[6]}
                for r in rows
            ]

    @staticmethod
    def calculate_position(queue_id: int, db_path: str = DB_PATH) -> int:
        entry = QueueService.get_queue_entry(queue_id, db_path)
        if not entry or entry['status'] != 'WAITING':
            return 0
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT COUNT(*) FROM sih_queue
                WHERE facility_id = ? AND DATE(joined_at) = DATE(?) AND status = 'WAITING'
                AND (priority > ? OR (priority = ? AND joined_at < ?))
            """, (entry['facility_id'], entry['joined_at'], entry['priority'], entry['priority'], entry['joined_at']))
            ahead = c.fetchone()[0]
        return ahead + 1

    @staticmethod
    def estimate_wait_time(queue_id: int, avg_consultation_minutes: int = 15, db_path: str = DB_PATH) -> int:
        position = QueueService.calculate_position(queue_id, db_path)
        if position <= 1:
            return 0
        return (position - 1) * avg_consultation_minutes

    @staticmethod
    def call_next(facility_id: str, date: str = None, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            query = "SELECT id FROM sih_queue WHERE facility_id = ? AND status = 'WAITING'"
            params = [facility_id]
            if date:
                query += " AND DATE(joined_at) = ?"
                params.append(date)
            else:
                query += " AND DATE(joined_at) = DATE('now')"
                
            query += " ORDER BY priority DESC, joined_at ASC LIMIT 1"
            c.execute(query, tuple(params))
            row = c.fetchone()
            if not row:
                return None
            queue_id = row[0]
            c.execute("""
                UPDATE sih_queue SET status = 'CALLED', called_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (queue_id,))
            conn.commit()
            return QueueService.get_queue_entry(queue_id, db_path)

    @staticmethod
    def update_status(queue_id: int, new_status: str, db_path: str = DB_PATH) -> bool:
        valid_statuses = ['WAITING', 'CALLED', 'IN_CONSULTATION', 'COMPLETED', 'CANCELLED', 'NO_SHOW']
        if new_status not in valid_statuses:
            return False
        timestamp_col = ""
        if new_status == 'IN_CONSULTATION':
            timestamp_col = ", consultation_start_at = CURRENT_TIMESTAMP"
        elif new_status == 'COMPLETED':
            timestamp_col = ", completed_at = CURRENT_TIMESTAMP"
            
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute(f"""
                UPDATE sih_queue 
                SET status = ?, updated_at = CURRENT_TIMESTAMP {timestamp_col}
                WHERE id = ?
            """, (new_status, queue_id))
            affected = c.rowcount
            conn.commit()
            return affected > 0
