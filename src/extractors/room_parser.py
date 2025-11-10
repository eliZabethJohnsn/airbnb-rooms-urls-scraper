import logging
import time
from typing import Any, Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from .amenities_parser import extract_amenities
from .ratings_parser import extract_ratings

logger = logging.getLogger(__name__)

class RoomScrapeError(Exception):
    """Raised when scraping a single room fails in a non-recoverable way."""

def fetch_room_html(
    url: str,
    session: requests.Session,
    headers: Dict[str, str],
    timeout: float,
    max_retries: int,
) -> str:
    """Fetch room HTML with simple retry logic."""
    last_exc: Optional[Exception] = None

    for attempt in range(1, max_retries + 2):
        try:
            logger.debug("Fetching %s (attempt %d)", url, attempt)
            response = session.get(url, headers=headers, timeout=timeout)
            if response.status_code == 200:
                return response.text

            logger.warning(
                "Non-200 status %s for %s on attempt %d",
                response.status_code,
                url,
                attempt,
            )
        except requests.RequestException as exc:
            last_exc = exc
            logger.warning("Request error for %s on attempt %d: %s", url, attempt, exc)

        # Backoff between retries
        if attempt <= max_retries:
            time.sleep(1.0 * attempt)

    raise RoomScrapeError(f"Failed to fetch {url}") from last_exc

def _safe_get_text(node: Optional[Any]) -> str:
    if not node:
        return ""
    return node.get_text(strip=True)

def parse_property_type(soup: BeautifulSoup) -> Optional[str]:
    # Try known patterns first: title might contain property type.
    title_tag = soup.find("title")
    if title_tag and "-" in title_tag.text:
        title_text = title_tag.text.split("-")[0].strip()
        if title_text:
            return title_text

    # Fallback to heading text.
    heading = soup.find(["h1", "h2"])
    if heading:
        text = heading.get_text(strip=True)
        if text:
            return text

    return None

def parse_person_capacity(soup: BeautifulSoup) -> Optional[int]:
    # Look for text like "4 guests" or "up to 2 guests"
    body_text = soup.get_text(" ", strip=True)
    if not body_text:
        return None

    tokens = body_text.split()
    for idx, token in enumerate(tokens):
        if token.isdigit() and idx + 1 < len(tokens):
            next_token = tokens[idx + 1].lower()
            if "guest" in next_token:
                try:
                    return int(token)
                except ValueError:
                    continue
    return None

def parse_highlights(soup: BeautifulSoup) -> List[Dict[str, str]]:
    highlights: List[Dict[str, str]] = []

    # Heuristic: short bullet points near words like "Superhost", "Top", "Great location".
    body_text = soup.get_text("\n", strip=True)
    candidates = []
    for line in body_text.splitlines():
        lower = line.lower()
        if any(keyword in lower for keyword in ("superhost", "top", "great location")):
            candidates.append(line.strip())

    for line in candidates:
        # Create simple title/subtitle split.
        if ":" in line:
            title, subtitle = line.split(":", 1)
            highlights.append(
                {"title": title.strip(), "subtitle": subtitle.strip()},
            )
        else:
            highlights.append(
                {"title": line.strip(), "subtitle": ""},
            )

    return highlights

def parse_images(soup: BeautifulSoup) -> List[Dict[str, str]]:
    images: List[Dict[str, str]] = []
    for img in soup.find_all("img"):
        src = img.get("src") or img.get("data-src")
        if not src:
            continue
        caption = img.get("alt") or ""
        images.append({"url": src, "caption": caption})
    return images

def parse_host_details(soup: BeautifulSoup) -> Dict[str, Any]:
    # This is a heuristic; Airbnb's DOM may differ.
    host_section = None
    for heading in soup.find_all(["h2", "h3"]):
        if heading.string and "hosted by" in heading.string.lower():
            host_section = heading.parent
            break

    host_name: Optional[str] = None
    description: Optional[str] = None

    if host_section:
        heading_text = host_section.get_text(" ", strip=True)
        if "hosted by" in heading_text.lower():
            # Try to extract the name after "Hosted by"
            parts = heading_text.split("Hosted by")
            if len(parts) > 1:
                host_name = parts[1].strip().split()[0]

        paragraphs = host_section.find_all("p")
        if paragraphs:
            description = paragraphs[0].get_text(strip=True)

    return {
        "name": host_name,
        "description": description,
    }

def parse_price(soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
    body_text = soup.get_text(" ", strip=True)
    currency_symbols = ["$", "€", "£", "₹", "¥"]

    for sym in currency_symbols:
        if sym in body_text:
            idx = body_text.index(sym)
            snippet = body_text[idx : idx + 20]
            # Try to find a numeric sequence after the symbol.
            digits = []
            for ch in snippet[1:]:
                if ch.isdigit() or ch in ",.":
                    digits.append(ch)
                else:
                    break
            amount_str = "".join(digits).replace(",", "")
            try:
                amount = float(amount_str)
                return {
                    "currencySymbol": sym,
                    "amount": amount,
                    "raw": snippet.strip(),
                }
            except ValueError:
                continue

    return None

def scrape_room(
    url: str,
    session: requests.Session,
    headers: Dict[str, str],
    timeout: float,
    max_retries: int,
) -> Dict[str, Any]:
    """
    High-level entry point that fetches a single room and parses all relevant
    data into a structured dictionary.
    """
    html = fetch_room_html(
        url=url,
        session=session,
        headers=headers,
        timeout=timeout,
        max_retries=max_retries,
    )
    soup = BeautifulSoup(html, "html.parser")

    property_type = parse_property_type(soup)
    person_capacity = parse_person_capacity(soup)
    amenities = extract_amenities(soup)
    rating = extract_ratings(soup)
    highlights = parse_highlights(soup)
    images = parse_images(soup)
    host_details = parse_host_details(soup)
    price = parse_price(soup)

    result: Dict[str, Any] = {
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

    return result