"""
SIH Appointment Service.
Handles appointment booking, cancellation, rescheduling, time slot management, and provider listing.
"""

import sqlite3
import uuid
import datetime
from typing import List, Dict, Any, Optional

from .sih_database import get_sih_connection, init_sih_db, DB_PATH
from .facility_directory import FacilityDirectory

SAMPLE_PROVIDERS = {
    "Primary Health Centre (PHC)": [
        {"id": "DOC-PHC-01", "name": "[SAMPLE] Dr. Anita Sharma (Medical Officer - MBBS)", "specialty": "Maternal & Primary Care"},
        {"id": "DOC-PHC-02", "name": "[SAMPLE] Sister Sunita Devi (Senior Staff Nurse / LHV)", "specialty": "Antenatal Checkups & Immunization"},
        {"id": "DOC-PHC-03", "name": "[SAMPLE] Dr. Rajesh Kumar (Community Health Officer)", "specialty": "General Health & Nutrition"}
    ],
    "Community Health Centre (CHC)": [
        {"id": "DOC-CHC-01", "name": "[SAMPLE] Dr. Kavitha Reddy (Consultant OB/GYN - MS)", "specialty": "Obstetrics & High-Risk Pregnancy"},
        {"id": "DOC-CHC-02", "name": "[SAMPLE] Dr. Suresh Verma (Pediatrician - MD)", "specialty": "Neonatal & Child Health"},
        {"id": "DOC-CHC-03", "name": "[SAMPLE] Dr. Meena Rao (General Duty Medical Officer)", "specialty": "Maternal Emergency & OPD"}
    ],
    "District Hospital": [
        {"id": "DOC-DH-01", "name": "[SAMPLE] Dr. Priya Deshmukh (Senior Obstetrician - MD)", "specialty": "Comprehensive Emergency Obstetric Care (CEmONC)"},
        {"id": "DOC-DH-02", "name": "[SAMPLE] Dr. Arun Nair (Consultant Radiologist & Sonologist)", "specialty": "Fetal Ultrasound & Anomaly Scans"},
        {"id": "DOC-DH-03", "name": "[SAMPLE] Dr. Farooq Ahmed (Pediatric & SNCU Lead)", "specialty": "Newborn Intensive Care"},
        {"id": "DOC-DH-04", "name": "[SAMPLE] Dr. Radhika Iyer (Clinical Nutritionist)", "specialty": "Gestational Diabetes & Anemia Management"}
    ],
    "Government Maternity Hospital": [
        {"id": "DOC-GMH-01", "name": "[SAMPLE] Prof. Dr. Lakshmi Prasanna (HOD Obstetrics)", "specialty": "Maternal-Fetal Medicine & Complex Deliveries"},
        {"id": "DOC-GMH-02", "name": "[SAMPLE] Dr. Swathi Krishna (Specialist Gynecologist)", "specialty": "Labor Suite & Pre-eclampsia Unit"},
        {"id": "DOC-GMH-03", "name": "[SAMPLE] Dr. N. Ramesh (Level-III NICU Neonatologist)", "specialty": "Preterm & Critical Newborn Care"}
    ],
    "Emergency Care Centre": [
        {"id": "DOC-ECC-01", "name": "[SAMPLE] Dr. Vikram Rathore (Emergency Triage Physician)", "specialty": "24/7 Obstetric & Trauma Resuscitation"},
        {"id": "DOC-ECC-02", "name": "[SAMPLE] Dr. Deepa Chawla (Critical Care Response Lead)", "specialty": "Maternal Stabilization & Rapid Transit"}
    ],
    "Diagnostic Laboratory": [
        {"id": "DOC-LAB-01", "name": "[SAMPLE] Dr. Sneha Patel (Chief Pathologist - MD)", "specialty": "Maternal Blood Profiles & Biopathology"},
        {"id": "DOC-LAB-02", "name": "[SAMPLE] Dr. Arvind Gupta (Consultant Sonologist)", "specialty": "Maternal Doppler & Fetal Growth Scan"}
    ],
    "Pharmacy": [
        {"id": "DOC-PHARM-01", "name": "[SAMPLE] Pharmacist Naveen Kumar (Chief Pharmacist)", "specialty": "Essential Maternal Drug Counseling & IFA Dispensing"}
    ]
}

STANDARD_TIME_SLOTS = [
    "09:00 AM - 10:00 AM",
    "10:00 AM - 11:00 AM",
    "11:00 AM - 12:00 PM",
    "12:00 PM - 01:00 PM",
    "02:00 PM - 03:00 PM",
    "03:00 PM - 04:00 PM",
    "04:00 PM - 05:00 PM",
    "05:00 PM - 06:00 PM"
]

