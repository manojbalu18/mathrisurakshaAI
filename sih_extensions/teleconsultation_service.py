"""
SIH Teleconsultation Service.
Handles teleconsultation workflow and integrates an abstracted provider for future WebRTC logic.
"""

import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from .sih_database import get_sih_connection, DB_PATH
from .facility_directory import FacilityDirectory

class TeleconsultationProvider:
    """Abstract base class/interface for Teleconsultation Providers (e.g. WebRTC, Zoom, etc)."""
    
    def create_session(self, consultation_id: str) -> Dict[str, Any]:
        raise NotImplementedError
        
    def join_session(self, session_id: str, user_id: str) -> Dict[str, Any]:
        raise NotImplementedError
        
    def end_session(self, session_id: str) -> bool:
        raise NotImplementedError
        
    def session_status(self, session_id: str) -> str:
        raise NotImplementedError

class DemoTeleconsultationProvider(TeleconsultationProvider):
    """A safe local demo provider that fakes a session without external APIs."""
    
    def create_session(self, consultation_id: str) -> Dict[str, Any]:
        session_id = f"demo-session-{consultation_id}"
        return {
            "success": True,
            "session_id": session_id,
            "meeting_url": f"https://demo.maatrisuraksha.local/meet/{session_id}?mode=DEMO_TELECONSULTATION",
            "message": "DEMO TELECONSULTATION: Not a real video call"
        }
        
    def join_session(self, session_id: str, user_id: str) -> Dict[str, Any]:
        return {
            "success": True,
            "message": "Joined DEMO TELECONSULTATION"
        }
        
    def end_session(self, session_id: str) -> bool:
        return True
        
    def session_status(self, session_id: str) -> str:
        return "ACTIVE"


