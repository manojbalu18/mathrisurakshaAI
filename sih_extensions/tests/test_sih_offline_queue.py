import unittest
import os
import tempfile
from sih_extensions.sih_database import init_sih_db
from sih_extensions.sih_offline_queue import SIHOfflineQueue

class TestSIHOfflineQueue(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        init_sih_db(db_path=self.db_path)

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_enqueue_and_get_pending(self):
        payload = {"foo": "bar"}
        op_id = SIHOfflineQueue.enqueue("TEST_OP", payload, db_path=self.db_path)
        self.assertIsNotNone(op_id)
        
        pending = SIHOfflineQueue.get_pending(db_path=self.db_path)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]['operation_id'], op_id)
        self.assertEqual(pending[0]['operation_type'], "TEST_OP")
        self.assertEqual(pending[0]['payload'], payload)
        self.assertEqual(pending[0]['status'], "PENDING")

    def test_status_transitions(self):
        op_id = SIHOfflineQueue.enqueue("TEST_OP", {"x": 1}, db_path=self.db_path)
        
        # PROCESSING
        SIHOfflineQueue.mark_processing(op_id, db_path=self.db_path)
        pending = SIHOfflineQueue.get_pending(db_path=self.db_path)
        self.assertEqual(len(pending), 0)  # PROCESSING shouldn't be returned
        
        status = SIHOfflineQueue.get_queue_status(db_path=self.db_path)
        self.assertEqual(status.get("PROCESSING"), 1)
        
        # FAILED
        SIHOfflineQueue.mark_failed(op_id, "error test", db_path=self.db_path)
        pending = SIHOfflineQueue.get_pending(db_path=self.db_path)
        self.assertEqual(len(pending), 1)  # FAILED < 3 retries is returned
        self.assertEqual(pending[0]['retry_count'], 1)
        self.assertEqual(pending[0]['status'], "FAILED")
        self.assertEqual(pending[0]['error_msg'], "error test")
        
        # Retry explicitly
        SIHOfflineQueue.retry_failed(db_path=self.db_path)
        pending = SIHOfflineQueue.get_pending(db_path=self.db_path)
        self.assertEqual(pending[0]['status'], "PENDING")
        
        # SYNCED
        SIHOfflineQueue.mark_synced(op_id, db_path=self.db_path)
        status = SIHOfflineQueue.get_queue_status(db_path=self.db_path)
        self.assertEqual(status.get("SYNCED"), 1)
