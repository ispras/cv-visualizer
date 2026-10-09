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

# Root conftest for the CVV test suite.
#
# The project root is the ``web`` directory of the repository (it holds
# ``manage.py``), so it must be on ``sys.path`` for imports such as
# ``web.utils``, ``jobs.models`` or ``reports.mea.core`` to resolve.
#
# Dependencies can be installed into a local ``pylibs`` directory with
# ``make deps``; add it to ``sys.path`` when present.

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))

sys.path.insert(0, os.path.join(ROOT, "web"))

_pylibs = os.path.join(ROOT, "pylibs")
if os.path.isdir(_pylibs):
    sys.path.insert(0, _pylibs)

sys.path.insert(0, os.path.join(ROOT, "tests"))

from bootstrap import ensure_generated_files  # noqa: E402

ensure_generated_files(ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web.settings")

import django  # noqa: E402

django.setup()
