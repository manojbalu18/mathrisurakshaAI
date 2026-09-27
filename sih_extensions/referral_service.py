"""
SIH Closed-loop Referral Service.
"""
import uuid
from typing import List, Dict, Any, Optional
from .sih_database import get_sih_connection, DB_PATH
from .facility_directory import FacilityDirectory

class ReferralService:
    @staticmethod
    def create_referral(patient_id: str, source_facility: str, destination_facility: str, reason: str, priority: int = 0, clinical_context: str = "", referred_by: str = "", db_path: str = DB_PATH) -> Dict[str, Any]:
        dest = FacilityDirectory.get_facility(destination_facility, db_path)
        if not dest or dest.get('status') != 'Active':
            return {"success": False, "error": "Invalid or inactive destination facility"}

        referral_id = str(uuid.uuid4())
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO sih_referrals (
                    referral_id, patient_id, source_facility, referred_to_facility, referred_by, reason, 
                    priority, clinical_context, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'REFERRAL_CREATED')
            """, (referral_id, patient_id, source_facility, destination_facility, referred_by, reason, priority, clinical_context))
            conn.commit()
        return {"success": True, "referral_id": referral_id}

    @staticmethod
    def get_referral(referral_id: str, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT referral_id, patient_id, source_facility, referred_to_facility, referred_by, reason,
                       priority, clinical_context, status, appointment_id, queue_id, consultation_id, follow_up_info,
                       notes, created_at, accepted_at, completed_at, closed_at, updated_at
                FROM sih_referrals WHERE referral_id = ?
            """, (referral_id,))
            r = c.fetchone()
            if r:
                return {
                    "referral_id": r[0], "patient_id": r[1], "source_facility": r[2], "destination_facility": r[3],
                    "referred_by": r[4], "reason": r[5], "priority": r[6], "clinical_context": r[7], "status": r[8],
                    "appointment_id": r[9], "queue_id": r[10], "consultation_id": r[11], "follow_up_info": r[12],
                    "notes": r[13], "created_at": r[14], "accepted_at": r[15], "completed_at": r[16],
                    "closed_at": r[17], "updated_at": r[18]
                }
        return None

    @staticmethod
    def list_incoming_referrals(facility_id: str, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT referral_id, patient_id, source_facility, reason, priority, status, created_at
                FROM sih_referrals WHERE referred_to_facility = ?
                ORDER BY created_at DESC
            """, (facility_id,))
            rows = c.fetchall()
            return [{"referral_id": r[0], "patient_id": r[1], "source_facility": r[2], "reason": r[3], "priority": r[4], "status": r[5], "created_at": r[6]} for r in rows]

    @staticmethod
    def update_status(referral_id: str, new_status: str, notes: str = "", db_path: str = DB_PATH) -> bool:
        valid_statuses = ['REFERRAL_CREATED', 'SENT', 'RECEIVED', 'ACCEPTED', 'REJECTED', 'APPOINTMENT_CREATED', 'CHECKED_IN', 'CONSULTATION_COMPLETED', 'FOLLOW_UP', 'CLOSED', 'CANCELLED']
        if new_status not in valid_statuses:
            return False
            
        timestamp_col = ""
        if new_status == 'ACCEPTED':
            timestamp_col = ", accepted_at = CURRENT_TIMESTAMP"
        elif new_status == 'CONSULTATION_COMPLETED':
            timestamp_col = ", completed_at = CURRENT_TIMESTAMP"
        elif new_status == 'CLOSED' or new_status == 'CANCELLED' or new_status == 'REJECTED':
            timestamp_col = ", closed_at = CURRENT_TIMESTAMP"

        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute(f"""
                UPDATE sih_referrals 
                SET status = ?, notes = ?, updated_at = CURRENT_TIMESTAMP {timestamp_col}
                WHERE referral_id = ?
            """, (new_status, notes, referral_id))
            affected = c.rowcount
            conn.commit()
            return affected > 0

    @staticmethod
    def link_appointment(referral_id: str, appointment_id: str, db_path: str = DB_PATH) -> bool:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE sih_referrals 
                SET appointment_id = ?, status = 'APPOINTMENT_CREATED', updated_at = CURRENT_TIMESTAMP
                WHERE referral_id = ?
            """, (appointment_id, referral_id))
            affected = c.rowcount
            conn.commit()
            return affected > 0

    @staticmethod
    def link_queue(referral_id: str, queue_id: str, db_path: str = DB_PATH) -> bool:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE sih_referrals 
                SET queue_id = ?, status = 'CHECKED_IN', updated_at = CURRENT_TIMESTAMP
                WHERE referral_id = ?
            """, (queue_id, referral_id))
            affected = c.rowcount
            conn.commit()
            return affected > 0
