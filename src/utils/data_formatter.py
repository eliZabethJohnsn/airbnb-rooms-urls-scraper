from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

RATING_FIELDS = [
    "accuracy",
    "checking",
    "cleanliness",
    "communication",
    "location",
    "value",
    "guestSatisfaction",
    "reviewsCount",
]

def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        logger.debug("Unable to coerce %r to int.", value)
        return None

def _coerce_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        logger.debug("Unable to coerce %r to float.", value)
        return None

def _normalize_rating(raw_rating: Any) -> Dict[str, Any]:
    if not isinstance(raw_rating, dict):
        raw_rating = {}

    normalized: Dict[str, Any] = {}
    for field in RATING_FIELDS:
        value = raw_rating.get(field)
        if field == "reviewsCount":
            normalized[field] = _coerce_int(value)
        else:
            normalized[field] = _coerce_float(value)

    return normalized

def _normalize_amenities(raw_amenities: Any) -> List[Dict[str, Any]]:
    if not isinstance(raw_amenities, list):
        return []

    normalized: List[Dict[str, Any]] = []
    for group in raw_amenities:
        if not isinstance(group, dict):
            continue
        title = str(group.get("title") or "").strip()
        values_raw = group.get("values") or []
        if not isinstance(values_raw, list):
            continue

        values: List[Dict[str, Any]] = []
        for item in values_raw:
            if not isinstance(item, dict):
                continue
            item_title = str(item.get("title") or "").strip()
            if not item_title:
                continue
            available = bool(item.get("available", True))
            values.append({"title": item_title, "available": available})

        if values:
            normalized.append({"title": title or "Amenities", "values": values})

    return normalized

def _normalize_highlights(raw_highlights: Any) -> List[Dict[str, str]]:
    if not isinstance(raw_highlights, list):
        return []

    normalized: List[Dict[str, str]] = []
    for item in raw_highlights:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        subtitle = str(item.get("subtitle") or "").strip()
        if title or subtitle:
            normalized.append({"title": title, "subtitle": subtitle})
    return normalized

def _normalize_images(raw_images: Any) -> List[Dict[str, str]]:
    if not isinstance(raw_images, list):
        return []

    normalized: List[Dict[str, str]] = []
    for img in raw_images:
        if not isinstance(img, dict):
            continue
        url = str(img.get("url") or "").strip()
        if not url:
            continue
        caption = str(img.get("caption") or "").strip()
        normalized.append({"url": url, "caption": caption})
    return normalized

def _normalize_host_details(raw_host: Any) -> Dict[str, Any]:
    if not isinstance(raw_host, dict):
        raw_host = {}

    return {
        "name": (raw_host.get("name") or None),
        "description": (raw_host.get("description") or None),
    }

def _normalize_price(raw_price: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(raw_price, dict):
        return None

    amount = _coerce_float(raw_price.get("amount"))
    if amount is None:
        return None

    currency_symbol = str(raw_price.get("currencySymbol") or "").strip() or None
    raw = str(raw_price.get("raw") or "").strip() or None
    return {
        "currencySymbol": currency_symbol,
        "amount": amount,
        "raw": raw,
    }

def prepare_room_payload(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize a raw scraping result into a clean, JSON-serializable payload
    matching the documented output structure.
    """
    url = str(raw.get("url") or "").strip() or None
    property_type = str(raw.get("propertyType") or "").strip() or None
    person_capacity = _coerce_int(raw.get("personCapacity"))

    rating = _normalize_rating(raw.get("rating"))
    amenities = _normalize_amenities(raw.get("amenities"))
    highlights = _normalize_highlights(raw.get("highlights"))
    images = _normalize_images(raw.get("images"))
    host_details = _normalize_host_details(raw.get("hostDetails"))
    price = _normalize_price(raw.get("price"))

    payload: Dict[str, Any] = {
        "url": url,
        "propertyType": property_type,
        "personCapacity": person_capacity,
        "rating": rating,
        "amenities": amenities,
        "highlights": highlights,
        "images": images,
        "hostDetails": host_details,
        "price": price,
    }

    return payload