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

"""Unit tests for jobs.configuration (CV core run configuration)."""

import io
import json
from types import SimpleNamespace

import pytest

from jobs.configuration import (
    Configuration,
    GetConfiguration,
    Parallelism,
    ConfigurationLogging,
    BooleanValues,
    str_to_int_or_float,
    get_configuration_value,
    CV_CORE_DEF_MODES,
)
from web.utils import BridgeException

SCHEDULING = ["LOW", "0", 100, "1"]
PARALLELISM = ["quick"]
RESOURCES = [1.0, 0, 100.0, None]
LOGGING = ["NONE", "brief", "NONE", "brief"]
BOOLEAN = [False, False, False, False, False, True]


def make_configuration():
    return Configuration(SCHEDULING, PARALLELISM, RESOURCES, LOGGING, BOOLEAN)


class _FileContext:
    """Minimal stand-in for a ``FieldFile`` usable as a context manager."""

    def __init__(self, content):
        self._content = content

    def __enter__(self):
        return io.BytesIO(self._content.encode("utf8"))

    def __exit__(self, *exc):
        return False


def fake_last_run(as_json):
    return SimpleNamespace(configuration=SimpleNamespace(file=_FileContext(as_json)))


# --------------------------------------------------------------------------- #
# str_to_int_or_float                                                         #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "value,expected",
    [
        (5, 5),
        (5.0, 5.0),
        ("1,5", 1.5),
        (" 42 ", 42),
        ("3.25", 3.25),
    ],
)
def test_str_to_int_or_float(value, expected):
    assert str_to_int_or_float(value) == expected


def test_str_to_int_or_float_rejects_garbage():
    with pytest.raises(ValueError):
        str_to_int_or_float("not a number")


# --------------------------------------------------------------------------- #
# Parallelism                                                                 #
# --------------------------------------------------------------------------- #

def test_parallelism_default_pack():
    assert Parallelism("quick").values == (1, 2, 1)
    assert Parallelism("very quick").values == (1, 1.0, 2)


def test_parallelism_unknown_pack():
    with pytest.raises(ValueError):
        Parallelism("no such pack")


def test_parallelism_pack_must_be_string():
    with pytest.raises(ValueError):
        Parallelism(1)


def test_parallelism_explicit_values_are_coerced():
    assert Parallelism(1, "2", "3.5").values == (1, 2, 3.5)


def test_parallelism_wrong_number_of_values():
    with pytest.raises(ValueError):
        Parallelism(1, 2)


def test_parallelism_representations():
    parallelism = Parallelism("quick")
    assert parallelism.packs() is Parallelism.parallelism_packs
    assert parallelism.for_request() == {
        "sub_jobs_proc_parallelism": "1",
        "tasks_gen_parallelism": "2",
        "results_processing_parallelism": "1",
    }
    assert parallelism.for_json() == {
        "Sub-jobs processing": 1,
        "Tasks generation": 2,
        "Results processing": 1,
    }
    assert parallelism.for_template()[0][0] == "sub_jobs_proc_parallelism"


# --------------------------------------------------------------------------- #
# ConfigurationLogging                                                        #
# --------------------------------------------------------------------------- #

def test_logging_default_formatter_by_name():
    logging = ConfigurationLogging("brief")
    assert logging.values == ["%(name)s %(levelname)5s> %(message)s"]


def test_logging_unknown_formatter_name():
    with pytest.raises(ValueError):
        ConfigurationLogging("no such formatter")


def test_logging_full_four_arguments():
    logging = ConfigurationLogging("INFO", "brief", "DEBUG", "detailed")
    assert logging.values[0] == "INFO"
    assert logging.values[2] == "DEBUG"
    assert "asctime" in logging.values[3]


def test_logging_invalid_level():
    with pytest.raises(ValueError):
        ConfigurationLogging("VERBOSE", "brief", "DEBUG", "detailed")


def test_logging_custom_formatter_passthrough():
    custom = "%(message)s custom"
    logging = ConfigurationLogging("INFO", custom, "DEBUG", custom)
    assert logging.values[1] == custom


def test_logging_empty_formatter():
    with pytest.raises(ValueError):
        ConfigurationLogging("INFO", "", "DEBUG", "brief")


def test_logging_wrong_number_of_arguments():
    with pytest.raises(ValueError):
        ConfigurationLogging("INFO", "brief")


def test_logging_representations():
    logging = ConfigurationLogging("INFO", "brief", "DEBUG", "detailed")
    assert logging.for_template()["console"] == {"level": "INFO", "formatter": logging.values[1]}
    assert logging.for_request("console_log_formatter") == {"console_log_formatter": "INFO"}
    assert logging.for_json()["loggers"][0]["handlers"][0]["name"] == "console"


# --------------------------------------------------------------------------- #
# BooleanValues                                                               #
# --------------------------------------------------------------------------- #

def test_boolean_values_for_json_keys():
    values = BooleanValues(*BOOLEAN)
    assert list(values.for_json()) == [
        "keep intermediate files",
        "upload input files of static verifiers",
        "upload other intermediate files",
        "ignore other instances",
        "ignore failed sub-jobs",
        "collect total code coverage",
    ]


def test_boolean_values_wrong_count():
    with pytest.raises(ValueError):
        BooleanValues(True, False)


def test_boolean_values_require_bool():
    with pytest.raises(ValueError):
        BooleanValues(1, 0, 0, 0, 0, 0)


def test_boolean_values_for_template():
    values = BooleanValues(*BOOLEAN)
    assert len(values.for_template()) == len(BooleanValues.boolean_names)


