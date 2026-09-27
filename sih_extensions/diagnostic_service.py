"""
SIH Diagnostic Availability Service.
"""
import os
import json
from typing import List, Dict, Any, Optional
from .sih_database import get_sih_connection, init_sih_db, DB_PATH
from .facility_directory import FacilityDirectory

class DiagnosticService:
    @staticmethod
    def get_diagnostic(item_id: str, facility_id: str, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT item_id, item_name, category, department, status, source, verification_status, active, last_updated
                FROM sih_inventory 
                WHERE item_type = 'DIAGNOSTIC' AND item_id = ? AND facility_id = ?
            """, (item_id, facility_id))
            r = c.fetchone()
            if r:
                return {
                    "item_id": r[0], "item_name": r[1], "category": r[2], "department": r[3], "status": r[4],
                    "source": r[5], "verification_status": r[6], "active": bool(r[7]), "last_updated": r[8]
                }
        return None

    @staticmethod
    def create_or_update_diagnostic(facility_id: str, item_id: str, item_name: str, category: str, department: str, status: str = "UNKNOWN", source: str = "DEMO", db_path: str = DB_PATH) -> Dict[str, Any]:
        fac = FacilityDirectory.get_facility(facility_id, db_path)
        if not fac:
            return {"success": False, "error": "Invalid facility"}

        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("SELECT id FROM sih_inventory WHERE item_type = 'DIAGNOSTIC' AND item_id = ? AND facility_id = ?", (item_id, facility_id))
            row = c.fetchone()
            if row:
                c.execute("""
                    UPDATE sih_inventory 
                    SET item_name = ?, category = ?, department = ?, status = ?, source = ?, last_updated = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (item_name, category, department, status, source, row[0]))
            else:
                c.execute("""
                    INSERT INTO sih_inventory (
                        facility_id, item_type, item_id, item_name, category, department, status, source, verification_status, active
                    ) VALUES (?, 'DIAGNOSTIC', ?, ?, ?, ?, ?, ?, 'UNVERIFIED', 1)
                """, (facility_id, item_id, item_name, category, department, status, source))
            conn.commit()
        return {"success": True}

    @staticmethod
    def get_facility_diagnostics(facility_id: str, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT item_id, item_name, category, department, status, last_updated 
                FROM sih_inventory 
                WHERE item_type = 'DIAGNOSTIC' AND facility_id = ? AND active = 1
                ORDER BY item_name ASC
            """, (facility_id,))
            return [{"item_id": r[0], "item_name": r[1], "category": r[2], "department": r[3], "status": r[4], "last_updated": r[5]} for r in c.fetchall()]

    @staticmethod
    def search_diagnostic(query: str, facility_id: str = None, category: str = None, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            sql = """
                SELECT facility_id, item_id, item_name, category, department, status, last_updated 
                FROM sih_inventory 
                WHERE item_type = 'DIAGNOSTIC' AND active = 1 AND item_name LIKE ?
            """
            params = [f"%{query}%"]
            if facility_id:
                sql += " AND facility_id = ?"
                params.append(facility_id)
            if category:
                sql += " AND category = ?"
                params.append(category)
            c.execute(sql, tuple(params))
            return [{"facility_id": r[0], "item_id": r[1], "item_name": r[2], "category": r[3], "department": r[4], "status": r[5], "last_updated": r[6]} for r in c.fetchall()]

    @staticmethod
    def update_availability(item_id: str, facility_id: str, status: str, db_path: str = DB_PATH) -> bool:
        valid = ['AVAILABLE', 'LIMITED', 'UNAVAILABLE', 'UNKNOWN']
        if status not in valid:
            return False
            
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE sih_inventory 
                SET status = ?, last_updated = CURRENT_TIMESTAMP
                WHERE item_type = 'DIAGNOSTIC' AND item_id = ? AND facility_id = ?
            """, (status, item_id, facility_id))
            affected = c.rowcount
            conn.commit()
            return affected > 0

    @staticmethod
    def deactivate_diagnostic(item_id: str, facility_id: str, db_path: str = DB_PATH) -> bool:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE sih_inventory 
                SET active = 0, last_updated = CURRENT_TIMESTAMP
                WHERE item_type = 'DIAGNOSTIC' AND item_id = ? AND facility_id = ?
            """, (item_id, facility_id))
            affected = c.rowcount
            conn.commit()
            return affected > 0

    @staticmethod
    def seed_default_diagnostics(patient_id: str = "001", db_path: str = DB_PATH):
        """Seeds standard maternal diagnostic tests for demonstration."""
        init_sih_db(db_path=db_path)
        demo_tests = [
            {
                "test_id": "TEST-2026-USG01",
                "patient_id": patient_id,
                "test_name": "[Demo Data] Obstetric Ultrasound - Level II Anomaly & Fetal Anatomy Scan",
                "reason": "Detailed evaluation of fetal anatomical structures, amniotic fluid index (AFI), and placental location at 18-22 weeks",
                "recommended_date": "2026-10-05",
                "status": "Pending",
                "doctor_name": "[Demo Data] Dr. Kavitha Reddy (Consultant OB/GYN)",
                "facility_id": "FAC-CHC-001",
                "facility_name": "[SAMPLE DATA] Medchal Community Health Centre (CHC)",
                "report_file_name": "",
                "result_summary": "Scheduled examination. High-frequency 2D/3D obstetric ultrasound scan.",
                "completed_date": None
            },
            {
                "test_id": "TEST-2026-CBC02",
                "patient_id": patient_id,
                "test_name": "[Demo Data] Complete Blood Count (CBC) & Hemoglobin Profile",
                "reason": "Routine 2nd trimester anemia screening & platelet count assessment",
                "recommended_date": "2026-09-28",
                "status": "Scheduled",
                "doctor_name": "[Demo Data] Dr. Anita Sharma (Medical Officer)",
                "facility_id": "FAC-DEMO-002",
                "facility_name": "[SAMPLE DATA] Shamirpet Primary Health Centre (PHC)",
                "report_file_name": "",
                "result_summary": "Sample collection scheduled for morning OPD hours.",
                "completed_date": None
            },
            {
                "test_id": "TEST-2026-OGTT03",
                "patient_id": patient_id,
                "test_name": "[Demo Data] Oral Glucose Tolerance Test (OGTT - 75g Single Step)",
                "reason": "Screening for gestational diabetes mellitus (GDM) at 24-28 weeks",
                "recommended_date": "2026-10-12",
                "status": "Pending",
                "doctor_name": "[Demo Data] Dr. Kavitha Reddy (Consultant OB/GYN)",
                "facility_id": "FAC-LAB-001",
                "facility_name": "[SAMPLE DATA] Telangana Diagnostics Central Pathology & Imaging Lab",
                "report_file_name": "",
                "result_summary": "Standard 2-hour 75g oral glucose tolerance test.",
                "completed_date": None
            },
            {
                "test_id": "TEST-2026-NT04",
                "patient_id": patient_id,
                "test_name": "[Demo Data] 1st Trimester NT/NB Dating Ultrasound Scan",
                "reason": "Gestational age confirmation, nuchal translucency (NT) measurement, and early growth check",
                "recommended_date": "2026-07-15",
                "status": "Completed",
                "doctor_name": "[Demo Data] Dr. Arun Nair (Consultant Radiologist)",
                "facility_id": "FAC-DEMO-001",
                "facility_name": "[SAMPLE DATA] District General Hospital - Maternal & Trauma Wing",
                "report_file_name": "maternal_scan_trimester1_verified_report.pdf",
                "result_summary": "Single intrauterine viable fetus. CRL corresponds to 12w4d. NT: 1.3 mm (Normal < 2.5 mm). Nasal bone visualized. Fetal heart rate: 154 bpm. Normal anatomical survey.",
                "completed_date": "2026-07-15"
            },
            {
                "test_id": "TEST-2026-BLD05",
                "patient_id": patient_id,
                "test_name": "[Demo Data] Baseline Blood Grouping (ABO/Rh) & Maternal Serology Screen",
                "reason": "Baseline prenatal blood typing and infectious disease screening",
                "recommended_date": "2026-06-20",
                "status": "Completed",
                "doctor_name": "[Demo Data] Dr. Anita Sharma (Medical Officer)",
                "facility_id": "FAC-DEMO-002",
                "facility_name": "[SAMPLE DATA] Shamirpet Primary Health Centre (PHC)",
                "report_file_name": "maternal_blood_group_serology_report.pdf",
                "result_summary": "Blood Group: B Positive (Rh +ve). Hemoglobin (Hb): 11.2 g/dL. HIV: Non-Reactive. HBsAg: Negative. VDRL: Non-Reactive. Urine Albumin: Nil.",
                "completed_date": "2026-06-20"
            }
        ]

        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            for t in demo_tests:
                c.execute("SELECT id FROM sih_diagnostics_records WHERE test_id = ?", (t['test_id'],))
                if c.fetchone() is None:
                    c.execute("""
                        INSERT INTO sih_diagnostics_records (
                            test_id, patient_id, test_name, reason, recommended_date,
                            status, doctor_name, facility_id, facility_name,
                            report_file_name, result_summary, completed_date
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        t['test_id'], t['patient_id'], t['test_name'], t['reason'], t['recommended_date'],
                        t['status'], t['doctor_name'], t['facility_id'], t['facility_name'],
                        t['report_file_name'], t['result_summary'], t['completed_date']
                    ))
            conn.commit()

    @staticmethod
    def list_patient_diagnostics(patient_id: str, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
        DiagnosticService.seed_default_diagnostics(patient_id=patient_id, db_path=db_path)
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT test_id, patient_id, test_name, reason, recommended_date,
                       status, doctor_name, facility_id, facility_name,
                       report_file_name, result_summary, completed_date, created_at
                FROM sih_diagnostics_records WHERE patient_id = ?
                ORDER BY CASE status WHEN 'Pending' THEN 1 WHEN 'Scheduled' THEN 2 ELSE 3 END, recommended_date DESC
            """, (patient_id,))
            rows = c.fetchall()

        return [
            {
                "test_id": r[0],
                "patient_id": r[1],
                "test_name": r[2],
                "reason": r[3] or "",
                "recommended_date": r[4] or "",
                "status": r[5] or "Pending",
                "doctor_name": r[6] or "Medical Officer",
                "facility_id": r[7] or "",
                "facility_name": r[8] or "Community Diagnostic Center",
                "report_file_name": r[9] or "",
                "result_summary": r[10] or "",
                "completed_date": r[11] or "",
                "created_at": r[12]
            } for r in rows
        ]

    @staticmethod
    def update_diagnostic_status(test_id: str, new_status: str, result_summary: str = None, db_path: str = DB_PATH) -> bool:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            if result_summary is not None:
                c.execute("UPDATE sih_diagnostics_records SET status = ?, result_summary = ? WHERE test_id = ?", (new_status, result_summary, test_id))
            else:
                c.execute("UPDATE sih_diagnostics_records SET status = ? WHERE test_id = ?", (new_status, test_id))
            affected = c.rowcount
            conn.commit()
            return affected > 0

    @staticmethod
    def upload_diagnostic_report(test_id: str, report_file_name: str, result_summary: str, db_path: str = DB_PATH) -> bool:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE sih_diagnostics_records 
                SET report_file_name = ?, result_summary = ?, status = 'Completed', completed_date = CURRENT_DATE 
                WHERE test_id = ?
            """, (report_file_name, result_summary, test_id))
            affected = c.rowcount
            conn.commit()
            return affected > 0

    @staticmethod
    def seed_demo_data(db_path: str = DB_PATH):
        json_path = os.path.join(os.path.dirname(__file__), "data", "diagnostics.json")
        if not os.path.exists(json_path):
            return
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for diag in data:
            DiagnosticService.create_or_update_diagnostic(
                facility_id=diag["facility_id"],
                item_id=diag["item_id"],
                item_name=diag["item_name"],
                category=diag.get("category", "General"),
                department=diag.get("department", "Radiology/Pathology"),
                status=diag.get("status", "AVAILABLE"),
                source="DEMO",
                db_path=db_path
            )
        DiagnosticService.seed_default_diagnostics(db_path=db_path)

