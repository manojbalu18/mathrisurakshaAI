import unittest
import os
import tempfile
from sih_extensions.sih_database import init_sih_db
from sih_extensions.facility_directory import FacilityDirectory
from sih_extensions.referral_service import ReferralService

class TestReferralService(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        init_sih_db(db_path=self.db_path)
        FacilityDirectory.seed_demo_data(db_path=self.db_path)

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_create_and_get_referral(self):
        res = ReferralService.create_referral(
            "PAT-001", "FAC-DEMO-002", "FAC-DEMO-001", "Requires specialized scan", db_path=self.db_path
        )
        self.assertTrue(res["success"])
        ref_id = res["referral_id"]
        
        ref = ReferralService.get_referral(ref_id, db_path=self.db_path)
        self.assertEqual(ref["patient_id"], "PAT-001")
        self.assertEqual(ref["status"], "REFERRAL_CREATED")
        
    def test_invalid_destination_facility(self):
        res = ReferralService.create_referral(
            "PAT-001", "FAC-DEMO-002", "INVALID_FAC", "Test", db_path=self.db_path
        )
        self.assertFalse(res["success"])
        self.assertIn("Invalid", res["error"])

    def test_referral_flow_and_linkage(self):
        res = ReferralService.create_referral(
            "PAT-001", "FAC-DEMO-002", "FAC-DEMO-001", "Test", db_path=self.db_path
        )
        ref_id = res["referral_id"]
        
        ReferralService.update_status(ref_id, "ACCEPTED", "We can see them today", db_path=self.db_path)
        ref = ReferralService.get_referral(ref_id, db_path=self.db_path)
        self.assertEqual(ref["status"], "ACCEPTED")
        self.assertIsNotNone(ref["accepted_at"])
        
        ReferralService.link_appointment(ref_id, "APP-123", db_path=self.db_path)
        ref = ReferralService.get_referral(ref_id, db_path=self.db_path)
        self.assertEqual(ref["status"], "APPOINTMENT_CREATED")
        self.assertEqual(ref["appointment_id"], "APP-123")
        
        ReferralService.link_queue(ref_id, "Q-123", db_path=self.db_path)
        ref = ReferralService.get_referral(ref_id, db_path=self.db_path)
        self.assertEqual(ref["status"], "CHECKED_IN")

    def test_list_incoming(self):
        ReferralService.create_referral("PAT-1", "FAC-DEMO-002", "FAC-DEMO-001", "Reason 1", db_path=self.db_path)
        ReferralService.create_referral("PAT-2", "FAC-DEMO-002", "FAC-DEMO-001", "Reason 2", db_path=self.db_path)
        
        incoming = ReferralService.list_incoming_referrals("FAC-DEMO-001", db_path=self.db_path)
        self.assertEqual(len(incoming), 2)