# --------------------------------------------------------------------------- #
# Configuration                                                               #
# --------------------------------------------------------------------------- #

def test_configuration_attributes():
    config = make_configuration()
    assert config.priority == "LOW"
    assert config.max_tasks == 100
    assert config.weight == "1"
    assert config.resources == [1.0, 0, 100.0, None]


def test_configuration_wrong_scheduling_length():
    with pytest.raises(ValueError):
        Configuration(["LOW", "0", 100], PARALLELISM, RESOURCES, LOGGING, BOOLEAN)


def test_configuration_unknown_priority():
    with pytest.raises(ValueError):
        Configuration(["NOPE", "0", 100, "1"], PARALLELISM, RESOURCES, LOGGING, BOOLEAN)


def test_configuration_unknown_weight():
    with pytest.raises(ValueError):
        Configuration(["LOW", "0", 100, "nope"], PARALLELISM, RESOURCES, LOGGING, BOOLEAN)


@pytest.mark.parametrize("max_tasks", ["x", 0, -5])
def test_configuration_invalid_max_tasks(max_tasks):
    with pytest.raises(ValueError):
        Configuration(["LOW", "0", max_tasks, "1"], PARALLELISM, RESOURCES, LOGGING, BOOLEAN)


def test_configuration_negative_ram():
    with pytest.raises(ValueError):
        Configuration(SCHEDULING, PARALLELISM, [-1.0, 0, 100.0, None], LOGGING, BOOLEAN)


def test_configuration_non_numeric_ram():
    with pytest.raises(ValueError):
        Configuration(SCHEDULING, PARALLELISM, ["big", 0, 100.0, None], LOGGING, BOOLEAN)


def test_configuration_cpu_cores_allow_zero_and_negative():
    config = Configuration(SCHEDULING, PARALLELISM, [1.0, -1, 100.0, None], LOGGING, BOOLEAN)
    assert config.resources[1] == -1


def test_configuration_empty_cpu_model_becomes_none():
    config = Configuration(SCHEDULING, PARALLELISM, [1.0, 0, 100.0, "  "], LOGGING, BOOLEAN)
    assert config.resources[3] is None


def test_configuration_non_string_cpu_model():
    with pytest.raises(ValueError):
        Configuration(SCHEDULING, PARALLELISM, [1.0, 0, 100.0, 42], LOGGING, BOOLEAN)


def test_configuration_as_json():
    config = make_configuration()
    data = json.loads(config.as_json("job-1"))
    assert data["identifier"] == "job-1"
    assert data["priority"] == "LOW"
    assert data["max solving tasks per sub-job"] == 100
    assert data["weight"] == "1"
    assert data["resource limits"] == {
        "memory size": 1000000000,
        "disk memory size": 100000000000,
        "number of CPU cores": 0,
        "CPU model": None,
    }
    assert data["keep intermediate files"] is False
    assert data["collect total code coverage"] is True


# --------------------------------------------------------------------------- #
# GetConfiguration                                                            #
# --------------------------------------------------------------------------- #

def test_get_configuration_by_name():
    getter = GetConfiguration(conf_name="production")
    assert getter.configuration.priority == "LOW"
    assert [mode[0] for mode in getter.modes] == [mode["id"] for mode in CV_CORE_DEF_MODES]


def test_get_configuration_unknown_name():
    with pytest.raises(ValueError):
        GetConfiguration(conf_name="no such mode")


def test_get_configuration_from_user_conf():
    getter = GetConfiguration(user_conf=[SCHEDULING, PARALLELISM, RESOURCES, LOGGING, BOOLEAN])
    assert getter.configuration.max_tasks == 100


def test_get_configuration_default_uses_settings_mode():
    # Generated settings use web.development, where DEF_CV_CORE_MODE == 'development'.
    from django.conf import settings

    getter = GetConfiguration()
    expected = GetConfiguration(conf_name=settings.DEF_CV_CORE_MODE)
    assert getter.configuration.priority == expected.configuration.priority


def test_get_configuration_last_run_roundtrip():
    as_json = make_configuration().as_json("job-1")
    getter = GetConfiguration(last_run=fake_last_run(as_json))
    assert getter.configuration.priority == "LOW"
    assert getter.configuration.max_tasks == 100
    assert getter.configuration.weight == "1"
    assert getter.configuration.resources == [1.0, 0, 100.0, None]


def test_get_configuration_file_conf_roundtrip():
    """Regression: file_conf used to build a 3-element scheduling list and crash."""
    original = make_configuration()
    stream = io.BytesIO(original.as_json("job-1").encode("utf8"))
    restored = GetConfiguration(file_conf=stream).configuration
    assert restored.priority == original.priority
    assert restored.max_tasks == original.max_tasks
    assert restored.weight == original.weight
    assert restored.resources == original.resources
    assert restored.parallelism.values == original.parallelism.values
    assert restored.logging.values == original.logging.values
    assert restored.boolean.values == original.boolean.values


# --------------------------------------------------------------------------- #
# get_configuration_value                                                     #
# --------------------------------------------------------------------------- #

def test_get_configuration_value_parallelism():
    value = get_configuration_value("parallelism", "quick")
    assert value["tasks_gen_parallelism"] == "2"


def test_get_configuration_value_formatter():
    value = get_configuration_value("console_log_formatter", "brief")
    assert value == {"console_log_formatter": "%(name)s %(levelname)5s> %(message)s"}


def test_get_configuration_value_unknown_name():
    with pytest.raises(BridgeException):
        get_configuration_value("no such name", "value")
