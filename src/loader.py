import json
import os
from pathlib import Path
def fetch_data(path, prefix_to_strip:str|None = None):
    "This fetches all data from tweets.js file or similar"
    path = Path(path).resolve()
    if not os.path.exists(path):
        raise FileNotFoundError(f"Path does not exist: {path}")
    with open(path, mode="r", encoding="utf-8") as json_file:
        data = json_file.read()
        if prefix_to_strip:
            data = data.replace(prefix_to_strip,"")
        
        try:
            data = json.loads(data)
        except json.JSONDecodeError as e:
            raise ValueError(f"Error parsing file: {e}")

    return data