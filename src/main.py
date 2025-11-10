import argparse
import json
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List

import requests

from extractors.room_parser import scrape_room
from utils.data_formatter import prepare_room_payload

logger = logging.getLogger(__name__)

DEFAULT_SETTINGS: Dict[str, Any] = {
    "userAgent": "Mozilla/5.0 (compatible; AirbnbRoomsScraper/1.0; +https://bitbash.dev)",
    "requestTimeout": 20,
    "maxRetries": 2,
    "maxWorkers": 4,
}

def configure_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    )

def load_settings(settings_path: Path) -> Dict[str, Any]:
    if not settings_path.exists():
        logger.warning("Settings file %s not found, using defaults.", settings_path)
        return DEFAULT_SETTINGS.copy()

    try:
        with settings_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "Failed to read settings file %s (%s). Using defaults.",
            settings_path,
            exc,
        )
        return DEFAULT_SETTINGS.copy()

    if not isinstance(data, dict):
        logger.error(
            "Settings file %s does not contain a JSON object. Using defaults.",
            settings_path,
        )
        return DEFAULT_SETTINGS.copy()

    merged = DEFAULT_SETTINGS.copy()
    merged.update(data)
    return merged

def load_input(input_path: Path) -> List[str]:
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    with input_path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    urls: List[str] = []

    # Support several simple shapes:
    # - [{"startUrl": "https://..."}, ...]
    # - [{"url": "https://..."}, ...]
    # - [{"startUrls": ["https://...", ...]}, ...]
    # - {"startUrls": ["https://...", ...]}
    # - ["https://...", ...]
    if isinstance(raw, dict):
        candidates = raw.get("startUrls") or raw.get("urls")
        if isinstance(candidates, list):
            urls.extend(str(u) for u in candidates if u)
    elif isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                urls.append(item)
            elif isinstance(item, dict):
                if "startUrl" in item and item["startUrl"]:
                    urls.append(str(item["startUrl"]))
                elif "url" in item and item["url"]:
                    urls.append(str(item["url"]))
                elif "startUrls" in item and isinstance(item["startUrls"], list):
                    urls.extend(str(u) for u in item["startUrls"] if u)
    else:
        raise ValueError("Unsupported input JSON structure for URLs.")

    urls = [u for u in urls if isinstance(u, str) and u.strip()]
    if not urls:
        raise ValueError("No URLs found in the input file.")

    logger.info("Loaded %d URL(s) from %s", len(urls), input_path)
    return urls

def process_urls(urls: List[str], settings: Dict[str, Any]) -> List[Dict[str, Any]]:
    timeout = float(settings.get("requestTimeout", DEFAULT_SETTINGS["requestTimeout"]))
    max_retries = int(settings.get("maxRetries", DEFAULT_SETTINGS["maxRetries"]))
    max_workers = int(settings.get("maxWorkers", DEFAULT_SETTINGS["maxWorkers"]))
    user_agent = str(settings.get("userAgent", DEFAULT_SETTINGS["userAgent"]))

    headers = {
        "User-Agent": user_agent,
        "Accept-Language": "en-US,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    logger.info(
        "Starting scrape for %d URL(s) with up to %d workers.",
        len(urls),
        max_workers,
    )

    results: List[Dict[str, Any]] = []

    def worker(url: str) -> Dict[str, Any]:
        # A separate session per worker keeps thread safety simple.
        with requests.Session() as session:
            return scrape_room(
                url=url,
                session=session,
                headers=headers,
                timeout=timeout,
                max_retries=max_retries,
            )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(worker, url): url for url in urls}

        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                raw_room = future.result()
                if not raw_room:
                    logger.warning("No data returned for %s", url)
                    continue
                formatted = prepare_room_payload(raw_room)
                results.append(formatted)
                logger.info("Successfully scraped %s", url)
            except Exception as exc:  # noqa: BLE001
                logger.exception("Failed to scrape %s: %s", url, exc)

    logger.info("Finished scraping. Successfully collected %d record(s).", len(results))
    return results

def save_output(output_path: Path, payload: List[Dict[str, Any]]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info("Wrote %d record(s) to %s", len(payload), output_path)

def build_arg_parser() -> argparse.ArgumentParser:
    project_root = Path(__file__).resolve().parents[1]
    default_input = project_root / "data" / "sample_input.json"
    default_output = project_root / "data" / "sample_output.json"
    default_settings = Path(__file__).resolve().parent / "config" / "settings.example.json"

    parser = argparse.ArgumentParser(
        description="Scrape Airbnb room URLs into structured JSON.",
    )
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        default=default_input,
        help=f"Path to input JSON file (default: {default_input})",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=default_output,
        help=f"Path to output JSON file (default: {default_output})",
    )
    parser.add_argument(
        "-s",
        "--settings",
        type=Path,
        default=default_settings,
        help=f"Path to settings JSON file (default: {default_settings})",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging.",
    )
    return parser

def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    configure_logging(verbose=args.verbose)

    try:
        settings = load_settings(args.settings)
    except Exception as exc:  # noqa: BLE001
        logger.error("Unable to load settings: %s", exc)
        settings = DEFAULT_SETTINGS.copy()

    try:
        urls = load_input(args.input)
    except Exception as exc:  # noqa: BLE001
        logger.error("Unable to load input URLs: %s", exc)
        raise SystemExit(1) from exc

    payload = process_urls(urls, settings)
    save_output(args.output, payload)

if __name__ == "__main__":
    main()