from utils.google_places import place_details, place_photo_url


async def fetch_unsplash_images(subject: str, context: str) -> dict:
    """Stub: Unsplash entfernt. Bilder werden im Frontend via Google Places geladen."""
    return {"image_overview": None, "image_mood": None, "image_customer": None}


async def fetch_place_images(place_id: str) -> dict:
    """Google Places Fotos für einen Ort laden."""
    if not place_id:
        return {"image_overview": None, "image_mood": None, "image_customer": None}
    details = await place_details(place_id)
    photos = details.get("photos", [])
    return {
        "image_overview": place_photo_url(photos[0]["photo_reference"]) if len(photos) > 0 else None,
        "image_mood": place_photo_url(photos[1]["photo_reference"]) if len(photos) > 1 else None,
        "image_customer": place_photo_url(photos[2]["photo_reference"]) if len(photos) > 2 else None,
    }
