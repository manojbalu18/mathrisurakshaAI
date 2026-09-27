import unittest
import os
import tempfile
from sih_extensions.sih_database import init_sih_db
from sih_extensions.facility_directory import FacilityDirectory
from sih_extensions.appointment_service import AppointmentService

class TestAppointmentService(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        init_sih_db(db_path=self.db_path)
        FacilityDirectory.seed_demo_data(db_path=self.db_path)

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_create_and_get_appointment(self):
        # Valid creation
        res = AppointmentService.create_appointment("PAT-001", "FAC-DEMO-001", "2026-10-10 10:00:00", db_path=self.db_path)
        self.assertTrue(res["success"])
        app_id = res["appointment_id"]
        
        # Get appointment
        app = AppointmentService.get_appointment(app_id, db_path=self.db_path)
        self.assertIsNotNone(app)
        self.assertEqual(app["patient_id"], "PAT-001")
        self.assertEqual(app["status"], "Scheduled")

    def test_duplicate_booking_protection(self):
        res1 = AppointmentService.create_appointment("PAT-002", "FAC-DEMO-001", "2026-10-10 10:00:00", db_path=self.db_path)
        self.assertTrue(res1["success"])
        
        # Conflict for same patient and time
        res2 = AppointmentService.create_appointment("PAT-002", "FAC-DEMO-002", "2026-10-10 10:00:00", db_path=self.db_path)
        self.assertFalse(res2["success"])
        self.assertIn("conflicting", res2["error"])

    def test_invalid_facility(self):
        res = AppointmentService.create_appointment("PAT-001", "INVALID_FAC", "2026-10-10 10:00:00", db_path=self.db_path)
        self.assertFalse(res["success"])
        self.assertIn("Invalid facility", res["error"])

    def test_update_status(self):
        res = AppointmentService.create_appointment("PAT-003", "FAC-DEMO-001", "2026-10-10 10:00:00", db_path=self.db_path)
        app_id = res["appointment_id"]
        
        # Update valid status
        success = AppointmentService.update_status(app_id, "Confirmed", db_path=self.db_path)
        self.assertTrue(success)
        app = AppointmentService.get_appointment(app_id, db_path=self.db_path)
        self.assertEqual(app["status"], "Confirmed")
        
        # Update invalid status
        success = AppointmentService.update_status(app_id, "MagicStatus", db_path=self.db_path)
        self.assertFalse(success)

    def test_list_appointments(self):
        AppointmentService.create_appointment("PAT-004", "FAC-DEMO-001", "2026-10-10 10:00:00", db_path=self.db_path)
        AppointmentService.create_appointment("PAT-004", "FAC-DEMO-002", "2026-10-11 10:00:00", db_path=self.db_path)
        
        pat_apps = AppointmentService.list_patient_appointments("PAT-004", db_path=self.db_path)
        self.assertEqual(len(pat_apps), 2)
        
        fac_apps = AppointmentService.list_facility_appointments("FAC-DEMO-001", db_path=self.db_path)
        self.assertEqual(len(fac_apps), 1)
