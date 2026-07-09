import json
from logger import logger
from pathlib import Path
import os

config_obj = None

def load_config(path)->dict:
    global config_obj

    if config_obj is None:  
        if not os.path.exists(path):
             logger.error(f"Path JSON file path does not exist '{path}'")
             raise Exception(f"Path JSON file path does not exist '{path}'")
        with open(path, mode='r', encoding="utf-8") as file:
            try:
                config_obj = json.load(file)
            except Exception as e:
                logger.error(f"Invalid JSON format in '{path}': {e}")
                raise e
    return config_obj


def validate_config(data:dict):
    if data.get("database_url", None) is None:
        logger.error(f"database_url not found in your config.json:{data}", exc_info=False)
        raise Exception("database_url not found in your config.json")
    if data.get("gemini_api_key", None) is None:
        logger.error(f"gemini_api_key not found in your config.json:{data}", exc_info=False)
        raise Exception("gemini_api_key not found in your config.json")
    return data



path = Path.cwd().parent / 'config.json'
env=validate_config(load_config(path))