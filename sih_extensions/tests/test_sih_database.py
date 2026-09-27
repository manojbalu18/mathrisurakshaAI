import unittest
import sqlite3
import os
import tempfile
from sih_extensions.sih_database import init_sih_db, get_sih_connection

class TestSIHDatabase(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        # Initialize some fake legacy tables to verify they remain intact
        with sqlite3.connect(self.db_path) as conn:
            c = conn.cursor()
            c.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
            c.execute("INSERT INTO users (name) VALUES ('Test Mother')")
            conn.commit()

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_init_sih_db_idempotency_and_safety(self):
        # First initialization
        init_sih_db(db_path=self.db_path)
        
        # Second initialization (idempotency check)
        init_sih_db(db_path=self.db_path)
        
        with get_sih_connection(self.db_path) as conn:
            c = conn.cursor()
            
            # Verify legacy table intact
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
            self.assertIsNotNone(c.fetchone())
            c.execute("SELECT COUNT(*) FROM users")
            self.assertEqual(c.fetchone()[0], 1)
            
            # Verify SIH tables were created
            expected_tables = [
                'sih_facilities', 'sih_inventory', 'sih_appointments', 
                'sih_queue', 'sih_referrals', 'sih_consultations', 
                'sih_fhir_records', 'sih_offline_sync'
            ]
            
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'sih_%'")
            created_tables = [row[0] for row in c.fetchall()]
            
            for t in expected_tables:
                self.assertIn(t, created_tables)
