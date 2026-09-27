import unittest
import os
import tempfile
from sih_extensions.sih_database import init_sih_db
from sih_extensions.facility_directory import FacilityDirectory
from sih_extensions.teleconsultation_service import TeleconsultationService, DemoTeleconsultationProvider

class TestTeleconsultationService(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        init_sih_db(db_path=self.db_path)
        FacilityDirectory.seed_demo_data(db_path=self.db_path)
        # Ensure provider is demo
        TeleconsultationService.set_provider(DemoTeleconsultationProvider())

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_create_and_get_consultation(self):
        res = TeleconsultationService.create_request(
            patient_id="PAT-001",
            requesting_user_id="ASHA-101",
            facility_id="FAC-DEMO-001",
            reason="High fever and chills",
            db_path=self.db_path
        )
        self.assertTrue(res["success"])
        cid = res["consultation_id"]
        
        c = TeleconsultationService.get_consultation(cid, db_path=self.db_path)
        self.assertEqual(c["status"], "REQUESTED")
        self.assertEqual(c["patient_id"], "PAT-001")
        
    def test_invalid_facility(self):
        res = TeleconsultationService.create_request(
            patient_id="PAT-001",
            requesting_user_id="ASHA-101",
            facility_id="INVALID_FACILITY",
            reason="Test",
            db_path=self.db_path
        )
        self.assertFalse(res["success"])
        self.assertIn("Invalid", res["error"])

    def test_provider_workflow(self):
        res = TeleconsultationService.create_request("PAT-001", "ASHA-1", "FAC-DEMO-001", "Fever", db_path=self.db_path)
        cid = res["consultation_id"]
        
        # Test accept (provider queue simulation)
        acc = TeleconsultationService.accept_consultation(cid, "DOC-1", db_path=self.db_path)
        self.assertTrue(acc["success"])
        self.assertIn("session_info", acc)
        self.assertIn("DEMO", acc["session_info"]["message"])
        
        c = TeleconsultationService.get_consultation(cid, db_path=self.db_path)
        self.assertEqual(c["status"], "ACCEPTED")
        self.assertIsNotNone(c["meeting_url"])
        
        # Test start
        self.assertTrue(TeleconsultationService.start_consultation(cid, db_path=self.db_path))
        c = TeleconsultationService.get_consultation(cid, db_path=self.db_path)
        self.assertEqual(c["status"], "IN_PROGRESS")
        
        # Test notes
        self.assertTrue(TeleconsultationService.record_consultation_notes(cid, "Patient looks fine", "Drink fluids", db_path=self.db_path))
        c = TeleconsultationService.get_consultation(cid, db_path=self.db_path)
        self.assertEqual(c["advice"], "Drink fluids")
        
        # Test completion
        self.assertTrue(TeleconsultationService.complete_consultation(cid, db_path=self.db_path))
        c = TeleconsultationService.get_consultation(cid, db_path=self.db_path)
        self.assertEqual(c["status"], "COMPLETED")

    def test_state_transitions(self):
        res = TeleconsultationService.create_request("PAT-001", "ASHA-1", "FAC-DEMO-001", "Test", db_path=self.db_path)
        cid = res["consultation_id"]
        
        # Reject
        self.assertTrue(TeleconsultationService.reject_consultation(cid, "Unavailable", db_path=self.db_path))
        c = TeleconsultationService.get_consultation(cid, db_path=self.db_path)
        self.assertEqual(c["status"], "REJECTED")
        self.assertEqual(c["notes"], "Unavailable")
        
        # Cannot accept if rejected (invalid state transition)
        acc = TeleconsultationService.accept_consultation(cid, "DOC-1", db_path=self.db_path)
        self.assertFalse(acc["success"])

    def test_lists(self):
        TeleconsultationService.create_request("PAT-1", "ASHA-1", "FAC-DEMO-001", "Headache", db_path=self.db_path)
        TeleconsultationService.create_request("PAT-1", "ASHA-1", "FAC-DEMO-001", "Fever", db_path=self.db_path)
        
        patient_cons = TeleconsultationService.list_patient_consultations("PAT-1", db_path=self.db_path)
        self.assertEqual(len(patient_cons), 2)
        
        pending = TeleconsultationService.list_pending_requests("FAC-DEMO-001", db_path=self.db_path)
        self.assertEqual(len(pending), 2)
        
        # Accept one
        cid = pending[0]["consultation_id"]
        TeleconsultationService.accept_consultation(cid, "DOC-XYZ", db_path=self.db_path)
        
        prov_cons = TeleconsultationService.list_provider_consultations("DOC-XYZ", db_path=self.db_path)
        self.assertEqual(len(prov_cons), 1)
        self.assertEqual(prov_cons[0]["consultation_id"], cid)

    def test_no_show_and_cancel(self):
        res = TeleconsultationService.create_request("PAT-2", "ASHA-1", "FAC-DEMO-001", "Checkup", db_path=self.db_path)
        cid = res["consultation_id"]
        
        # Cancel requested
        self.assertTrue(TeleconsultationService.cancel_consultation(cid, "Patient changed mind", db_path=self.db_path))
        c = TeleconsultationService.get_consultation(cid, db_path=self.db_path)
        self.assertEqual(c["status"], "CANCELLED")

        res2 = TeleconsultationService.create_request("PAT-3", "ASHA-1", "FAC-DEMO-001", "Checkup", db_path=self.db_path)
        cid2 = res2["consultation_id"]
        TeleconsultationService.accept_consultation(cid2, "DOC-1", db_path=self.db_path)
        
        # Mark no show
        self.assertTrue(TeleconsultationService.mark_no_show(cid2, db_path=self.db_path))
        c2 = TeleconsultationService.get_consultation(cid2, db_path=self.db_path)
        self.assertEqual(c2["status"], "NO_SHOW")

    def test_demo_provider_semantics(self):
        provider = DemoTeleconsultationProvider()
        sess = provider.create_session("CONS-123")
        self.assertTrue(sess["success"])
        self.assertIn("DEMO TELECONSULTATION", sess["message"])
        self.assertIn("demo-session-CONS-123", sess["session_id"])
        
        status = provider.session_status(sess["session_id"])
        self.assertEqual(status, "ACTIVE")
