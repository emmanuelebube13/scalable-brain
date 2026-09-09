import sys
import os
sys.path.append(os.getcwd())
from src.common.storage import build_storage
storage = build_storage()

print("Root level objects:")
for obj in storage.list(""):
    if not obj.startswith("system1/") and not obj.startswith("models/"):
        print(obj)
