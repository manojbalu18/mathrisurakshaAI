import unittest
import os
import tempfile
from sih_extensions.sih_database import init_sih_db
from sih_extensions.facility_directory import FacilityDirectory

class TestFacilityDirectory(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        init_sih_db(db_path=self.db_path)

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_seed_demo_data_idempotency(self):
        # First seed
        inserted = FacilityDirectory.seed_demo_data(db_path=self.db_path)
        self.assertGreater(inserted, 0)
        
        # Second seed (should be 0)
        inserted_again = FacilityDirectory.seed_demo_data(db_path=self.db_path)
        self.assertEqual(inserted_again, 0)
        
    def test_get_and_list_facilities(self):
        FacilityDirectory.seed_demo_data(db_path=self.db_path)
        facs = FacilityDirectory.list_facilities(db_path=self.db_path)
        self.assertGreater(len(facs), 0)
        
        fac = FacilityDirectory.get_facility("FAC-DEMO-001", db_path=self.db_path)
        self.assertIsNotNone(fac)
        self.assertEqual(fac["type"], "District Hospital")
        self.assertIn("District", fac["name"])

    def test_find_nearby(self):
        FacilityDirectory.seed_demo_data(db_path=self.db_path)
        
        # Hyderabad coordinate search
        nearby = FacilityDirectory.find_nearby(17.3910, 78.4860, max_distance_km=10.0, db_path=self.db_path)
        self.assertTrue(len(nearby) >= 1)
        
        # Some random location far away
        far = FacilityDirectory.find_nearby(40.7128, -74.0060, max_distance_km=10.0, db_path=self.db_path)
        self.assertEqual(len(far), 0)

    def test_filter_by_type(self):
        FacilityDirectory.seed_demo_data(db_path=self.db_path)
        facs = FacilityDirectory.list_facilities(type_filter="District Hospital", db_path=self.db_path)
        for f in facs:
            self.assertEqual(f["type"], "District Hospital")
