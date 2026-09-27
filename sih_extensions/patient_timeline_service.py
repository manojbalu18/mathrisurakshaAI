"""
SIH Patient Timeline Service.
Aggregates legacy and SIH data into a unified, read-only chronological timeline.
"""
from typing import List, Dict, Any, Optional
import sqlite3
from .sih_database import get_sih_connection, DB_PATH
import database # Import legacy database

class PatientTimelineService:
    @staticmethod
    def get_patient_timeline(patient_id: str, event_type: str = None, start_date: str = None, end_date: str = None, limit: int = 100, offset: int = 0, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
        events = []
        
        # 1. Fetch from legacy database connection
        # Need to use the main database.py path if db_path is not test db, but for tests we'll pass test db
        # Actually legacy `database.get_connection()` hardcodes "maatrisuraksha.db".
        # For test isolation, we'll connect directly to db_path since tests initialize the legacy schema there too.
        with sqlite3.connect(db_path, check_same_thread=False) as conn:
            c = conn.cursor()
            
            try:
                c.execute("SELECT id, date, risk_level, risk_score, symptoms, mood, nutrition FROM daily_logs WHERE user_id = ? OR CAST(user_id AS TEXT) = ?", (patient_id, str(patient_id)))
                for r in c.fetchall():
                    events.append({
                        "event_id": f"log-{r[0]}",
                        "patient_id": patient_id,
                        "event_type": "DAILY_LOG",
                        "event_date": r[1] or "",
                        "title": f"Daily Log: {r[2]} Risk",
                        "description": f"Symptoms: {r[4] or 'None'}. Mood: {r[5]}. Nutrition: {r[6]}.",
                        "status": r[2],
                        "source": "daily_logs",
                        "reference_id": str(r[0]),
                        "metadata": {"risk_score": r[3], "symptoms": r[4]}
                    })
            except sqlite3.OperationalError:
                pass
                
            try:
                c.execute("SELECT id, timestamp, risk_level, status FROM alerts WHERE user_id = ? OR CAST(user_id AS TEXT) = ?", (patient_id, str(patient_id)))
                for r in c.fetchall():
                    events.append({
                        "event_id": f"alert-{r[0]}",
                        "patient_id": patient_id,
                        "event_type": "ALERT",
                        "event_date": r[1] or "",
                        "title": f"Risk Alert: {r[2]}",
                        "description": f"Alert Status: {r[3]}",
                        "status": r[3],
                        "source": "alerts",
                        "reference_id": str(r[0]),
                        "metadata": {"risk_level": r[2]}
                    })
            except sqlite3.OperationalError:
                pass

            try:
                c.execute("SELECT id, timestamp, status, action_taken, notes, asha_id FROM case_actions WHERE mother_id = ? OR CAST(mother_id AS TEXT) = ?", (patient_id, str(patient_id)))
                for r in c.fetchall():
                    events.append({
                        "event_id": f"case-{r[0]}",
                        "patient_id": patient_id,
                        "event_type": "CASE_ACTION",
                        "event_date": r[1] or "",
                        "title": f"Case Action: {r[3]}",
                        "description": r[4] or "No notes provided.",
                        "status": r[2],
                        "source": "case_actions",
                        "reference_id": str(r[0]),
                        "metadata": {"asha_id": r[5]}
                    })
            except sqlite3.OperationalError:
                pass
                
            try:
                c.execute("SELECT id, timestamp, exercise_type FROM exercise_logs WHERE mother_id = ? OR CAST(mother_id AS TEXT) = ?", (patient_id, str(patient_id)))
                for r in c.fetchall():
                    events.append({
                        "event_id": f"ex-{r[0]}",
                        "patient_id": patient_id,
                        "event_type": "EXERCISE_LOG",
                        "event_date": r[1] or "",
                        "title": "Exercise Logged",
                        "description": f"Type: {r[2]}",
                        "status": "COMPLETED",
                        "source": "exercise_logs",
                        "reference_id": str(r[0]),
                        "metadata": {}
                    })
            except sqlite3.OperationalError:
                pass

            try:
                c.execute("SELECT id, date, fever, cough, weight, feeding_pattern, sleep_hours FROM baby_logs WHERE mother_id = ? OR CAST(mother_id AS TEXT) = ?", (patient_id, str(patient_id)))
                for r in c.fetchall():
                    events.append({
                        "event_id": f"baby-{r[0]}",
                        "patient_id": patient_id,
                        "event_type": "BABY_LOG",
                        "event_date": r[1] or "",
                        "title": "Baby Health Log",
                        "description": f"Weight: {r[4]}. Feeding: {r[5]}. Sleep: {r[6]}.",
                        "status": "LOGGED",
                        "source": "baby_logs",
                        "reference_id": str(r[0]),
                        "metadata": {"fever": r[2], "cough": r[3]}
                    })
            except sqlite3.OperationalError:
                pass

            try:
                c.execute("SELECT id, completed_date, due_date, vaccine_name, status FROM vaccinations WHERE mother_id = ? OR CAST(mother_id AS TEXT) = ?", (patient_id, str(patient_id)))
                for r in c.fetchall():
                    dt = r[1] if (r[4] == 'Completed' and r[1]) else r[2]
                    events.append({
                        "event_id": f"vax-{r[0]}",
                        "patient_id": patient_id,
                        "event_type": "VACCINATION",
                        "event_date": dt or "",
                        "title": f"Vaccination: {r[3]}",
                        "description": f"Status: {r[4]}",
                        "status": r[4],
                        "source": "vaccinations",
                        "reference_id": str(r[0]),
                        "metadata": {"due_date": r[2], "completed_date": r[1]}
                    })
            except sqlite3.OperationalError:
                pass

        # 2. Fetch from SIH tables
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            
            c.execute("SELECT appointment_id, created_at, appointment_time, facility_id, doctor_id, status FROM sih_appointments WHERE patient_id = ?", (patient_id,))
            for r in c.fetchall():
                events.append({
                    "event_id": f"app-{r[0]}",
                    "patient_id": patient_id,
                    "event_type": "APPOINTMENT",
                    "event_date": r[2] or r[1] or "",
                    "title": "Appointment Scheduled",
                    "description": f"Facility: {r[3]}. Provider: {r[4] or 'Unassigned'}.",
                    "status": r[5],
                    "source": "sih_appointments",
                    "reference_id": r[0],
                    "metadata": {}
                })

            c.execute("SELECT referral_id, created_at, source_facility, referred_to_facility, reason, status FROM sih_referrals WHERE patient_id = ?", (patient_id,))
            for r in c.fetchall():
                events.append({
                    "event_id": f"ref-{r[0]}",
                    "patient_id": patient_id,
                    "event_type": "REFERRAL",
                    "event_date": r[1] or "",
                    "title": f"Referral to {r[3]}",
                    "description": f"Reason: {r[4]}",
                    "status": r[5],
                    "source": "sih_referrals",
                    "reference_id": r[0],
                    "metadata": {"source_facility": r[2]}
                })

            c.execute("SELECT consultation_id, requested_at, facility_id, doctor_id, reason, symptoms, status, assessment, advice FROM sih_consultations WHERE patient_id = ?", (patient_id,))
            for r in c.fetchall():
                events.append({
                    "event_id": f"cons-{r[0]}",
                    "patient_id": patient_id,
                    "event_type": "TELECONSULTATION",
                    "event_date": r[1] or "",
                    "title": "Teleconsultation",
                    "description": f"Reason: {r[4]}. Assessment: {r[7] or 'Pending'}",
                    "status": r[6],
                    "source": "sih_consultations",
                    "reference_id": r[0],
                    "metadata": {"facility": r[2], "doctor": r[3], "advice": r[8]}
                })
                
            c.execute("SELECT id, joined_at, facility_id, department, status, token_number FROM sih_queue WHERE patient_id = ?", (patient_id,))
            for r in c.fetchall():
                events.append({
                    "event_id": f"queue-{r[0]}",
                    "patient_id": patient_id,
                    "event_type": "QUEUE_EVENT",
                    "event_date": r[1] or "",
                    "title": f"Queue Join: {r[5]}",
                    "description": f"Facility: {r[2]} Dept: {r[3]}",
                    "status": r[4],
                    "source": "sih_queue",
                    "reference_id": str(r[0]),
                    "metadata": {"token": r[5]}
                })

        # Apply filtering
        if event_type:
            events = [e for e in events if e["event_type"] == event_type]
            
        if start_date:
            events = [e for e in events if e["event_date"] >= start_date]
            
        if end_date:
            events = [e for e in events if e["event_date"] <= end_date]
            
        # Sort by date descending
        # Handle empty string dates safely by putting them at the end or treating them as min date
        events.sort(key=lambda x: x["event_date"] or "0000", reverse=True)
        
        # Paginate
        return events[offset:offset+limit]
