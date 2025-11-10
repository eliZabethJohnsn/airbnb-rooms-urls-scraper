import logging
import re
from typing import Any, Dict, Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

RATING_FIELDS = [
    "accuracy",
    "checking",
    "cleanliness",
    "communication",
    "location",
    "value",
]

def _parse_overall_rating_and_reviews(text: str) -> (Optional[float], Optional[int]):
    # Match patterns like "4.97 · 36 reviews"
    rating_match = re.search(r"(\d\.\d{1,2})", text)
    reviews_match = re.search(r"(\d+)\s+review", text, re.IGNORECASE)

    overall = float(rating_match.group(1)) if rating_match else None
    reviews = int(reviews_match.group(1)) if reviews_match else None
    return overall, reviews

def _parse_subratings(soup: BeautifulSoup) -> Dict[str, Optional[float]]:
    subratings: Dict[str, Optional[float]] = {field: None for field in RATING_FIELDS}

    # Airbnb often uses rows with a label and a score, e.g., "Cleanliness 4.9"
    for row in soup.find_all(["div", "li"]):
        text = row.get_text(" ", strip=True)
        lower = text.lower()
        for field in RATING_FIELDS:
            if field in lower:
                match = re.search(r"(\d\.\d{1,2})", text)
                if match:
                    try:
                        subratings[field] = float(match.group(1))
                    except ValueError:
                        logger.debug("Unable to parse subrating from %r", text)
                break

    return subratings

def extract_ratings(soup: BeautifulSoup) -> Dict[str, Any]:
    """
    Extract ratings into a normalized structure:

    {
      "accuracy": 4.94,
      "checking": 5.0,
      "cleanliness": 4.97,
      "communication": 5.0,
      "location": 4.97,
      "value": 4.94,
      "guestSatisfaction": 4.97,
      "reviewsCount": 36
    }
    """
    body_text = soup.get_text(" ", strip=True)
    overall, reviews_count = _parse_overall_rating_and_reviews(body_text)

    subratings = _parse_subratings(soup)

    # Guest satisfaction can be approximated as overall rating when available.
    guest_satisfaction = overall

    rating: Dict[str, Any] = {
        **{field: subratings.get(field) for field in RATING_FIELDS},
        "guestSatisfaction": guest_satisfaction,
        "reviewsCount": reviews_count,
    }

    return rating