class AppointmentService:

    @staticmethod
    def get_providers_for_facility(facility_id: str, db_path: str = DB_PATH) -> List[Dict[str, str]]:
        """Returns sample demonstration healthcare providers for a given facility."""
        fac = FacilityDirectory.get_facility(facility_id, db_path)
        if not fac:
            return SAMPLE_PROVIDERS.get("Primary Health Centre (PHC)", [])
        ftype = fac.get("type", "Primary Health Centre (PHC)")
        return SAMPLE_PROVIDERS.get(ftype, SAMPLE_PROVIDERS.get("Primary Health Centre (PHC)", []))

    @staticmethod
    def get_time_slots() -> List[str]:
        return STANDARD_TIME_SLOTS

    @staticmethod
    def create_appointment(
        patient_id: str,
        facility_id: str,
        appointment_time: str,
        doctor_id: str = "",
        doctor_name: str = "",
        consultation_type: str = "In-Person",
        reason: str = "Routine Antenatal Checkup (ANC)",
        time_slot: str = "09:00 AM - 10:00 AM",
        pregnancy_week: Optional[int] = None,
        trimester: str = "",
        reminder_enabled: bool = True,
        status: str = "Scheduled",
        db_path: str = DB_PATH
    ) -> Dict[str, Any]:
        """
        Creates an appointment. Prevents double booking for the same patient at the same time.
        """
        init_sih_db(db_path=db_path)
        
        # Validate facility exists
        fac = FacilityDirectory.get_facility(facility_id, db_path)
        if not fac:
            return {"success": False, "error": "Invalid facility"}

        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            
            # Check conflicting active appointment for the same patient on that date/time
            c.execute("""
            SELECT appointment_id FROM sih_appointments 
            WHERE patient_id = ? AND appointment_time = ? AND status IN ('Scheduled', 'Confirmed', 'Pending', 'Rescheduled')
            """, (patient_id, appointment_time))
            conflict = c.fetchone()
            if conflict:
                return {
                    "success": False,
                    "error": f"Patient already has a conflicting appointment at this time ({conflict[0]}). Please choose another slot."
                }

            # Generate formatted clean Appointment ID
            rand_suffix = str(uuid.uuid4())[:6].upper()
            appointment_id = f"APT-{datetime.datetime.now().strftime('%Y%m%d')}-{rand_suffix}"
            
            c.execute("""
            INSERT INTO sih_appointments (
                appointment_id, patient_id, facility_id, doctor_id, doctor_name,
                consultation_type, reason, time_slot, pregnancy_week, trimester,
                reminder_enabled, appointment_time, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                appointment_id, patient_id, facility_id, doctor_id or "UNKNOWN", doctor_name or "Doctor / Medical Officer",
                consultation_type, reason, time_slot, pregnancy_week, trimester,
                1 if reminder_enabled else 0, appointment_time, status
            ))
            conn.commit()
            
        return {
            "success": True,
            "appointment_id": appointment_id,
            "facility_name": fac.get('name', ''),
            "appointment_time": appointment_time,
            "time_slot": time_slot,
            "doctor_name": doctor_name or "Doctor / Medical Officer",
            "consultation_type": consultation_type
        }

    @staticmethod
    def get_appointment(appointment_id: str, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
            SELECT a.appointment_id, a.patient_id, a.facility_id, a.doctor_id, a.doctor_name,
                   a.consultation_type, a.reason, a.time_slot, a.pregnancy_week, a.trimester,
                   a.reminder_enabled, a.appointment_time, a.status, a.created_at, a.updated_at,
                   f.name, f.type, f.address, f.contact_number
            FROM sih_appointments a
            LEFT JOIN sih_facilities f ON a.facility_id = f.facility_id
            WHERE a.appointment_id = ?
            """, (appointment_id,))
            r = c.fetchone()
            if r:
                return {
                    "appointment_id": r[0],
                    "patient_id": r[1],
                    "facility_id": r[2],
                    "doctor_id": r[3],
                    "doctor_name": r[4] or "Medical Officer / Specialist",
                    "consultation_type": r[5] or "In-Person",
                    "reason": r[6] or "Antenatal Checkup",
                    "time_slot": r[7] or "09:00 AM - 10:00 AM",
                    "pregnancy_week": r[8],
                    "trimester": r[9] or "",
                    "reminder_enabled": bool(r[10]),
                    "appointment_time": r[11],
                    "status": r[12] or "Confirmed",
                    "created_at": r[13],
                    "updated_at": r[14],
                    "facility_name": r[15] or r[2],
                    "facility_type": r[16] or "",
                    "facility_address": r[17] or "",
                    "facility_contact": r[18] or ""
                }
        return None

    @staticmethod
    def update_status(appointment_id: str, new_status: str, db_path: str = DB_PATH) -> bool:
        """Status options: Confirmed, Pending, Completed, Cancelled, Rescheduled, Scheduled, No-Show"""
        valid_statuses = ['Confirmed', 'Pending', 'Completed', 'Cancelled', 'Rescheduled', 'Scheduled', 'No-Show']
        if new_status not in valid_statuses:
            return False
            
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
            UPDATE sih_appointments 
            SET status = ?, updated_at = CURRENT_TIMESTAMP 
            WHERE appointment_id = ?
            """, (new_status, appointment_id))
            affected = c.rowcount
            conn.commit()
            
        return affected > 0

    @staticmethod
    def reschedule_appointment(
        appointment_id: str,
        new_appointment_time: str,
        new_time_slot: str,
        db_path: str = DB_PATH
    ) -> Dict[str, Any]:
        """Reschedules an appointment to a new date and time slot."""
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT patient_id FROM sih_appointments WHERE appointment_id = ?", (appointment_id,))
            row = c.fetchone()
            if not row:
                return {"success": False, "error": "Appointment not found"}
                
            patient_id = row[0]
            # Check conflict
            c.execute("""
            SELECT appointment_id FROM sih_appointments
            WHERE patient_id = ? AND appointment_time = ? AND appointment_id != ? AND status IN ('Scheduled', 'Confirmed', 'Pending')
            """, (patient_id, new_appointment_time, appointment_id))
            if c.fetchone():
                return {"success": False, "error": "Patient already has another appointment booked at this new time."}

            c.execute("""
            UPDATE sih_appointments
            SET appointment_time = ?, time_slot = ?, status = 'Confirmed', updated_at = CURRENT_TIMESTAMP
            WHERE appointment_id = ?
            """, (new_appointment_time, new_time_slot, appointment_id))
            conn.commit()

        return {"success": True, "message": f"Appointment successfully rescheduled to {new_appointment_time} ({new_time_slot})."}

    @staticmethod
    def cancel_appointment(appointment_id: str, db_path: str = DB_PATH) -> Dict[str, Any]:
        """Cancels an appointment."""
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
            UPDATE sih_appointments
            SET status = 'Cancelled', updated_at = CURRENT_TIMESTAMP
            WHERE appointment_id = ?
            """, (appointment_id,))
            affected = c.rowcount
            conn.commit()

        if affected > 0:
            return {"success": True, "message": "Appointment cancelled successfully."}
        return {"success": False, "error": "Appointment not found"}

    @staticmethod
    def list_patient_appointments(patient_id: str, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
            SELECT a.appointment_id, a.patient_id, a.facility_id, a.doctor_id, a.doctor_name,
                   a.consultation_type, a.reason, a.time_slot, a.pregnancy_week, a.trimester,
                   a.reminder_enabled, a.appointment_time, a.status, a.created_at, a.updated_at,
                   f.name, f.type, f.address, f.contact_number
            FROM sih_appointments a
            LEFT JOIN sih_facilities f ON a.facility_id = f.facility_id
            WHERE a.patient_id = ?
            ORDER BY a.appointment_time DESC
            """, (patient_id,))
            rows = c.fetchall()
            
        return [
            {
                "appointment_id": r[0],
                "patient_id": r[1],
                "facility_id": r[2],
                "doctor_id": r[3],
                "doctor_name": r[4] or "Medical Officer / Specialist",
                "consultation_type": r[5] or "In-Person",
                "reason": r[6] or "Antenatal Checkup",
                "time_slot": r[7] or "09:00 AM - 10:00 AM",
                "pregnancy_week": r[8],
                "trimester": r[9] or "",
                "reminder_enabled": bool(r[10]),
                "appointment_time": r[11],
                "status": r[12] or "Confirmed",
                "created_at": r[13],
                "updated_at": r[14],
                "facility_name": r[15] or r[2],
                "facility_type": r[16] or "",
                "facility_address": r[17] or "",
                "facility_contact": r[18] or ""
            } for r in rows
        ]

    @staticmethod
    def list_facility_appointments(facility_id: str, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
            SELECT a.appointment_id, a.patient_id, a.facility_id, a.doctor_id, a.doctor_name,
                   a.consultation_type, a.reason, a.time_slot, a.pregnancy_week, a.trimester,
                   a.reminder_enabled, a.appointment_time, a.status, a.created_at, a.updated_at,
                   f.name, f.type, f.address, f.contact_number
            FROM sih_appointments a
            LEFT JOIN sih_facilities f ON a.facility_id = f.facility_id
            WHERE a.facility_id = ?
            ORDER BY a.appointment_time DESC
            """, (facility_id,))
            rows = c.fetchall()
            
        return [
            {
                "appointment_id": r[0],
                "patient_id": r[1],
                "facility_id": r[2],
                "doctor_id": r[3],
                "doctor_name": r[4] or "Medical Officer / Specialist",
                "consultation_type": r[5] or "In-Person",
                "reason": r[6] or "Antenatal Checkup",
                "time_slot": r[7] or "09:00 AM - 10:00 AM",
                "pregnancy_week": r[8],
                "trimester": r[9] or "",
                "reminder_enabled": bool(r[10]),
                "appointment_time": r[11],
                "status": r[12] or "Confirmed",
                "created_at": r[13],
                "updated_at": r[14],
                "facility_name": r[15] or r[2],
                "facility_type": r[16] or "",
                "facility_address": r[17] or "",
                "facility_contact": r[18] or ""
            } for r in rows
        ]

