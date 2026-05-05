"""
Cannabis grow-room CSV adapter.

Normalises column names exported from common platforms (Aroya, TrolMaster,
Growlink, Priva, Argus, Wadsworth, Metrc, Canix, GrowerIQ, Trym, generic
environmental loggers) into a stable set of signal names the engine can use.

Usage
-----
    from neraium.adapters.cannabis import normalise_dataframe, build_cannabis_context

    df_clean = normalise_dataframe(df)          # rename & filter columns
    context  = build_cannabis_context(df_clean) # signal → subsystem mapping
"""

import re

import pandas as pd

# ---------------------------------------------------------------------------
# Canonical signal names  →  human label, subsystem, unit hint
# ---------------------------------------------------------------------------
_SIGNALS: dict[str, tuple[str, str, str]] = {
    # environment
    "temperature_c":       ("Air Temp",             "environment",  "°C"),
    "temperature_f":       ("Air Temp",             "environment",  "°F"),
    "humidity_rh":         ("Relative Humidity",    "environment",  "% RH"),
    "vpd_kpa":             ("VPD",                  "environment",  "kPa"),
    "co2_ppm":             ("CO₂",                  "environment",  "ppm"),
    "dew_point_c":         ("Dew Point",            "environment",  "°C"),
    "canopy_temp_c":       ("Canopy Temp",          "environment",  "°C"),
    # lighting
    "ppfd_umol":           ("PPFD",                 "lighting",     "µmol/m²/s"),
    "dli_mol":             ("DLI",                  "lighting",     "mol/m²/day"),
    "par_umol":            ("PAR",                  "lighting",     "µmol/m²/s"),
    # irrigation / root zone
    "ph":                  ("Nutrient pH",          "irrigation",   "pH"),
    "ec_ms_cm":            ("Electrical Conductivity", "irrigation","mS/cm"),
    "substrate_moisture":  ("Substrate Moisture",   "irrigation",   "% VWC"),
    "substrate_temp_c":    ("Root Zone Temp",       "irrigation",   "°C"),
    "water_flow_lph":      ("Water Flow",           "irrigation",   "L/h"),
    "runoff_ph":           ("Runoff pH",            "irrigation",   "pH"),
    "runoff_ec":           ("Runoff EC",            "irrigation",   "mS/cm"),
    # HVAC / mechanical
    "hvac_load_pct":       ("HVAC Load",            "hvac",         "%"),
    "fan_speed_pct":       ("Fan Speed",            "hvac",         "%"),
    "dehumidifier_pct":    ("Dehumidifier",         "hvac",         "%"),
    # compliance / inventory
    "plant_count":         ("Plant Count",          "compliance",   "plants"),
    "inventory_g":         ("Inventory",            "compliance",   "g"),
    "waste_g":             ("Waste",                "compliance",   "g"),
    # yield / business
    "yield_g_per_plant":   ("Yield/Plant",          "yield",        "g"),
    "yield_g_per_sqft":    ("Yield/ft²",            "yield",        "g/ft²"),
    "energy_kwh":          ("Energy",               "yield",        "kWh"),
}

