import json
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
WEB = os.path.join(ROOT, "web")

if WEB not in sys.path:
    sys.path.insert(0, WEB)

db_path = os.path.join(WEB, "web", "db.json")
settings_path = os.path.join(WEB, "web", "settings.py")

if not os.path.exists(db_path):
    with open(db_path, "w", encoding="utf8") as fp:
        json.dump({"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}, fp, indent=4)

if not os.path.exists(settings_path):
    with open(settings_path, "w", encoding="utf8") as fp:
        fp.write("from web.development import *\nPERFORM_AUTO_SAVE = False\n")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web.settings")

import django

django.setup()
