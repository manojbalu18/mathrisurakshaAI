import unittest
import os
import tempfile
from sih_extensions.sih_database import init_sih_db
from sih_extensions.facility_directory import FacilityDirectory
from sih_extensions.medicine_service import MedicineService

class TestMedicineService(unittest.TestCase):
    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp()
        init_sih_db(db_path=self.db_path)
        FacilityDirectory.seed_demo_data(db_path=self.db_path)
        MedicineService.seed_demo_data(db_path=self.db_path)

    def tearDown(self):
        os.close(self.db_fd)
        os.unlink(self.db_path)

    def test_medicine_creation_and_retrieval(self):
        res = MedicineService.create_or_update_medicine(
            "FAC-DEMO-001", "MED-100", "Ibuprofen 400mg", "Ibuprofen", 100, "Tablets", db_path=self.db_path
        )
        self.assertTrue(res["success"])
        self.assertEqual(res["status"], "IN_STOCK")
        
        m = MedicineService.get_medicine("MED-100", "FAC-DEMO-001", db_path=self.db_path)
        self.assertEqual(m["generic_name"], "Ibuprofen")
        
    def test_invalid_facility(self):
        res = MedicineService.create_or_update_medicine(
            "INVALID", "MED-100", "Test", "Test", 10, "Tabs", db_path=self.db_path
        )
        self.assertFalse(res["success"])

    def test_quantity_and_availability(self):
        MedicineService.create_or_update_medicine("FAC-DEMO-001", "MED-200", "Test", "Test", 10, "Tabs", db_path=self.db_path)
        m = MedicineService.get_medicine("MED-200", "FAC-DEMO-001", db_path=self.db_path)
        self.assertEqual(m["status"], "LOW_STOCK")
        
        MedicineService.update_quantity("MED-200", "FAC-DEMO-001", 0, db_path=self.db_path)
        m2 = MedicineService.get_medicine("MED-200", "FAC-DEMO-001", db_path=self.db_path)
        self.assertEqual(m2["status"], "OUT_OF_STOCK")

    def test_search_and_list(self):
        # Demo data is seeded
        inv = MedicineService.get_facility_inventory("FAC-DEMO-001", db_path=self.db_path)
        self.assertGreaterEqual(len(inv), 2)
        
        search = MedicineService.search_medicine("Para", db_path=self.db_path)
        self.assertTrue(any(s["item_name"] == "Paracetamol 500mg" for s in search))

    def test_deactivate(self):
        MedicineService.deactivate_medicine("MED-001", "FAC-DEMO-001", db_path=self.db_path)
        inv = MedicineService.get_facility_inventory("FAC-DEMO-001", db_path=self.db_path)
        # Should not include deactivated item
        self.assertFalse(any(i["item_id"] == "MED-001" for i in inv))
