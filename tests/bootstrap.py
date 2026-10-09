#
# CVV is a continuous verification visualizer.
# Copyright (c) 2023 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""
Bootstrap the files that are normally produced by ``deploys/deployment.sh``.

``web/web/settings.py`` and ``web/web/db.json`` are gitignored and generated at
deploy time.  The test suite needs a working Django configuration, so it creates
the same files (if they are missing) pointing at a throw-away SQLite database.
Unit tests never touch the database, so no server is required.
"""

import json
import os

SETTINGS_TEMPLATE = "from web.development import *\nPERFORM_AUTO_SAVE = False\n"


def ensure_generated_files(root):
    web_dir = os.path.join(root, "web", "web")
    db_path = os.path.join(web_dir, "db.json")
    settings_path = os.path.join(web_dir, "settings.py")

    if not os.path.isfile(db_path):
        db = {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.path.join(root, "web", "test_db.sqlite3"),
        }
        with open(db_path, "w", encoding="utf8") as fp:
            json.dump(db, fp, indent=4)

    if not os.path.isfile(settings_path):
        with open(settings_path, "w", encoding="utf8") as fp:
            fp.write(SETTINGS_TEMPLATE)


if __name__ == "__main__":
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ensure_generated_files(_root)
