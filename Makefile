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

PYTHON ?= python3
PIP    ?= $(PYTHON) -m pip
PYLIBS ?= pylibs

export PYTHONPATH := $(CURDIR)/$(PYLIBS):$(CURDIR)/web

.PHONY: help deps test-setup test-unit test clean-test

help:
	@echo "Available targets:"
	@echo "  deps        Install test/runtime dependencies into $(PYLIBS)/"
	@echo "  test-setup  Generate web/web/settings.py and web/web/db.json if missing"
	@echo "  test-unit   Run the unit test suite (tests/unit)"
	@echo "  test        Alias for test-unit (all available suites)"
	@echo "  clean-test  Remove test caches and the throw-away SQLite database"

# Install dependencies into a local directory so that no root access is required.
# The Docker image and CI install the same packages system-wide.
deps:
	$(PIP) install --target $(PYLIBS) \
	    requests ujson "django==4.2" pluggy py attrs six more-itertools ply \
	    pytest atomicwrites pycparser sympy pytz

# deployment.sh generates these files for real deployments; tests need them too.
test-setup:
	$(PYTHON) tests/bootstrap.py

test-unit: test-setup
	$(PYTHON) -m pytest tests/unit -v

test: test-unit

clean-test:
	rm -rf .pytest_cache
	rm -f web/test_db.sqlite3
