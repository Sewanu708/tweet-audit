import json
import os
from pathlib import Path
from logger import logger

def resolve_path(filename, current_dir: str | None = None, max_recall: int = 3):
    if max_recall == 0:
        raise FileNotFoundError(f"Could not find '{filename}' within 3 levels of current directory")
    
    wd = Path(current_dir) if current_dir else Path.cwd()
    logger.info(f"Searching for '{filename}' in {wd}")

    if (wd / filename).exists():
        logger.info(f"Found '{filename}' at {wd / filename}")
        return wd / filename
    
    logger.info(f"Not found in {wd}, moving up...")
    return resolve_path(filename, wd.parent, max_recall - 1)


def fetch_data(path, prefix_to_strip: str | None = None):
    "This fetches all data from tweets.js file or similar"
    resolved = resolve_path(path)

    logger.info(f"Loading data from {resolved}")
    with open(resolved, mode="r", encoding="utf-8") as json_file:
        data = json_file.read()
        if prefix_to_strip:
            logger.info(f"Stripping prefix: '{prefix_to_strip}'")
            data = data.replace(prefix_to_strip, "")
        
        try:
            data = json.loads(data)
            logger.info(f"Loaded {len(data)} records successfully")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON: {e}")
            raise ValueError(f"Error parsing file: {e}")

    return data