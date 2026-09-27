"""
SIH Facility Directory Service.
Manages facility listing, search, filtering, distance calculation, and clean sample data seeding.
"""

import json
import os
import math
import sqlite3
from typing import List, Dict, Any, Optional

from .sih_database import get_sih_connection, init_sih_db, DB_PATH

def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate the great circle distance between two points in km."""
    R = 6371.0 # Earth radius in km
    
    lat1_rad, lon1_rad = math.radians(lat1), math.radians(lon1)
    lat2_rad, lon2_rad = math.radians(lat2), math.radians(lon2)
    
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad
    
    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return R * c

class FacilityDirectory:
    
    @staticmethod
    def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate the great circle distance between two points in km."""
        return haversine_distance(lat1, lon1, lat2, lon2)

    @staticmethod
    def seed_demo_data(db_path: str = DB_PATH, force_reload: bool = False) -> int:
        """
        Idempotently seeds clean healthcare facility content from facilities.json.
        Removes legacy dummy placeholder records if present.
        """
        init_sih_db(db_path=db_path)
        json_path = os.path.join(os.path.dirname(__file__), "data", "facilities.json")
        if not os.path.exists(json_path):
            return 0
            
        with open(json_path, "r", encoding="utf-8") as f:
            facilities = json.load(f)
            
        inserted = 0
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            
            # Clean up old mock records containing obsolete placeholders
            c.execute("DELETE FROM sih_facilities WHERE name LIKE '%(DEMO DATA)%'")
            
            if force_reload:
                c.execute("DELETE FROM sih_facilities")

            for fac in facilities:
                fid = fac.get('facility_id')
                name = fac.get('name', '')
                ftype = fac.get('type', '')
                addr = fac.get('address', '')
                lat = float(fac.get('latitude', 0.0))
                lon = float(fac.get('longitude', 0.0))
                phone = fac.get('contact_number', fac.get('phone', ''))
                hours = fac.get('operating_hours', '24/7 Open' if fac.get('emergency_available') else '08:00 AM - 05:00 PM')
                emerg = 1 if fac.get('emergency_available') else 0
                services = fac.get('services', '')
                status = fac.get('status', 'Active')
                
                c.execute("SELECT id FROM sih_facilities WHERE facility_id = ?", (fid,))
                row = c.fetchone()
                if row is None:
                    c.execute("""
                        INSERT INTO sih_facilities (
                            facility_id, name, type, address, latitude, longitude,
                            contact_number, operating_hours, emergency_available, services, status
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (fid, name, ftype, addr, lat, lon, phone, hours, emerg, services, status))
                    inserted += 1
                else:
                    # Update existing record to clean format
                    c.execute("""
                        UPDATE sih_facilities SET
                            name = ?, type = ?, address = ?, latitude = ?, longitude = ?,
                            contact_number = ?, operating_hours = ?, emergency_available = ?,
                            services = ?, status = ?
                        WHERE facility_id = ?
                    """, (name, ftype, addr, lat, lon, phone, hours, emerg, services, status, fid))
                    
            conn.commit()
        return inserted

    @staticmethod
    def get_facility(facility_id: str, db_path: str = DB_PATH) -> Optional[Dict[str, Any]]:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT facility_id, name, type, address, latitude, longitude,
                       contact_number, operating_hours, emergency_available, services, status
                FROM sih_facilities WHERE facility_id = ?
            """, (facility_id,))
            row = c.fetchone()
            if row:
                return {
                    "facility_id": row[0],
                    "name": row[1],
                    "type": row[2],
                    "address": row[3] or "",
                    "latitude": row[4],
                    "longitude": row[5],
                    "contact_number": row[6] or "",
                    "operating_hours": row[7] or "",
                    "emergency_available": bool(row[8]),
                    "services": row[9] or "",
                    "status": row[10] or "Active"
                }
        return None

    @staticmethod
    def list_facilities(type_filter: str = None, service_filter: str = None,
                        search_query: str = None, emergency_only: bool = False,
                        active_only: bool = True, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            query = """
                SELECT facility_id, name, type, address, latitude, longitude,
                       contact_number, operating_hours, emergency_available, services, status
                FROM sih_facilities WHERE 1=1
            """
            params = []
            
            if active_only:
                query += " AND status = 'Active'"
            if type_filter and type_filter != "All":
                query += " AND type = ?"
                params.append(type_filter)
            if emergency_only:
                query += " AND emergency_available = 1"
                
            c.execute(query, tuple(params))
            rows = c.fetchall()
            
        facilities = []
        for r in rows:
            fac = {
                "facility_id": r[0],
                "name": r[1],
                "type": r[2],
                "address": r[3] or "",
                "latitude": r[4],
                "longitude": r[5],
                "contact_number": r[6] or "",
                "operating_hours": r[7] or "",
                "emergency_available": bool(r[8]),
                "services": r[9] or "",
                "status": r[10] or "Active"
            }
            
            # Post-filter by service text match if requested
            if service_filter and service_filter != "All":
                if service_filter.lower() not in fac["services"].lower():
                    continue
                    
            # Post-filter by name/location search query if requested
            if search_query and search_query.strip():
                sq = search_query.strip().lower()
                combined_text = f"{fac['name']} {fac['type']} {fac['address']} {fac['services']}".lower()
                if sq not in combined_text:
                    continue
                    
            facilities.append(fac)
            
        return facilities
        
    @staticmethod
    def find_nearby(lat: float, lon: float, max_distance_km: float = 50.0,
                    type_filter: str = None, db_path: str = DB_PATH) -> List[Dict[str, Any]]:
        facilities = FacilityDirectory.list_facilities(type_filter=type_filter, active_only=True, db_path=db_path)
        nearby = []
        for fac in facilities:
            dist = haversine_distance(lat, lon, fac['latitude'], fac['longitude'])
            if max_distance_km is None or dist <= max_distance_km:
                fac['distance_km'] = round(dist, 1)
                nearby.append(fac)
        return sorted(nearby, key=lambda x: x['distance_km'])

    @staticmethod
    def create_facility(facility_data: Dict[str, Any], db_path: str = DB_PATH) -> bool:
        """Create a new facility manually."""
        with get_sih_connection(db_path) as conn:
            c = conn.cursor()
            try:
                c.execute("""
                    INSERT INTO sih_facilities (
                        facility_id, name, type, address, latitude, longitude,
                        contact_number, operating_hours, emergency_available, services, status
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    facility_data['facility_id'], facility_data['name'], facility_data['type'],
                    facility_data.get('address', ''), facility_data['latitude'], facility_data['longitude'],
                    facility_data.get('contact_number', facility_data.get('phone', '')),
                    facility_data.get('operating_hours', '24/7 Open'),
                    1 if facility_data.get('emergency_available') else 0,
                    facility_data.get('services', ''),
                    facility_data.get('status', 'Active')
                ))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