# ---------------------------------------------------------------------------
# Platform-specific column aliases  →  canonical name
# Lowercase, stripped of spaces/underscores for fuzzy matching.
# ---------------------------------------------------------------------------
_ALIASES: dict[str, str] = {
    # temperature
    "temp":                  "temperature_c",
    "temperature":           "temperature_c",
    "air_temp":              "temperature_c",
    "room_temp":             "temperature_c",
    "temp_c":                "temperature_c",
    "temp_f":                "temperature_f",
    "temperature_f":         "temperature_f",
    "airtemp":               "temperature_c",
    "airtemperaturec":       "temperature_c",
    "airtemperaturef":       "temperature_f",
    "canopytemp":            "canopy_temp_c",
    "canopy_temp":           "canopy_temp_c",
    "leaf_temp":             "canopy_temp_c",
    "leaftemp":              "canopy_temp_c",
    # humidity
    "humidity":              "humidity_rh",
    "rh":                    "humidity_rh",
    "relative_humidity":     "humidity_rh",
    "humidity_rh":           "humidity_rh",
    "relativehumidity":      "humidity_rh",
    # vpd
    "vpd":                   "vpd_kpa",
    "vpd_kpa":               "vpd_kpa",
    "vapor_pressure_deficit":"vpd_kpa",
    "vaporpressuredeficit":  "vpd_kpa",
    # co2
    "co2":                   "co2_ppm",
    "co2_ppm":               "co2_ppm",
    "carbon_dioxide":        "co2_ppm",
    "carbondioxide":         "co2_ppm",
    "co2ppm":                "co2_ppm",
    # ppfd / dli / par
    "ppfd":                  "ppfd_umol",
    "ppfd_umol":             "ppfd_umol",
    "light_intensity":       "ppfd_umol",
    "lightintensity":        "ppfd_umol",
    "par":                   "par_umol",
    "par_umol":              "par_umol",
    "dli":                   "dli_mol",
    "dli_mol":               "dli_mol",
    # pH
    "ph":                    "ph",
    "ph_water":              "ph",
    "nutrient_ph":           "ph",
    "res_ph":                "ph",
    "reservoirph":           "ph",
    "solution_ph":           "ph",
    "runoff_ph":             "runoff_ph",
    # EC
    "ec":                    "ec_ms_cm",
    "ec_ms_cm":              "ec_ms_cm",
    "electrical_conductivity":"ec_ms_cm",
    "electricalconductivity":"ec_ms_cm",
    "nutrient_ec":           "ec_ms_cm",
    "res_ec":                "ec_ms_cm",
    "solution_ec":           "ec_ms_cm",
    "tds":                   "ec_ms_cm",
    "runoff_ec":             "runoff_ec",
    # substrate / root zone
    "substrate_moisture":    "substrate_moisture",
    "vwc":                   "substrate_moisture",
    "volumetric_water_content":"substrate_moisture",
    "moisture":              "substrate_moisture",
    "substrate_temp":        "substrate_temp_c",
    "rootzone_temp":         "substrate_temp_c",
    "root_zone_temp":        "substrate_temp_c",
    # hvac
    "fan_speed":             "fan_speed_pct",
    "fanspeed":              "fan_speed_pct",
    "hvac_load":             "hvac_load_pct",
    "hvacload":              "hvac_load_pct",
    "dehumidifier":          "dehumidifier_pct",
    # compliance
    "plant_count":           "plant_count",
    "plantcount":            "plant_count",
    "inventory":             "inventory_g",
    "inventory_weight":      "inventory_g",
    "waste":                 "waste_g",
    "waste_weight":          "waste_g",
    # dew point
    "dew_point":             "dew_point_c",
    "dewpoint":              "dew_point_c",
    # yield
    "yield_per_plant":       "yield_g_per_plant",
    "yield_g_plant":         "yield_g_per_plant",
    "yield_sqft":            "yield_g_per_sqft",
    "energy":                "energy_kwh",
    "energy_kwh":            "energy_kwh",
    "water_flow":            "water_flow_lph",
}

# Columns that are metadata / timestamps — drop, never feed to the engine
_DROP_PATTERNS = re.compile(
    r"\b(timestamp|date|time|room|zone|location|batch|strain|"
    r"employee|plant_id|name|tag|lot|transfer|state|notes?|comment)\b",
    re.IGNORECASE,
)


def _normalise_key(col: str) -> str:
    """Strip punctuation, spaces → lowercase for alias lookup."""
    return re.sub(r"[\s\-/]+", "_", col.strip().lower())


def normalise_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a new DataFrame with:
      - non-signal columns (timestamps, text metadata) dropped
      - column names mapped to canonical cannabis signal names
      - unknown numeric columns kept under their original name
      - all values cast to float, NaN rows dropped
    """
    rename_map: dict[str, str] = {}
    drop_cols: list[str] = []

    for col in df.columns:
        if _DROP_PATTERNS.search(col):
            drop_cols.append(col)
            continue
        key = _normalise_key(col)
        canonical = _ALIASES.get(key)
        if canonical:
            rename_map[col] = canonical

    df = df.drop(columns=drop_cols, errors="ignore")
    df = df.rename(columns=rename_map)
    df = df.select_dtypes(include="number")
    df = df.dropna()
    return df


def build_cannabis_context(df: pd.DataFrame) -> dict[str, dict]:
    """
    Build a sensor context dict from the columns of a normalised DataFrame.
    Columns that match a canonical name get proper labels and subsystem tags.
    Unknown columns fall back to a generated title.
    """
    context: dict[str, dict] = {}
    for col in df.columns:
        if col in _SIGNALS:
            label, subsystem, unit = _SIGNALS[col]
            context[col] = {
                "name": f"{label} ({unit})" if unit else label,
                "subsystem": subsystem,
                "component": col,
            }
        else:
            # Unknown numeric signal — keep it, give it a readable name
            context[col] = {
                "name": col.replace("_", " ").title(),
                "subsystem": "other",
                "component": col,
            }
    return context


def detect_platform(df: pd.DataFrame) -> str:
    """
    Best-effort platform detection from raw column names.
    Returns a human-readable string; used only for logging.
    """
    cols_lower = {c.lower() for c in df.columns}

    if any("metrc" in c or "plant_tag" in c or "package_tag" in c for c in cols_lower):
        return "Metrc"
    if any("aroya" in c or "substrate_moisture" in c and "vpd" in c for c in cols_lower):
        return "Aroya"
    if "trolmaster" in " ".join(cols_lower):
        return "TrolMaster"
    if any("growlink" in c for c in cols_lower):
        return "Growlink"
    if any("priva" in c for c in cols_lower):
        return "Priva"
    if any("argus" in c for c in cols_lower):
        return "Argus"
    if any("trym" in c or "groweriq" in c or "artemis" in c for c in cols_lower):
        return "Cultivation management"
    if {"temp", "humidity", "vpd", "co2"} & cols_lower:
        return "Generic environmental logger"
    return "Unknown"
