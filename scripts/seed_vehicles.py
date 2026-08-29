"""
scripts/seed_vehicles.py — Comprehensive vehicle library seed.
Clears and re-seeds vehicle_categories and vehicles on every run.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import get_connection, init_db

# ── Categories ────────────────────────────────────────────────────────────────

CATEGORIES = [
    {"name": "Small-lift orbital (SLV)",  "sort_order": 1},
    {"name": "Medium-lift orbital (MLV)", "sort_order": 2},
    {"name": "Heavy-lift orbital (HLV)",  "sort_order": 3},
    {"name": "Super heavy-lift (SHLV)",   "sort_order": 4},
    {"name": "Suborbital / hypersonic",   "sort_order": 5},
    {"name": "Air-launched",              "sort_order": 6},
]

_SLV  = "Small-lift orbital (SLV)"
_MLV  = "Medium-lift orbital (MLV)"
_HLV  = "Heavy-lift orbital (HLV)"
_SHLV = "Super heavy-lift (SHLV)"
_SUB  = "Suborbital / hypersonic"
_AIR  = "Air-launched"

# ── Vehicles ──────────────────────────────────────────────────────────────────
# All REAL threshold fields in units: kts, kts, m, m, s
# vehicle_class: slv_orb / slv_sub / mlv_orb / mlv_sub  (probability engine classes)

VEHICLES = [

    # ── Small-lift orbital ────────────────────────────────────────────────────

    {
        "name": "Firefly Alpha / Alpha Block 2",
        "provider": "Firefly Aerospace", "country": "USA",
        "category": _SLV, "vehicle_class": "slv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 1000, "sso_payload_kg": 630,
        "height_m": 29.5, "diameter_m": 1.8, "gross_mass_kg": 54_000,
        "stages": 2, "propellant_stage1": "LOX/Kerosene",
        "status": "operational", "first_flight_year": 2022,
        "max_wind_kts": 18, "max_gust_kts": 25, "max_hs_m": 1.5,
        "max_swell_ht_m": 2.0, "max_swell_period_s": 12.0,
        "data_source": "estimated",
        "notes": "Gateway Series primary paired vehicle per MOU 2026",
    },
    {
        "name": "Rocket Lab Electron / Electron KS",
        "provider": "Rocket Lab", "country": "USA/NZ",
        "category": _SLV, "vehicle_class": "slv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 300, "sso_payload_kg": 200,
        "height_m": 18.0, "diameter_m": 1.2, "gross_mass_kg": 13_000,
        "stages": 2, "propellant_stage1": "LOX/Kerosene",
        "status": "operational", "first_flight_year": 2017,
        "max_wind_kts": 15, "max_gust_kts": 20, "max_hs_m": 1.2,
        "max_swell_ht_m": 2.0, "max_swell_period_s": 12.0,
        "data_source": "estimated",
        "notes": "High flight rate; recovery variant adds droneship ops",
    },
    {
        "name": "ABL Space RS1",
        "provider": "ABL Space Systems", "country": "USA",
        "category": _SLV, "vehicle_class": "slv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 1350, "sso_payload_kg": 900,
        "height_m": 27.0, "diameter_m": 1.8, "gross_mass_kg": 90_000,
        "stages": 2, "propellant_stage1": "LOX/Kerosene",
        "status": "operational", "first_flight_year": 2023,
        "max_wind_kts": 18, "max_gust_kts": 25, "max_hs_m": 1.5,
        "max_swell_ht_m": 2.0, "max_swell_period_s": 12.0,
        "data_source": "estimated",
    },
    {
        "name": "Relativity Terran 1",
        "provider": "Relativity Space", "country": "USA",
        "category": _SLV, "vehicle_class": "slv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 1250,
        "height_m": 33.5, "diameter_m": 2.2,
        "stages": 2, "propellant_stage1": "LOX/Methane",
        "status": "retired", "first_flight_year": 2023,
        "max_wind_kts": 18, "max_gust_kts": 25, "max_hs_m": 1.5,
        "max_swell_ht_m": 2.0, "max_swell_period_s": 12.0,
        "data_source": "estimated",
        "notes": "3D-printed structure; program cancelled after test flight",
    },
    {
        "name": "Vega-C",
        "provider": "Avio/ESA", "country": "Italy/EU",
        "category": _SLV, "vehicle_class": "slv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 2350, "sso_payload_kg": 1740,
        "height_m": 35.0, "diameter_m": 3.4, "gross_mass_kg": 210_000,
        "stages": 4, "propellant_stage1": "Solid", "propellant_stage2": "Solid",
        "status": "operational", "first_flight_year": 2022,
        "max_wind_kts": 22, "max_gust_kts": 30, "max_hs_m": 1.7,
        "max_swell_ht_m": 2.0, "max_swell_period_s": 12.0,
        "data_source": "estimated",
    },
    {
        "name": "Vega-E",
        "provider": "Avio/ESA", "country": "Italy/EU",
        "category": _SLV, "vehicle_class": "slv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 2200, "sso_payload_kg": 1800,
        "height_m": 33.0, "diameter_m": 3.4,
        "stages": 3, "propellant_stage1": "Solid", "propellant_stage2": "Solid",
        "propellant_upper": "LOX/Methane",
        "status": "development", "first_flight_year": 2027,
        "max_wind_kts": 22, "max_gust_kts": 30, "max_hs_m": 1.7,
        "max_swell_ht_m": 2.0, "max_swell_period_s": 12.0,
        "data_source": "estimated",
    },
    {
        "name": "Minotaur I",
        "provider": "Northrop Grumman", "country": "USA",
        "category": _SLV, "vehicle_class": "slv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 580, "sso_payload_kg": 300,
        "height_m": 19.2, "diameter_m": 1.3,
        "stages": 4, "propellant_stage1": "Solid", "propellant_stage2": "Solid",
        "status": "operational", "first_flight_year": 2000,
        "max_wind_kts": 20, "max_gust_kts": 28, "max_hs_m": 1.5,
        "max_swell_ht_m": 2.0, "max_swell_period_s": 12.0,
        "data_source": "estimated",
        "notes": "Converted Minuteman I/II first stages; USG manifest only",
    },
    {
        "name": "Minotaur IV",
        "provider": "Northrop Grumman", "country": "USA",
        "category": _SLV, "vehicle_class": "slv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 1735, "sso_payload_kg": 1130,
        "height_m": 23.9, "diameter_m": 2.3,
        "stages": 4, "propellant_stage1": "Solid", "propellant_stage2": "Solid",
        "status": "operational", "first_flight_year": 2010,
        "max_wind_kts": 20, "max_gust_kts": 28, "max_hs_m": 1.5,
        "max_swell_ht_m": 2.0, "max_swell_period_s": 12.0,
        "data_source": "estimated",
        "notes": "Converted Peacekeeper ICBM stages; USG manifest only",
    },
    {
        "name": "Minotaur-C",
        "provider": "Northrop Grumman", "country": "USA",
        "category": _SLV, "vehicle_class": "slv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 1370, "sso_payload_kg": 820,
        "height_m": 29.6, "diameter_m": 2.3,
        "stages": 4, "propellant_stage1": "Solid",
        "status": "operational", "first_flight_year": 1994,
        "max_wind_kts": 20, "max_gust_kts": 28, "max_hs_m": 1.5,
        "max_swell_ht_m": 2.0, "max_swell_period_s": 12.0,
        "data_source": "estimated",
        "notes": "Formerly Taurus; solid-propellant stack",
    },
    {
        "name": "ISRO SSLV",
        "provider": "ISRO", "country": "India",
        "category": _SLV, "vehicle_class": "slv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 500, "sso_payload_kg": 300,
        "height_m": 34.0, "diameter_m": 2.0, "gross_mass_kg": 120_000,
        "stages": 3, "propellant_stage1": "Solid", "propellant_stage2": "Solid",
        "status": "operational", "first_flight_year": 2022,
        "max_wind_kts": 18, "max_gust_kts": 25, "max_hs_m": 1.5,
        "max_swell_ht_m": 2.0, "max_swell_period_s": 12.0,
        "data_source": "estimated",
    },
    {
        "name": "New Entrants SLV (placeholder)",
        "provider": "Various", "country": "USA/International",
        "category": _SLV, "vehicle_class": "slv_orb",
        "recovery_mode": "expendable",
        "status": "development",
        "max_wind_kts": 18, "max_gust_kts": 25, "max_hs_m": 1.5,
        "max_swell_ht_m": 2.0, "max_swell_period_s": 12.0,
        "data_source": "estimated",
        "notes": "Placeholder for emerging SLV providers (Dawn Aerospace, RocketStar, etc.)",
    },

    # ── Medium-lift orbital ───────────────────────────────────────────────────

    {
        "name": "Rocket Lab Neutron",
        "provider": "Rocket Lab", "country": "USA",
        "category": _MLV, "vehicle_class": "mlv_orb",
        "recovery_mode": "rtls",
        "leo_payload_kg": 13_000, "sso_payload_kg": 8_000,
        "height_m": 40.0, "diameter_m": 7.0, "gross_mass_kg": 480_000,
        "stages": 2, "propellant_stage1": "LOX/Methane",
        "status": "development", "first_flight_year": 2026,
        "max_wind_kts": 25, "max_gust_kts": 35, "max_hs_m": 2.0,
        "max_swell_ht_m": 2.5, "max_swell_period_s": 14.0,
        "data_source": "estimated",
        "notes": "Reusable first stage; bridges SLV-MLV boundary",
    },
    {
        "name": "Relativity Terran R",
        "provider": "Relativity Space", "country": "USA",
        "category": _MLV, "vehicle_class": "mlv_orb",
        "recovery_mode": "rtls",
        "leo_payload_kg": 20_000,
        "height_m": 66.0, "diameter_m": 5.5,
        "stages": 2, "propellant_stage1": "LOX/Methane",
        "status": "development", "first_flight_year": 2026,
        "max_wind_kts": 25, "max_gust_kts": 35, "max_hs_m": 2.0,
        "max_swell_ht_m": 2.5, "max_swell_period_s": 14.0,
        "data_source": "estimated",
        "notes": "Fully reusable; scaled Terran architecture",
    },
    {
        "name": "Firefly Miranda (proposed MLV)",
        "provider": "Firefly Aerospace", "country": "USA",
        "category": _MLV, "vehicle_class": "mlv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 8_000, "height_m": 55.0,
        "status": "proposed",
        "max_wind_kts": 25, "max_gust_kts": 35, "max_hs_m": 2.0,
        "max_swell_ht_m": 2.5, "max_swell_period_s": 14.0,
        "data_source": "estimated",
        "notes": "Proposed follow-on to Alpha; not yet announced formally",
    },
    {
        "name": "Antares 230+",
        "provider": "Northrop Grumman", "country": "USA",
        "category": _MLV, "vehicle_class": "mlv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 8_000, "sso_payload_kg": 5_400,
        "height_m": 42.5, "diameter_m": 3.9, "gross_mass_kg": 300_000,
        "stages": 2, "propellant_stage1": "LOX/Kerosene", "propellant_stage2": "Solid",
        "status": "operational", "first_flight_year": 2013,
        "max_wind_kts": 25, "max_gust_kts": 35, "max_hs_m": 2.0,
        "max_swell_ht_m": 2.5, "max_swell_period_s": 14.0,
        "data_source": "estimated",
    },
    {
        "name": "Antares 330",
        "provider": "Northrop Grumman / Firefly", "country": "USA",
        "category": _MLV, "vehicle_class": "mlv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 8_000, "height_m": 42.5, "diameter_m": 3.9,
        "stages": 2, "propellant_stage1": "LOX/Kerosene",
        "status": "development", "first_flight_year": 2025,
        "max_wind_kts": 25, "max_gust_kts": 35, "max_hs_m": 2.0,
        "max_swell_ht_m": 2.5, "max_swell_period_s": 14.0,
        "data_source": "estimated",
        "notes": "RD-181 replacement engines; Firefly Miranda upper stage",
    },
    {
        "name": "Falcon 9 Block 5",
        "provider": "SpaceX", "country": "USA",
        "category": _MLV, "vehicle_class": "mlv_orb",
        "recovery_mode": "droneship",
        "leo_payload_kg": 22_800, "sso_payload_kg": 15_600, "gto_payload_kg": 8_300,
        "height_m": 70.0, "diameter_m": 3.7, "gross_mass_kg": 549_000,
        "stages": 2, "propellant_stage1": "LOX/Kerosene", "propellant_stage2": "LOX/Kerosene",
        "status": "operational", "first_flight_year": 2010,
        "max_wind_kts": 30, "max_gust_kts": 42, "max_hs_m": 2.5,
        "max_swell_ht_m": 2.5, "max_swell_period_s": 14.0,
        "data_source": "range_safety", "wind_hold_verified": 1,
        "notes": "Highest flight rate vehicle; RTLS or ASDS recovery",
    },
    {
        "name": "Atlas V 401",
        "provider": "ULA", "country": "USA",
        "category": _MLV, "vehicle_class": "mlv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 18_850, "gto_payload_kg": 8_900,
        "height_m": 58.3, "diameter_m": 3.8,
        "stages": 2, "propellant_stage1": "LOX/Kerosene", "propellant_stage2": "LOX/LH2",
        "status": "operational", "first_flight_year": 2002,
        "max_wind_kts": 28, "max_gust_kts": 38, "max_hs_m": 2.0,
        "max_swell_ht_m": 2.5, "max_swell_period_s": 14.0,
        "data_source": "estimated",
        "notes": "Final flights underway; being replaced by Vulcan Centaur",
    },
    {
        "name": "Atlas V 551",
        "provider": "ULA", "country": "USA",
        "category": _MLV, "vehicle_class": "mlv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 18_500, "gto_payload_kg": 8_900,
        "height_m": 62.2, "diameter_m": 3.8,
        "stages": 2, "propellant_stage1": "LOX/Kerosene", "propellant_stage2": "LOX/LH2",
        "status": "operational", "first_flight_year": 2006,
        "max_wind_kts": 28, "max_gust_kts": 38, "max_hs_m": 2.0,
        "max_swell_ht_m": 2.5, "max_swell_period_s": 14.0,
        "data_source": "estimated",
        "notes": "5 solid strap-on boosters; largest Atlas V config",
    },
    {
        "name": "Vulcan Centaur VC2S",
        "provider": "ULA", "country": "USA",
        "category": _MLV, "vehicle_class": "mlv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 27_200, "gto_payload_kg": 15_000,
        "height_m": 61.6, "diameter_m": 5.4, "gross_mass_kg": 547_000,
        "stages": 2, "propellant_stage1": "LOX/LH2", "propellant_stage2": "LOX/LH2",
        "status": "operational", "first_flight_year": 2024,
        "max_wind_kts": 30, "max_gust_kts": 40, "max_hs_m": 2.2,
        "max_swell_ht_m": 2.5, "max_swell_period_s": 14.0,
        "data_source": "estimated",
        "notes": "BE-4 engines; replaces Atlas V and Delta IV Medium",
    },
    {
        "name": "New Glenn Block 1",
        "provider": "Blue Origin", "country": "USA",
        "category": _MLV, "vehicle_class": "mlv_orb",
        "recovery_mode": "droneship",
        "leo_payload_kg": 45_000, "gto_payload_kg": 13_600,
        "height_m": 98.0, "diameter_m": 7.0, "gross_mass_kg": 1_000_000,
        "stages": 2, "propellant_stage1": "LOX/LH2", "propellant_stage2": "LOX/LH2",
        "status": "operational", "first_flight_year": 2025,
        "max_wind_kts": 32, "max_gust_kts": 45, "max_hs_m": 2.8,
        "max_swell_ht_m": 2.5, "max_swell_period_s": 14.0,
        "data_source": "estimated",
        "notes": "7-meter fairing; reusable first stage to ship landing",
    },
    {
        "name": "Ariane 6 A62",
        "provider": "ArianeGroup/ESA", "country": "EU/France",
        "category": _MLV, "vehicle_class": "mlv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 21_600, "gto_payload_kg": 10_350,
        "height_m": 62.0, "diameter_m": 5.4,
        "stages": 2, "propellant_stage1": "LOX/LH2", "propellant_stage2": "LOX/LH2",
        "status": "operational", "first_flight_year": 2024,
        "max_wind_kts": 27, "max_gust_kts": 38, "max_hs_m": 2.2,
        "max_swell_ht_m": 2.5, "max_swell_period_s": 14.0,
        "data_source": "estimated",
        "notes": "2 P120C solid strap-on boosters",
    },
    {
        "name": "Ariane 6 A64",
        "provider": "ArianeGroup/ESA", "country": "EU/France",
        "category": _MLV, "vehicle_class": "mlv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 21_600, "gto_payload_kg": 11_500,
        "height_m": 62.0, "diameter_m": 5.4,
        "stages": 2, "propellant_stage1": "LOX/LH2", "propellant_stage2": "LOX/LH2",
        "status": "operational", "first_flight_year": 2024,
        "max_wind_kts": 27, "max_gust_kts": 38, "max_hs_m": 2.2,
        "max_swell_ht_m": 2.5, "max_swell_period_s": 14.0,
        "data_source": "estimated",
        "notes": "4 P120C solid strap-on boosters; higher GTO capacity",
    },
    {
        "name": "H3 Launch Vehicle (H3-22)",
        "provider": "JAXA/MHI", "country": "Japan",
        "category": _MLV, "vehicle_class": "mlv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 16_500, "sso_payload_kg": 7_000,
        "height_m": 63.0, "diameter_m": 5.2,
        "stages": 2, "propellant_stage1": "LOX/LH2", "propellant_stage2": "LOX/LH2",
        "status": "operational", "first_flight_year": 2024,
        "max_wind_kts": 26, "max_gust_kts": 36, "max_hs_m": 2.0,
        "max_swell_ht_m": 2.5, "max_swell_period_s": 14.0,
        "data_source": "estimated",
        "notes": "Replaces H-IIA; LE-9 engines",
    },
    {
        "name": "ISRO PSLV-XL",
        "provider": "ISRO", "country": "India",
        "category": _MLV, "vehicle_class": "mlv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 3_800, "sso_payload_kg": 1_750,
        "height_m": 44.4, "diameter_m": 2.8,
        "stages": 4, "propellant_stage1": "Solid", "propellant_stage2": "Hypergolic",
        "status": "operational", "first_flight_year": 1994,
        "max_wind_kts": 22, "max_gust_kts": 30, "max_hs_m": 1.8,
        "max_swell_ht_m": 2.5, "max_swell_period_s": 14.0,
        "data_source": "estimated",
        "notes": "Extremely reliable; >50 consecutive successes",
    },
    {
        "name": "ISRO GSLV Mk III (LVM3)",
        "provider": "ISRO", "country": "India",
        "category": _MLV, "vehicle_class": "mlv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 10_000, "gto_payload_kg": 4_000,
        "height_m": 43.5, "diameter_m": 4.0,
        "stages": 3, "propellant_stage1": "Solid", "propellant_stage2": "LOX/LH2",
        "status": "operational", "first_flight_year": 2017,
        "max_wind_kts": 25, "max_gust_kts": 35, "max_hs_m": 2.0,
        "max_swell_ht_m": 2.5, "max_swell_period_s": 14.0,
        "data_source": "estimated",
        "notes": "CE-20 cryogenic upper stage; commercial satellite launcher",
    },
    {
        "name": "Long March 2C",
        "provider": "CASC", "country": "China",
        "category": _MLV, "vehicle_class": "mlv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 3_850, "sso_payload_kg": 1_900,
        "height_m": 43.0, "diameter_m": 3.4,
        "stages": 2, "propellant_stage1": "Hypergolic", "propellant_stage2": "Hypergolic",
        "status": "operational", "first_flight_year": 1975,
        "max_wind_kts": 22, "max_gust_kts": 30, "max_hs_m": 1.8,
        "max_swell_ht_m": 2.5, "max_swell_period_s": 14.0,
        "data_source": "estimated",
    },
    {
        "name": "Long March 4B",
        "provider": "CASC", "country": "China",
        "category": _MLV, "vehicle_class": "mlv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 4_200, "sso_payload_kg": 2_800,
        "height_m": 45.8, "diameter_m": 3.4,
        "stages": 3, "propellant_stage1": "Hypergolic",
        "status": "operational", "first_flight_year": 1999,
        "max_wind_kts": 22, "max_gust_kts": 30, "max_hs_m": 1.8,
        "max_swell_ht_m": 2.5, "max_swell_period_s": 14.0,
        "data_source": "estimated",
    },
    {
        "name": "Long March 7",
        "provider": "CASC", "country": "China",
        "category": _MLV, "vehicle_class": "mlv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 13_500, "sso_payload_kg": 5_500,
        "height_m": 53.1, "diameter_m": 3.4,
        "stages": 2, "propellant_stage1": "LOX/Kerosene", "propellant_stage2": "LOX/Kerosene",
        "status": "operational", "first_flight_year": 2016,
        "max_wind_kts": 25, "max_gust_kts": 35, "max_hs_m": 2.0,
        "max_swell_ht_m": 2.5, "max_swell_period_s": 14.0,
        "data_source": "estimated",
        "notes": "Wenchang coastal launch site; Tianzhou cargo missions",
    },
    {
        "name": "Soyuz-2.1a / 2.1b",
        "provider": "Roscosmos", "country": "Russia",
        "category": _MLV, "vehicle_class": "mlv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 7_020, "sso_payload_kg": 4_350,
        "height_m": 46.3, "diameter_m": 2.9,
        "stages": 3, "propellant_stage1": "LOX/Kerosene",
        "status": "operational", "first_flight_year": 2004,
        "max_wind_kts": 24, "max_gust_kts": 33, "max_hs_m": 2.0,
        "max_swell_ht_m": 2.5, "max_swell_period_s": 14.0,
        "data_source": "estimated",
        "notes": "Baikonur and Vostochny; most-flown rocket family in history",
    },
    {
        "name": "Soyuz-2.1v",
        "provider": "Roscosmos", "country": "Russia",
        "category": _MLV, "vehicle_class": "mlv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 2_850, "sso_payload_kg": 1_500,
        "height_m": 44.0, "diameter_m": 2.7,
        "stages": 3, "propellant_stage1": "LOX/Kerosene",
        "status": "operational", "first_flight_year": 2013,
        "max_wind_kts": 22, "max_gust_kts": 30, "max_hs_m": 1.8,
        "max_swell_ht_m": 2.5, "max_swell_period_s": 14.0,
        "data_source": "estimated",
        "notes": "Lightweight variant; NK-33 first stage engine",
    },

    # ── Heavy-lift orbital ────────────────────────────────────────────────────

    {
        "name": "Falcon Heavy",
        "provider": "SpaceX", "country": "USA",
        "category": _HLV, "vehicle_class": "mlv_orb",
        "recovery_mode": "rtls",
        "leo_payload_kg": 63_800, "gto_payload_kg": 26_700,
        "height_m": 70.0, "diameter_m": 3.7, "gross_mass_kg": 1_420_788,
        "stages": 2, "propellant_stage1": "LOX/Kerosene",
        "status": "operational", "first_flight_year": 2018,
        "max_wind_kts": 30, "max_gust_kts": 42, "max_hs_m": 2.5,
        "max_swell_ht_m": 3.0, "max_swell_period_s": 15.0,
        "data_source": "estimated",
        "notes": "3x Falcon 9 cores; side booster RTLS standard",
    },
    {
        "name": "Delta IV Heavy",
        "provider": "ULA", "country": "USA",
        "category": _HLV, "vehicle_class": "mlv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 28_790, "gto_payload_kg": 14_220,
        "height_m": 72.0, "diameter_m": 5.1,
        "stages": 2, "propellant_stage1": "LOX/LH2",
        "status": "retired", "first_flight_year": 2004,
        "max_wind_kts": 30, "max_gust_kts": 42, "max_hs_m": 2.5,
        "max_swell_ht_m": 3.0, "max_swell_period_s": 15.0,
        "data_source": "estimated",
        "notes": "Final flight 2024; replaced by Vulcan Centaur",
    },
    {
        "name": "Long March 5",
        "provider": "CASC", "country": "China",
        "category": _HLV, "vehicle_class": "mlv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 25_000, "gto_payload_kg": 14_000,
        "height_m": 56.97, "diameter_m": 5.0,
        "stages": 2, "propellant_stage1": "LOX/LH2", "propellant_stage2": "LOX/Kerosene",
        "status": "operational", "first_flight_year": 2016,
        "max_wind_kts": 30, "max_gust_kts": 42, "max_hs_m": 2.5,
        "max_swell_ht_m": 3.0, "max_swell_period_s": 15.0,
        "data_source": "estimated",
        "notes": "Wenchang coastal launch facility; Tianwen Mars mission",
    },
    {
        "name": "Long March 5B",
        "provider": "CASC", "country": "China",
        "category": _HLV, "vehicle_class": "mlv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 25_000,
        "height_m": 53.66, "diameter_m": 5.0,
        "stages": 1, "propellant_stage1": "LOX/LH2",
        "status": "operational", "first_flight_year": 2020,
        "max_wind_kts": 30, "max_gust_kts": 42, "max_hs_m": 2.5,
        "max_swell_ht_m": 3.0, "max_swell_period_s": 15.0,
        "data_source": "estimated",
        "notes": "Single-stage; CSS module launcher; uncontrolled reentries",
    },
    {
        "name": "SLS Block 1",
        "provider": "NASA/Boeing", "country": "USA",
        "category": _HLV, "vehicle_class": "mlv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 95_000,
        "height_m": 98.0, "diameter_m": 8.4,
        "stages": 2, "propellant_stage1": "LOX/LH2", "propellant_stage2": "Solid",
        "status": "operational", "first_flight_year": 2022,
        "max_wind_kts": 35, "max_gust_kts": 50, "max_hs_m": 3.0,
        "max_swell_ht_m": 3.0, "max_swell_period_s": 15.0,
        "data_source": "estimated",
        "notes": "Artemis program; Orion crew vehicle primary launcher",
    },

    # ── Super heavy-lift ──────────────────────────────────────────────────────

    {
        "name": "Starship / Super Heavy",
        "provider": "SpaceX", "country": "USA",
        "category": _SHLV, "vehicle_class": "mlv_orb",
        "recovery_mode": "air catch",
        "leo_payload_kg": 150_000,
        "height_m": 121.0, "diameter_m": 9.0, "gross_mass_kg": 5_000_000,
        "stages": 2, "propellant_stage1": "LOX/Methane", "propellant_stage2": "LOX/Methane",
        "status": "operational", "first_flight_year": 2023,
        "max_wind_kts": 35, "max_gust_kts": 50, "max_hs_m": 3.0,
        "max_swell_ht_m": 3.5, "max_swell_period_s": 16.0,
        "data_source": "estimated",
        "notes": "Fully reusable; mechazilla catch system; rapidly evolving capability",
    },
    {
        "name": "Long March 9",
        "provider": "CASC", "country": "China",
        "category": _SHLV, "vehicle_class": "mlv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 150_000,
        "height_m": 114.0, "diameter_m": 10.6,
        "stages": 3, "propellant_stage1": "LOX/Kerosene",
        "status": "development", "first_flight_year": 2030,
        "max_wind_kts": 35, "max_gust_kts": 50, "max_hs_m": 3.0,
        "max_swell_ht_m": 3.5, "max_swell_period_s": 16.0,
        "data_source": "estimated",
        "notes": "Lunar mission vehicle; partially reusable design",
    },

    # ── Air-launched ──────────────────────────────────────────────────────────

    {
        "name": "Pegasus XL",
        "provider": "Northrop Grumman", "country": "USA",
        "category": _AIR, "vehicle_class": "slv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 443, "sso_payload_kg": 350,
        "height_m": 17.6, "diameter_m": 1.3, "gross_mass_kg": 23_130,
        "stages": 3, "propellant_stage1": "Solid", "propellant_stage2": "Solid",
        "status": "operational", "first_flight_year": 1990,
        "max_wind_kts": 30, "max_gust_kts": 45, "max_hs_m": 3.0,
        "max_swell_ht_m": 4.0, "max_swell_period_s": 18.0,
        "data_source": "estimated",
        "notes": "L-1011 carrier aircraft; drop at 39,000 ft; "
                 "sea state constrains carrier ops not rocket directly",
    },
    {
        "name": "Virgin Orbit LauncherOne",
        "provider": "Virgin Orbit", "country": "USA",
        "category": _AIR, "vehicle_class": "slv_orb",
        "recovery_mode": "expendable",
        "leo_payload_kg": 500,
        "height_m": 21.3, "diameter_m": 1.6,
        "stages": 2, "propellant_stage1": "LOX/Kerosene",
        "status": "retired", "first_flight_year": 2021,
        "max_wind_kts": 30, "max_gust_kts": 45, "max_hs_m": 3.0,
        "max_swell_ht_m": 4.0, "max_swell_period_s": 18.0,
        "data_source": "estimated",
        "notes": "Boeing 747 carrier; company ceased operations 2023",
    },

    # ── Suborbital / hypersonic ───────────────────────────────────────────────

    {
        "name": "New Shepard NS",
        "provider": "Blue Origin", "country": "USA",
        "category": _SUB, "vehicle_class": "slv_sub",
        "recovery_mode": "rtls",
        "height_m": 18.0,
        "stages": 1, "propellant_stage1": "LOX/LH2",
        "status": "operational", "first_flight_year": 2015,
        "max_wind_kts": 22, "max_gust_kts": 30, "max_hs_m": 1.8,
        "max_swell_ht_m": 2.3, "max_swell_period_s": 13.0,
        "data_source": "estimated",
        "notes": "VTVL booster; crew capsule parachute recovery",
    },
    {
        "name": "SpaceShipTwo (VSS Unity)",
        "provider": "Virgin Galactic", "country": "USA",
        "category": _SUB, "vehicle_class": "slv_sub",
        "recovery_mode": "glide",
        "height_m": 18.3,
        "stages": 1, "propellant_stage1": "Solid/Nitrous",
        "status": "retired", "first_flight_year": 2018,
        "max_wind_kts": 25, "max_gust_kts": 35, "max_hs_m": 2.0,
        "max_swell_ht_m": 2.3, "max_swell_period_s": 13.0,
        "data_source": "estimated",
        "notes": "Air-launched from WhiteKnightTwo; company restructured 2024; feathering reentry",
    },
    {
        "name": "Hypersonic test vehicle (DoD generic)",
        "provider": "Various", "country": "USA",
        "category": _SUB, "vehicle_class": "slv_sub",
        "recovery_mode": "expendable",
        "status": "operational",
        "max_wind_kts": 25, "max_gust_kts": 35, "max_hs_m": 2.0,
        "max_swell_ht_m": 2.3, "max_swell_period_s": 13.0,
        "data_source": "estimated",
        "notes": "Placeholder for DARPA/AFRL hypersonic flight test programs",
    },
]


# ── DB helpers ────────────────────────────────────────────────────────────────

_V_INSERT = """
INSERT INTO vehicles (
    name, provider, country, vehicle_class, recovery_mode,
    leo_payload_kg, sso_payload_kg, gto_payload_kg,
    height_m, diameter_m, gross_mass_kg,
    stages, propellant_stage1, propellant_stage2, propellant_upper,
    status, first_flight_year, manufacturer,
    max_wind_kts, max_gust_kts, max_hs_m, max_swell_ht_m, max_swell_period_s,
    max_wind_dir_tolerance_deg, max_sea_dir_tolerance_deg, max_swell_dir_tolerance_deg,
    wind_hold_verified, sea_state_verified, data_source,
    notes, category_id
) VALUES (
    :name, :provider, :country, :vehicle_class, :recovery_mode,
    :leo_payload_kg, :sso_payload_kg, :gto_payload_kg,
    :height_m, :diameter_m, :gross_mass_kg,
    :stages, :propellant_stage1, :propellant_stage2, :propellant_upper,
    :status, :first_flight_year, :manufacturer,
    :max_wind_kts, :max_gust_kts, :max_hs_m, :max_swell_ht_m, :max_swell_period_s,
    :max_wind_dir_tolerance_deg, :max_sea_dir_tolerance_deg, :max_swell_dir_tolerance_deg,
    :wind_hold_verified, :sea_state_verified, :data_source,
    :notes, :category_id
)
"""

_DEFAULTS = {
    "provider": None, "country": None, "recovery_mode": "expendable",
    "leo_payload_kg": None, "sso_payload_kg": None, "gto_payload_kg": None,
    "height_m": None, "diameter_m": None, "gross_mass_kg": None,
    "stages": None, "propellant_stage1": None, "propellant_stage2": None,
    "propellant_upper": None, "manufacturer": None,
    "status": "operational", "first_flight_year": None,
    "max_wind_dir_tolerance_deg": 45.0, "max_sea_dir_tolerance_deg": 60.0,
    "max_swell_dir_tolerance_deg": 60.0,
    "wind_hold_verified": 0, "sea_state_verified": 0,
    "data_source": "estimated", "notes": None, "category_id": None,
}


def seed() -> None:
    init_db()
    conn = get_connection()
    c = conn.cursor()

    # Clear and re-seed
    c.execute("DELETE FROM vehicles")
    c.execute("DELETE FROM vehicle_categories")

    # Insert categories; capture their IDs
    cat_id: dict[str, int] = {}
    for cat in CATEGORIES:
        c.execute(
            "INSERT INTO vehicle_categories (name, sort_order) VALUES (?, ?)",
            (cat["name"], cat["sort_order"]),
        )
        cat_id[cat["name"]] = c.lastrowid

    # Insert vehicles
    for v in VEHICLES:
        row = {**_DEFAULTS, **v}
        row["category_id"] = cat_id.get(row.pop("category", None))
        # wind_hold_verified stored as int in DB
        row["wind_hold_verified"] = int(row.get("wind_hold_verified", 0))
        row["sea_state_verified"]  = int(row.get("sea_state_verified",  0))
        c.execute(_V_INSERT, row)
        print(f"  INSERT  {v['name']}")

    conn.commit()
    conn.close()

    n_cats = len(CATEGORIES)
    n_veh  = len(VEHICLES)
    operational = sum(1 for v in VEHICLES if v.get("status", "operational") == "operational")
    print(f"\nDone — {n_cats} categories, {n_veh} vehicles seeded "
          f"({operational} operational).")


if __name__ == "__main__":
    seed()
