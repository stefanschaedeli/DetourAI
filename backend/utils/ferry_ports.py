"""Faehr-Erkennung und Insel-Routing Hilfsfunktionen."""
from typing import Optional


FERRY_SPEED_KMH = 30.0  # Durchschnittliche Faehrgeschwindigkeit (D-07)


ISLAND_GROUPS: dict[str, dict] = {
    "cyclades": {
        "bbox": {"min_lat": 36.3, "max_lat": 37.7, "min_lon": 24.4, "max_lon": 26.3},
        "center": (37.0, 25.4),
        "primary_ports": ["Piraeus", "Rafina"],
        "ferry_hours_range": (4, 9),
    },
    "dodecanese": {
        "bbox": {"min_lat": 35.9, "max_lat": 37.2, "min_lon": 26.7, "max_lon": 28.3},
        "center": (36.4, 27.9),
        "primary_ports": ["Piraeus", "Rafina"],
        "ferry_hours_range": (8, 18),
    },
    "ionian": {
        "bbox": {"min_lat": 38.6, "max_lat": 39.8, "min_lon": 19.6, "max_lon": 20.8},
        "center": (39.6, 19.9),
        "primary_ports": ["Igoumenitsa", "Patras"],
        "ferry_hours_range": (1, 3),
    },
    "corsica": {
        "bbox": {"min_lat": 41.4, "max_lat": 43.0, "min_lon": 8.5, "max_lon": 9.6},
        "center": (42.15, 9.1),
        "primary_ports": ["Nice", "Marseille", "Livorno", "Genua"],
        "ferry_hours_range": (4, 12),
    },
    "sardinia": {
        "bbox": {"min_lat": 38.8, "max_lat": 41.3, "min_lon": 8.1, "max_lon": 9.8},
        "center": (40.0, 9.0),
        "primary_ports": ["Civitavecchia", "Livorno", "Genua", "Bonifacio"],
        "ferry_hours_range": (5, 12),
    },
    "sicily": {
        "bbox": {"min_lat": 36.6, "max_lat": 38.3, "min_lon": 12.4, "max_lon": 15.7},
        "center": (37.5, 14.0),
        "primary_ports": ["Villa San Giovanni", "Salerno", "Napoli"],
        "ferry_hours_range": (0.3, 10),
    },
    "balearics": {
        "bbox": {"min_lat": 38.6, "max_lat": 40.1, "min_lon": 1.1, "max_lon": 4.4},
        "center": (39.5, 2.9),
        "primary_ports": ["Barcelona", "Valencia", "Denia"],
        "ferry_hours_range": (4, 9),
    },
    "croatian_islands": {
        "bbox": {"min_lat": 42.4, "max_lat": 44.3, "min_lon": 14.7, "max_lon": 17.3},
        "center": (43.2, 16.4),
        "primary_ports": ["Split", "Dubrovnik", "Zadar", "Rijeka"],
        "ferry_hours_range": (0.5, 4),
    },
}


def is_island_destination(coords: tuple[float, float]) -> Optional[str]:
    """Gibt den Inselgruppen-Namen zurueck wenn Koordinaten in einer bekannten Bbox liegen, sonst None."""
    lat, lon = coords
    for group_name, group in ISLAND_GROUPS.items():
        bbox = group["bbox"]
        if (bbox["min_lat"] <= lat <= bbox["max_lat"] and
                bbox["min_lon"] <= lon <= bbox["max_lon"]):
            return group_name
    return None


def validate_island_coordinates(
    place_name: str, coords: tuple[float, float], expected_island_group: str
) -> bool:
    """Prueft ob Koordinaten innerhalb der erwarteten Inselgruppen-Bbox liegen."""
    group = ISLAND_GROUPS.get(expected_island_group)
    if not group:
        return True  # Unbekannte Gruppe, kann nicht validiert werden
    bbox = group["bbox"]
    lat, lon = coords
    return (bbox["min_lat"] <= lat <= bbox["max_lat"] and
            bbox["min_lon"] <= lon <= bbox["max_lon"])


def ferry_estimate(straight_km: float) -> dict:
    """Schaetzt Faehrdauer basierend auf Luftlinie. Gibt dict mit hours, km, is_ferry zurueck."""
    hours = round(straight_km / FERRY_SPEED_KMH, 1)
    return {
        "hours": hours,
        "km": round(straight_km, 0),
        "is_ferry": True,
    }


def get_ferry_ports(island_group: str) -> list[str]:
    """Gibt die primaeren Faehrhaefen fuer eine Inselgruppe zurueck, oder leere Liste."""
    group = ISLAND_GROUPS.get(island_group)
    if not group:
        return []
    return group.get("primary_ports", [])
