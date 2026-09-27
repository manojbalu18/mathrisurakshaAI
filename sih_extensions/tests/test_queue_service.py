import unittest
import os
import tempfile
import datetime
from sih_extensions.sih_database import init_sih_db
from sih_extensions.facility_directory import FacilityDirectory
from sih_extensions.queue_service import QueueService

class TestQueueService(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        init_sih_db(db_path=self.db_path)
        FacilityDirectory.seed_demo_data(db_path=self.db_path)

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_token_creation_and_retrieval(self):
        res1 = QueueService.add_patient("FAC-DEMO-001", "PAT-001", "OPD", db_path=self.db_path)
        self.assertTrue(res1["success"])
        self.assertEqual(res1["token_number"], "OPD-001")

        res2 = QueueService.add_patient("FAC-DEMO-001", "PAT-002", "OPD", db_path=self.db_path)
        self.assertTrue(res2["success"])
        self.assertEqual(res2["token_number"], "OPD-002")
        
        q = QueueService.get_facility_queue("FAC-DEMO-001", db_path=self.db_path)
        self.assertEqual(len(q), 2)
        
        entry = QueueService.get_queue_entry(res2["queue_id"], db_path=self.db_path)
        self.assertEqual(entry["patient_id"], "PAT-002")

    def test_queue_position_and_wait_time(self):
        # Low priority
        res1 = QueueService.add_patient("FAC-DEMO-001", "PAT-001", priority=0, db_path=self.db_path)
        # High priority comes later but should jump ahead
        res2 = QueueService.add_patient("FAC-DEMO-001", "PAT-002", priority=10, db_path=self.db_path)
        
        pos1 = QueueService.calculate_position(res1["queue_id"], db_path=self.db_path)
        pos2 = QueueService.calculate_position(res2["queue_id"], db_path=self.db_path)
        
        self.assertEqual(pos2, 1) # Priority 10 is ahead
        self.assertEqual(pos1, 2)
        
        wait = QueueService.estimate_wait_time(res1["queue_id"], avg_consultation_minutes=15, db_path=self.db_path)
        self.assertEqual(wait, 15)

    def test_call_next_and_status(self):
        res1 = QueueService.add_patient("FAC-DEMO-001", "PAT-001", priority=0, db_path=self.db_path)
        res2 = QueueService.add_patient("FAC-DEMO-001", "PAT-002", priority=10, db_path=self.db_path)
        
        # Calling next should return PAT-002 because of higher priority
        next_pat = QueueService.call_next("FAC-DEMO-001", db_path=self.db_path)
        self.assertEqual(next_pat["patient_id"], "PAT-002")
        self.assertEqual(next_pat["status"], "CALLED")
        
        # Transition to IN_CONSULTATION
        QueueService.update_status(next_pat["queue_id"], "IN_CONSULTATION", db_path=self.db_path)
        entry = QueueService.get_queue_entry(next_pat["queue_id"], db_path=self.db_path)
        self.assertEqual(entry["status"], "IN_CONSULTATION")
        self.assertIsNotNone(entry["consultation_start_at"])
