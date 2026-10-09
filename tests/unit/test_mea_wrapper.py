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

"""Unit tests for reports.mea.wrapper (pretty printing/parsing and args handling)."""

import copy
import json

import pytest

from reports.mea.core import (
    CET_OP,
    CET_OP_CALL,
    CET_OP_RETURN,
    CET_DISPLAY_NAME,
    CET_THREAD,
    CET_SOURCE,
    CET_LINE,
    CET_ID,
    COMPARISON_FUNCTION_EQUAL,
    TAG_ADDITIONAL_MODEL_FUNCTIONS,
    TAG_FILTERED_MODEL_FUNCTIONS,
    TAG_USE_NOTES,
    TAG_USE_WARNS,
)
from reports.mea.wrapper import (
    process_args,
    error_trace_pretty_print,
    error_trace_pretty_parse,
    compare_edited_traces,
    compare_converted_traces,
)


def cet(op, thread, name, source="src", line=1, cid=0):
    return {
        CET_OP: op,
        CET_THREAD: thread,
        CET_DISPLAY_NAME: name,
        CET_SOURCE: source,
        CET_LINE: line,
        CET_ID: cid,
    }


# --------------------------------------------------------------------------- #
# process_args                                                                #
# --------------------------------------------------------------------------- #

def test_process_args_splits_and_sorts_string():
    args = {TAG_ADDITIONAL_MODEL_FUNCTIONS: "b,a"}
    process_args(args)
    assert args[TAG_ADDITIONAL_MODEL_FUNCTIONS] == ["a", "b"]


def test_process_args_sort_is_in_place_for_list():
    args = {TAG_FILTERED_MODEL_FUNCTIONS: ["c", "a", "b"]}
    process_args(args)
    assert args[TAG_FILTERED_MODEL_FUNCTIONS] == ["a", "b", "c"]


def test_process_args_as_str_joins_values():
    args = {TAG_FILTERED_MODEL_FUNCTIONS: ["c", "a", "b"]}
    process_args(args, as_str=True)
    assert args[TAG_FILTERED_MODEL_FUNCTIONS] == "a,b,c"


def test_process_args_removes_empty_values():
    args = {TAG_USE_NOTES: "", TAG_USE_WARNS: "x"}
    process_args(args)
    assert TAG_USE_NOTES not in args
    assert args[TAG_USE_WARNS] == ["x"]


def test_process_args_keeps_boolean_flags():
    args = {TAG_USE_NOTES: True}
    process_args(args)
    assert args[TAG_USE_NOTES] is True


# --------------------------------------------------------------------------- #
# error_trace_pretty_print / error_trace_pretty_parse                         #
# --------------------------------------------------------------------------- #

def test_pretty_print_renders_calls_with_line_numbers():
    trace = [cet(CET_OP_CALL, 0, "main", line=10)]
    text = error_trace_pretty_print(trace)
    assert "|main" in text
    assert text.endswith("\n")


def test_pretty_print_accepts_json_string():
    trace = [cet(CET_OP_CALL, 0, "main", line=10)]
    text = error_trace_pretty_print(json.dumps(trace))
    assert "|main" in text


def test_pretty_print_skips_unmatched_return():
    trace = [cet(CET_OP_CALL, 0, "main", line=1), cet(CET_OP_RETURN, 0, "other", line=2)]
    text = error_trace_pretty_print(trace)
    assert "|main" in text
    assert "|other" not in text


def test_pretty_print_parse_roundtrip_nested_calls():
    trace = [
        cet(CET_OP_CALL, 0, "main", line=1),
        cet(CET_OP_CALL, 0, "foo", line=2),
        cet(CET_OP_RETURN, 0, "foo", line=3),
        cet(CET_OP_RETURN, 0, "main", line=4),
    ]
    text = error_trace_pretty_print(copy.deepcopy(trace))
    parsed = error_trace_pretty_parse(text)
    assert [(e[CET_OP], e[CET_DISPLAY_NAME]) for e in parsed] == [
        (CET_OP_CALL, "main"),
        (CET_OP_CALL, "foo"),
        (CET_OP_RETURN, "foo"),
        (CET_OP_RETURN, "main"),
    ]


def test_pretty_parse_rejects_garbage():
    with pytest.raises(ValueError):
        error_trace_pretty_parse("this line cannot be parsed")


def test_pretty_print_parse_roundtrip_multiple_threads():
    trace = [
        cet(CET_OP_CALL, 0, "main", line=1),
        cet(CET_OP_RETURN, 0, "main", line=2),
        cet(CET_OP_CALL, 1, "worker", line=3),
        cet(CET_OP_RETURN, 1, "worker", line=4),
    ]
    text = error_trace_pretty_print(copy.deepcopy(trace))
    parsed = error_trace_pretty_parse(text)
    assert [e[CET_DISPLAY_NAME] for e in parsed] == ["main", "main", "worker", "worker"]


# --------------------------------------------------------------------------- #
# comparison helpers                                                          #
# --------------------------------------------------------------------------- #

def test_compare_edited_traces_equal():
    trace = [cet(CET_OP_CALL, 0, "main", line=1)]
    is_equal, similarity = compare_edited_traces(
        copy.deepcopy(trace), copy.deepcopy(trace), COMPARISON_FUNCTION_EQUAL, 100
    )
    assert is_equal is True
    assert similarity == 1.0


def test_compare_edited_traces_accepts_json_strings():
    trace = [cet(CET_OP_CALL, 0, "main", line=1)]
    is_equal, _ = compare_edited_traces(
        json.dumps(trace), json.dumps(trace), COMPARISON_FUNCTION_EQUAL, 100
    )
    assert is_equal is True


def test_compare_converted_traces_equal():
    trace = [cet(CET_OP_CALL, 0, "main", line=1)]
    assert compare_converted_traces(
        copy.deepcopy(trace), copy.deepcopy(trace), COMPARISON_FUNCTION_EQUAL, 100
    ) is True


def test_compare_converted_traces_below_threshold():
    et1 = [cet(CET_OP_CALL, 0, "main", line=1)]
    et2 = [cet(CET_OP_CALL, 0, "other", line=1)]
    assert compare_converted_traces(et1, et2, COMPARISON_FUNCTION_EQUAL, 100) == 0.0
