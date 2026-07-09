import json
import os
from pathlib import Path
import zipfile
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

def load_data_from_content(filepath: str | Path, prefix_to_strip: str | None = None):
    """
    Loads tweet data from a file path, handling .js and .zip archives.
    Then, parses the string or bytes object into a Python list.
    """
    content = ""
    if str(filepath).endswith(".zip"):
        logger.info(f"Processing ZIP archive: {filepath}")
        if not zipfile.is_zipfile(filepath):
            raise ValueError("Corrupted or invalid ZIP file.")
        with zipfile.ZipFile(filepath) as z_file:
            target_path = next((path for path in z_file.namelist() if path.endswith("data/tweets.js") or path == "tweets.js"), None)
            if not target_path:
                raise FileNotFoundError("Could not find 'tweets.js' or 'data/tweets.js' in the ZIP archive.")
            logger.info(f"Found '{target_path}' in ZIP file. Reading content.")
            with z_file.open(target_path) as target_file:
                content = target_file.read()
    elif str(filepath).endswith(".js"):
        logger.info(f"Processing .js file: {filepath}")
        with open(filepath, "rb") as f:
            content = f.read()
    else:
        raise ValueError("Unsupported file type. Please provide a .zip or .js file.")

    if isinstance(content, bytes):
        content = content.decode("utf-8")

    if prefix_to_strip:
        logger.info(f"Stripping prefix: '{prefix_to_strip}'")
        content = content.replace(prefix_to_strip, "")
    elif not content.lstrip().startswith("["):
        content = content[content.find("["):]

    try:
        tweets = json.loads(content)
        logger.info(f"Loaded {len(tweets)} records successfully")
        return tweets
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON: {e}")
        raise ValueError(f"Error parsing file: {e}")

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


def load_file(file, prefix_to_strip: str | None = None):
    "This fetches all data from tweets.js file or similar"
    # resolved = resolve_path(path)

    logger.info(f"Loading data from {path}")
    with open(path, mode="r", encoding="utf-8") as json_file:
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