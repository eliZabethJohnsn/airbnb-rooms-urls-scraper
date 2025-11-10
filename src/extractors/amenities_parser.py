import logging
from typing import Any, Dict, List, Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

def _find_amenities_sections(soup: BeautifulSoup) -> List[Any]:
    sections: List[Any] = []

    # Common Airbnb pattern: heading "What this place offers" or "Amenities"
    for heading in soup.find_all(["h2", "h3"]):
        text = heading.get_text(strip=True).lower()
        if "amenities" in text or "what this place offers" in text:
            section = heading.find_parent("section") or heading.parent
            if section and section not in sections:
                sections.append(section)

    # Fallback: any section with "Amenities" somewhere in text.
    if not sections:
        for section in soup.find_all("section"):
            if "amenities" in section.get_text(" ", strip=True).lower():
                sections.append(section)

    return sections

def _parse_amenity_list(section: Any) -> List[Dict[str, Any]]:
    values: List[Dict[str, Any]] = []
    for li in section.find_all("li"):
        title = li.get_text(" ", strip=True)
        if not title:
            continue

        lower = title.lower()
        # Airbnb sometimes shows unavailable amenities with text like "Not included".
        unavailable = "not available" in lower or "unavailable" in lower or "not included" in lower
        values.append(
            {
                "title": title,
                "available": not unavailable,
            },
        )
    return values

def extract_amenities(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """
    Extract amenities into a normalized structure:

    [
      {
        "title": "Bathroom",
        "values": [
          {"title": "Hair dryer", "available": true},
          ...
        ]
      },
      ...
    ]
    """
    sections = _find_amenities_sections(soup)
    if not sections:
        logger.debug("No amenities sections detected.")
        return []

    grouped: List[Dict[str, Any]] = []

    for section in sections:
        heading: Optional[str] = None
        # Try to find the nearest heading for this section.
        for tag_name in ("h2", "h3", "h4"):
            heading_tag = section.find(tag_name)
            if heading_tag:
                heading = heading_tag.get_text(strip=True)
                break

        title = heading or "Amenities"
        values = _parse_amenity_list(section)
        if values:
            grouped.append(
                {
                    "title": title,
                    "values": values,
                },
            )

    # Merge groups with the same title.
    merged: Dict[str, Dict[str, Any]] = {}
    for group in grouped:
        key = group["title"]
        existing = merged.get(key)
        if not existing:
            merged[key] = {"title": key, "values": list(group["values"])}
        else:
            existing["values"].extend(group["values"])

    return list(merged.values())