class TeleconsultationService:
    provider: TeleconsultationProvider = DemoTeleconsultationProvider()
    
    @staticmethod
    def set_provider(provider: TeleconsultationProvider):
        TeleconsultationService.provider = provider
        
    @staticmethod
    def create_request(patient_id: str, requesting_user_id: str, facility_id: str, reason: str, symptoms: str = "", priority: int = 0, referral_id: str = "", appointment_id: str = "", db_path: str = DB_PATH) -> Dict[str, Any]:
        # Validate facility
        fac = FacilityDirectory.get_facility(facility_id, db_path)
        if not fac or fac.get('status') != 'Active':
            return {"success": False, "error": "Invalid or inactive facility"}
            
        consultation_id = str(uuid.uuid4())
        
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO sih_consultations (
                    consultation_id, patient_id, requesting_user_id, facility_id, referral_id, appointment_id,
                    reason, symptoms, priority, status, requested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'REQUESTED', CURRENT_TIMESTAMP)
            """, (consultation_id, patient_id, requesting_user_id, facility_id, referral_id, appointment_id, reason, symptoms, priority))
            conn.commit()
            
        return {"success": True, "consultation_id": consultation_id}

    @staticmethod
    def get_consultation(consultation_id: str, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT consultation_id, patient_id, requesting_user_id, doctor_id, facility_id, referral_id, appointment_id,
                       reason, symptoms, priority, status, meeting_url, requested_at, accepted_at, started_at, completed_at,
                       cancelled_at, notes, assessment, advice, outcome, follow_up_date, follow_up_instructions, provider_notes, updated_at
                FROM sih_consultations WHERE consultation_id = ?
            """, (consultation_id,))
            r = c.fetchone()
            if r:
                return {
                    "consultation_id": r[0], "patient_id": r[1], "requesting_user_id": r[2], "doctor_id": r[3],
                    "facility_id": r[4], "referral_id": r[5], "appointment_id": r[6], "reason": r[7], "symptoms": r[8],
                    "priority": r[9], "status": r[10], "meeting_url": r[11], "requested_at": r[12], "accepted_at": r[13],
                    "started_at": r[14], "completed_at": r[15], "cancelled_at": r[16], "notes": r[17], "assessment": r[18],
                    "advice": r[19], "outcome": r[20], "follow_up_date": r[21], "follow_up_instructions": r[22],
                    "provider_notes": r[23], "updated_at": r[24]
                }
        return None

    @staticmethod
    def list_patient_consultations(patient_id: str, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT consultation_id, reason, status, requested_at FROM sih_consultations WHERE patient_id = ? ORDER BY requested_at DESC", (patient_id,))
            return [{"consultation_id": r[0], "reason": r[1], "status": r[2], "requested_at": r[3]} for r in c.fetchall()]

    @staticmethod
    def list_provider_consultations(doctor_id: str, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT consultation_id, patient_id, reason, status, requested_at FROM sih_consultations WHERE doctor_id = ? ORDER BY requested_at DESC", (doctor_id,))
            return [{"consultation_id": r[0], "patient_id": r[1], "reason": r[2], "status": r[3], "requested_at": r[4]} for r in c.fetchall()]

    @staticmethod
    def list_pending_requests(facility_id: str, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT consultation_id, patient_id, reason, priority, requested_at FROM sih_consultations WHERE facility_id = ? AND status = 'REQUESTED' ORDER BY priority DESC, requested_at ASC", (facility_id,))
            return [{"consultation_id": r[0], "patient_id": r[1], "reason": r[2], "priority": r[3], "requested_at": r[4]} for r in c.fetchall()]

    @staticmethod
    def accept_consultation(consultation_id: str, doctor_id: str, db_path: str = DB_PATH) -> Dict[str, Any]:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            session_info = TeleconsultationService.provider.create_session(consultation_id)
            c.execute("""
                UPDATE sih_consultations 
                SET status = 'ACCEPTED', doctor_id = ?, accepted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP, meeting_url = ?
                WHERE consultation_id = ? AND status = 'REQUESTED'
            """, (doctor_id, session_info.get("meeting_url", ""), consultation_id))
            if c.rowcount > 0:
                conn.commit()
                return {"success": True, "session_info": session_info}
            return {"success": False, "error": "Invalid state or consultation not found"}

    @staticmethod
    def reject_consultation(consultation_id: str, reason: str, db_path: str = DB_PATH) -> bool:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE sih_consultations 
                SET status = 'REJECTED', notes = ?, cancelled_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE consultation_id = ? AND status = 'REQUESTED'
            """, (reason, consultation_id))
            affected = c.rowcount
            conn.commit()
            return affected > 0
            
    @staticmethod
    def start_consultation(consultation_id: str, db_path: str = DB_PATH) -> bool:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE sih_consultations 
                SET status = 'IN_PROGRESS', started_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE consultation_id = ? AND status = 'ACCEPTED'
            """, (consultation_id,))
            affected = c.rowcount
            conn.commit()
            return affected > 0
            
    @staticmethod
    def complete_consultation(consultation_id: str, db_path: str = DB_PATH) -> bool:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE sih_consultations 
                SET status = 'COMPLETED', completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE consultation_id = ? AND status = 'IN_PROGRESS'
            """, (consultation_id,))
            affected = c.rowcount
            if affected > 0:
                TeleconsultationService.provider.end_session(f"demo-session-{consultation_id}")
            conn.commit()
            return affected > 0

    @staticmethod
    def cancel_consultation(consultation_id: str, reason: str, db_path: str = DB_PATH) -> bool:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE sih_consultations 
                SET status = 'CANCELLED', notes = ?, cancelled_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE consultation_id = ? AND status IN ('REQUESTED', 'ACCEPTED')
            """, (reason, consultation_id))
            affected = c.rowcount
            conn.commit()
            return affected > 0
            
    @staticmethod
    def mark_no_show(consultation_id: str, db_path: str = DB_PATH) -> bool:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE sih_consultations 
                SET status = 'NO_SHOW', cancelled_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE consultation_id = ? AND status = 'ACCEPTED'
            """, (consultation_id,))
            affected = c.rowcount
            conn.commit()
            return affected > 0
            
    @staticmethod
    def record_consultation_notes(consultation_id: str, assessment: str, advice: str, provider_notes: str = "", db_path: str = DB_PATH) -> bool:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE sih_consultations 
                SET assessment = ?, advice = ?, provider_notes = ?, updated_at = CURRENT_TIMESTAMP
                WHERE consultation_id = ?
            """, (assessment, advice, provider_notes, consultation_id))
            affected = c.rowcount
            conn.commit()
            return affected > 0

    @staticmethod
    def record_outcome(consultation_id: str, outcome: str, follow_up_date: str = "", follow_up_instructions: str = "", db_path: str = DB_PATH) -> bool:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE sih_consultations 
                SET outcome = ?, follow_up_date = ?, follow_up_instructions = ?, updated_at = CURRENT_TIMESTAMP
                WHERE consultation_id = ?
            """, (outcome, follow_up_date, follow_up_instructions, consultation_id))
            affected = c.rowcount
            conn.commit()
            return affected > 0
