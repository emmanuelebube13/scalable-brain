import sys
import os
import json
sys.path.append(os.getcwd())
from src.common.storage import build_storage
storage = build_storage()

def read_json(key):
    try:
        storage.get_object(key, "/tmp/temp.json")
        with open("/tmp/temp.json") as f:
            print(json.dumps(json.load(f), indent=2))
    except Exception as e:
        print(f"Error reading {key}: {e}")

read_json("previous_model_set.json")
