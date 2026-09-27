"""
SIH Medicine Availability Service.
"""
import uuid
import json
import os
from typing import List, Dict, Any, Optional
from .sih_database import get_sih_connection, init_sih_db, DB_PATH
from .facility_directory import FacilityDirectory

class MedicineService:
    @staticmethod
    def get_medicine(item_id: str, facility_id: str, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT item_id, item_name, generic_name, quantity, status, unit, source, verification_status, active, last_updated
                FROM sih_inventory 
                WHERE item_type = 'MEDICINE' AND item_id = ? AND facility_id = ?
            """, (item_id, facility_id))
            r = c.fetchone()
            if r:
                return {
                    "item_id": r[0], "item_name": r[1], "generic_name": r[2], "quantity": r[3], "status": r[4],
                    "unit": r[5], "source": r[6], "verification_status": r[7], "active": bool(r[8]), "last_updated": r[9]
                }
        return None

    @staticmethod
    def create_or_update_medicine(facility_id: str, item_id: str, item_name: str, generic_name: str, quantity: int, unit: str, source: str = "DEMO", db_path: str = DB_PATH) -> Dict[str, Any]:
        fac = FacilityDirectory.get_facility(facility_id, db_path)
        if not fac:
            return {"success": False, "error": "Invalid facility"}

        status = "UNKNOWN"
        if quantity > 50:
            status = "IN_STOCK"
        elif quantity > 0:
            status = "LOW_STOCK"
        else:
            status = "OUT_OF_STOCK"

        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT id FROM sih_inventory WHERE item_type = 'MEDICINE' AND item_id = ? AND facility_id = ?", (item_id, facility_id))
            row = c.fetchone()
            if row:
                c.execute("""
                    UPDATE sih_inventory 
                    SET item_name = ?, generic_name = ?, quantity = ?, unit = ?, status = ?, source = ?, last_updated = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (item_name, generic_name, quantity, unit, status, source, row[0]))
            else:
                c.execute("""
                    INSERT INTO sih_inventory (
                        facility_id, item_type, item_id, item_name, generic_name, quantity, unit, status, source, verification_status, active
                    ) VALUES (?, 'MEDICINE', ?, ?, ?, ?, ?, ?, ?, 'UNVERIFIED', 1)
                """, (facility_id, item_id, item_name, generic_name, quantity, unit, status, source))
            conn.commit()
        return {"success": True, "status": status}
        
    @staticmethod
    def get_facility_inventory(facility_id: str, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT item_id, item_name, generic_name, quantity, status, unit, last_updated 
                FROM sih_inventory 
                WHERE item_type = 'MEDICINE' AND facility_id = ? AND active = 1
                ORDER BY item_name ASC
            """, (facility_id,))
            return [{"item_id": r[0], "item_name": r[1], "generic_name": r[2], "quantity": r[3], "status": r[4], "unit": r[5], "last_updated": r[6]} for r in c.fetchall()]

    @staticmethod
    def search_medicine(query: str, facility_id: str = None, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            sql = """
                SELECT facility_id, item_id, item_name, generic_name, quantity, status, unit, last_updated 
                FROM sih_inventory 
                WHERE item_type = 'MEDICINE' AND active = 1 AND (item_name LIKE ? OR generic_name LIKE ?)
            """
            params = [f"%{query}%", f"%{query}%"]
            if facility_id:
                sql += " AND facility_id = ?"
                params.append(facility_id)
            c.execute(sql, tuple(params))
            return [{"facility_id": r[0], "item_id": r[1], "item_name": r[2], "generic_name": r[3], "quantity": r[4], "status": r[5], "unit": r[6], "last_updated": r[7]} for r in c.fetchall()]

    @staticmethod
    def update_quantity(item_id: str, facility_id: str, quantity: int, db_path: str = DB_PATH) -> bool:
        status = "UNKNOWN"
        if quantity > 50:
            status = "IN_STOCK"
        elif quantity > 0:
            status = "LOW_STOCK"
        else:
            status = "OUT_OF_STOCK"
            
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE sih_inventory 
                SET quantity = ?, status = ?, last_updated = CURRENT_TIMESTAMP
                WHERE item_type = 'MEDICINE' AND item_id = ? AND facility_id = ?
            """, (quantity, status, item_id, facility_id))
            affected = c.rowcount
            conn.commit()
            return affected > 0

    @staticmethod
    def deactivate_medicine(item_id: str, facility_id: str, db_path: str = DB_PATH) -> bool:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE sih_inventory 
                SET active = 0, last_updated = CURRENT_TIMESTAMP
                WHERE item_type = 'MEDICINE' AND item_id = ? AND facility_id = ?
            """, (item_id, facility_id))
            affected = c.rowcount
            conn.commit()
            return affected > 0

    @staticmethod
    def seed_default_prescriptions(patient_id: str = "001", db_path: str = DB_PATH):
        """Seeds standard maternal prescriptions for demonstration."""
        init_sih_db(db_path=db_path)
        demo_prescriptions = [
            {
                "prescription_id": "RX-2026-IFA01",
                "patient_id": patient_id,
                "medicine_name": "[Demo Data] Iron & Folic Acid (IFA) Tablets (Red)",
                "purpose": "Prevention and treatment of maternal anemia & fetal neural tube development",
                "dosage": "100mg Elemental Iron + 500mcg Folic Acid",
                "frequency": "Once Daily (OD)",
                "duration": "180 Days (Throughout 2nd & 3rd Trimester)",
                "food_instruction": "Take after lunch with water or lemon juice. Do NOT take with tea, coffee, or milk.",
                "schedule_time": "01:30 PM",
                "taken_status": "Pending",
                "doctor_name": "[Demo Data] Dr. Anita Sharma (Medical Officer - MBBS)",
                "facility_name": "[SAMPLE DATA] Shamirpet Primary Health Centre (PHC)",
                "prescribed_date": "2026-09-15",
                "is_current": 1
            },
            {
                "prescription_id": "RX-2026-CAL02",
                "patient_id": patient_id,
                "medicine_name": "[Demo Data] Calcium & Vitamin D3 Tablets",
                "purpose": "Fetal bone & teeth mineralization, maternal skeletal strength, prevention of pre-eclampsia",
                "dosage": "500mg Elemental Calcium + 250 IU Vitamin D3",
                "frequency": "Twice Daily (BD)",
                "duration": "180 Days",
                "food_instruction": "Take after breakfast and after dinner with water. Keep a 2-hour gap from Iron tablets.",
                "schedule_time": "08:30 AM & 08:30 PM",
                "taken_status": "Taken",
                "doctor_name": "[Demo Data] Dr. Anita Sharma (Medical Officer - MBBS)",
                "facility_name": "[SAMPLE DATA] Shamirpet Primary Health Centre (PHC)",
                "prescribed_date": "2026-09-15",
                "is_current": 1
            },
            {
                "prescription_id": "RX-2026-MV03",
                "patient_id": patient_id,
                "medicine_name": "[Demo Data] Maternal Micronutrient & Multivitamin Complex",
                "purpose": "Essential trace vitamins, zinc, and minerals for healthy gestational growth",
                "dosage": "1 Capsule Daily",
                "frequency": "Once Daily (OD)",
                "duration": "90 Days",
                "food_instruction": "Take with morning breakfast.",
                "schedule_time": "09:00 AM",
                "taken_status": "Pending",
                "doctor_name": "[Demo Data] Dr. Kavitha Reddy (Consultant OB/GYN)",
                "facility_name": "[SAMPLE DATA] Medchal Community Health Centre (CHC)",
                "prescribed_date": "2026-09-20",
                "is_current": 1
            },
            {
                "prescription_id": "RX-2026-FA04",
                "patient_id": patient_id,
                "medicine_name": "[Demo Data] Folic Acid (5mg) First Trimester Tablets",
                "purpose": "Pre-conception and 1st trimester neural tube defect prevention",
                "dosage": "5mg",
                "frequency": "Once Daily (OD)",
                "duration": "90 Days (Completed at 12 Weeks)",
                "food_instruction": "Take after breakfast with water.",
                "schedule_time": "09:00 AM",
                "taken_status": "Completed",
                "doctor_name": "[Demo Data] Dr. Anita Sharma (Medical Officer)",
                "facility_name": "[SAMPLE DATA] Shamirpet Primary Health Centre (PHC)",
                "prescribed_date": "2026-06-10",
                "is_current": 0
            }
        ]

        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            for p in demo_prescriptions:
                c.execute("SELECT id FROM sih_prescriptions WHERE prescription_id = ?", (p['prescription_id'],))
                if c.fetchone() is None:
                    c.execute("""
                        INSERT INTO sih_prescriptions (
                            prescription_id, patient_id, medicine_name, purpose, dosage,
                            frequency, duration, food_instruction, schedule_time, taken_status,
                            doctor_name, facility_name, prescribed_date, is_current
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        p['prescription_id'], p['patient_id'], p['medicine_name'], p['purpose'], p['dosage'],
                        p['frequency'], p['duration'], p['food_instruction'], p['schedule_time'], p['taken_status'],
                        p['doctor_name'], p['facility_name'], p['prescribed_date'], p['is_current']
                    ))
            conn.commit()

    @staticmethod
    def list_patient_prescriptions(patient_id: str, is_current: Optional[int] = None, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
        MedicineService.seed_default_prescriptions(patient_id=patient_id, db_path=db_path)
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            query = """
                SELECT prescription_id, patient_id, medicine_name, purpose, dosage,
                       frequency, duration, food_instruction, schedule_time, taken_status,
                       doctor_name, facility_name, prescribed_date, is_current, created_at
                FROM sih_prescriptions WHERE patient_id = ?
            """
            params = [patient_id]
            if is_current is not None:
                query += " AND is_current = ?"
                params.append(is_current)
            query += " ORDER BY is_current DESC, prescribed_date DESC"
            c.execute(query, tuple(params))
            rows = c.fetchall()

        return [
            {
                "prescription_id": r[0],
                "patient_id": r[1],
                "medicine_name": r[2],
                "purpose": r[3] or "",
                "dosage": r[4] or "",
                "frequency": r[5] or "",
                "duration": r[6] or "",
                "food_instruction": r[7] or "",
                "schedule_time": r[8] or "",
                "taken_status": r[9] or "Pending",
                "doctor_name": r[10] or "Medical Officer",
                "facility_name": r[11] or "Primary Health Centre",
                "prescribed_date": r[12] or "",
                "is_current": bool(r[13]),
                "created_at": r[14]
            } for r in rows
        ]

    @staticmethod
    def update_taken_status(prescription_id: str, new_status: str, db_path: str = DB_PATH) -> bool:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("UPDATE sih_prescriptions SET taken_status = ? WHERE prescription_id = ?", (new_status, prescription_id))
            affected = c.rowcount
            conn.commit()
            return affected > 0

    @staticmethod
    def seed_demo_data(db_path: str = DB_PATH):
        json_path = os.path.join(os.path.dirname(__file__), "data", "medicines.json")
        if not os.path.exists(json_path):
            return
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for med in data:
            MedicineService.create_or_update_medicine(
                facility_id=med["facility_id"],
                item_id=med["item_id"],
                item_name=med["item_name"],
                generic_name=med["generic_name"],
                quantity=med["quantity"],
                unit=med["unit"],
                source="DEMO",
                db_path=db_path
            )
        MedicineService.seed_default_prescriptions(db_path=db_path)

