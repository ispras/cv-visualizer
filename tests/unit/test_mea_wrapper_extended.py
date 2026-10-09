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
Thorough unit tests for reports.mea.wrapper.

They cover error-trace pretty printing/parsing (including multi-thread and
overlapping-thread traces), argument post-processing and the two public
comparison helpers.
"""

import copy
import json

import pytest

from reports.mea.core import (
    convert_error_trace,
    CET_OP,
    CET_OP_CALL,
    CET_OP_RETURN,
    CET_OP_ASSUME,
    CET_OP_ASSIGN,
    CET_OP_NOTE,
    CET_OP_WARN,
    CET_DISPLAY_NAME,
    CET_THREAD,
    CET_SOURCE,
    CET_LINE,
    CET_ID,
    CONVERSION_FUNCTION_CALL_TREE,
    COMPARISON_FUNCTION_EQUAL,
    COMPARISON_FUNCTION_INCLUDE,
    TAG_ADDITIONAL_MODEL_FUNCTIONS,
    TAG_FILTERED_MODEL_FUNCTIONS,
    TAG_USE_NOTES,
    TAG_USE_WARNS,
    TAG_IGNORE_NOTES_TEXT,
)
from reports.mea.wrapper import (
    error_trace_pretty_print,
    error_trace_pretty_parse,
    process_args,
    compare_edited_traces,
    compare_converted_traces,
    CET_END,
)
from mea_utils import cet, random_error_trace, as_tuples


def calls(thread, *names):
    return [cet(CET_OP_CALL, thread, name, cid=i) for i, name in enumerate(names)]


def returns(thread, *names):
    return [cet(CET_OP_RETURN, thread, name, cid=i) for i, name in enumerate(names)]


def sequences_by_thread(error_trace):
    order = []
    per_thread = {}
    for elem in error_trace:
        thread = elem[CET_THREAD]
        if thread not in per_thread:
            per_thread[thread] = []
            order.append(thread)
        per_thread[thread].append((elem[CET_OP], elem[CET_DISPLAY_NAME]))
    return [per_thread[thread] for thread in order]


# --------------------------------------------------------------------------- #
# error_trace_pretty_print / error_trace_pretty_parse                         #
# --------------------------------------------------------------------------- #

def test_pretty_print_returns_empty_string_for_empty_trace():
    assert error_trace_pretty_print([]) == ""
    assert error_trace_pretty_parse("") == []


def test_pretty_print_line_numbers_are_right_justified():
    text = error_trace_pretty_print([cet(CET_OP_CALL, 0, "main", line="123")])
    assert text.startswith("  123\t|main")


def test_pretty_print_renders_all_operation_kinds():
    trace = [
        cet(CET_OP_CALL, 0, "main", source="m.c", line="1"),
        cet(CET_OP_ASSUME, 0, "x > 0", source="x > 0", line="2"),
        cet(CET_OP_ASSIGN, 0, "a = 1", source="a = 1", line="3"),
        cet(CET_OP_NOTE, 0, "note", source="m.c", line="4"),
        cet(CET_OP_WARN, 0, "warn", source="m.c", line="5"),
    ]
    text = error_trace_pretty_print(trace)
    assert "|main" in text
    assert "| ASSUME(x > 0)" in text
    assert "| ASSIGN: 'a = 1'" in text
    assert "| NOTE: 'note'" in text
    assert "| WARN: 'warn'" in text
    assert text.rstrip().endswith(CET_END)


def test_pretty_print_renders_negated_assume():
    trace = [cet(CET_OP_ASSUME, 0, "", source="x > 0", line="1")]
    assert "ASSUME(!(x > 0))" in error_trace_pretty_print(trace)


def test_pretty_print_does_not_mutate_input():
    trace = random_error_trace(11, n_threads=3)
    converted = convert_error_trace(trace, CONVERSION_FUNCTION_CALL_TREE, {})
    snapshot = copy.deepcopy(converted)
    error_trace_pretty_print(converted)
    assert converted == snapshot
    assert all(isinstance(elem[CET_THREAD], int) for elem in converted)


def test_pretty_print_skips_unmatched_return():
    # A return without a matching call must not break the (malformed) trace printing.
    trace = [cet(CET_OP_CALL, 0, "a", line="1"), cet(CET_OP_RETURN, 0, "b", line="2")]
    text = error_trace_pretty_print(trace)
    assert text.count("|a") == 1
    assert "|b" not in text


def test_pretty_print_skips_return_without_any_call():
    trace = [cet(CET_OP_RETURN, 0, "a", line="5")]
    assert error_trace_pretty_print(trace).count(CET_END) == 1


def test_pretty_print_accepts_json_string():
    trace = calls(0, "main")
    assert error_trace_pretty_print(json.dumps(trace)) == error_trace_pretty_print(trace)


@pytest.mark.parametrize("seed", list(range(30)))
def test_pretty_round_trip_preserves_each_thread(seed):
    trace = random_error_trace(seed, n_threads=(seed % 4) + 1)
    converted = convert_error_trace(trace, CONVERSION_FUNCTION_CALL_TREE, {})
    parsed = error_trace_pretty_parse(error_trace_pretty_print(converted))
    assert sequences_by_thread(parsed) == sequences_by_thread(converted)


def test_pretty_round_trip_overlapping_and_interleaved_threads():
    net = calls(0, "a", "b") + calls(1, "x", "y") + returns(0, "b", "a") + returns(1, "y", "x")
    parsed = error_trace_pretty_parse(error_trace_pretty_print(net))
    assert sequences_by_thread(parsed) == [
        [(CET_OP_CALL, "a"), (CET_OP_CALL, "b"), (CET_OP_RETURN, "b"), (CET_OP_RETURN, "a")],
        [(CET_OP_CALL, "x"), (CET_OP_CALL, "y"), (CET_OP_RETURN, "y"), (CET_OP_RETURN, "x")],
    ]


def test_pretty_print_groups_same_thread_together():
    # Thread 0 elements are the 1st and 3rd; both must appear in one contiguous block.
    net = [cet(CET_OP_CALL, 0, "a", line="1"),
           cet(CET_OP_CALL, 1, "b", line="2"),
           cet(CET_OP_RETURN, 0, "a", line="3"),
           cet(CET_OP_RETURN, 1, "b", line="4")]
    text = error_trace_pretty_print(net)
    assert text.count(CET_END) == 2
    first_block, second_block = text.split(CET_END)[:2]
    assert "|a" in first_block and "|b" not in first_block
    assert "|b" in second_block and "|a" not in second_block


def test_pretty_parse_reconstructs_nested_returns():
    text = "    1\t|a\n    2\t| b\n    0\t|__ERROR__\n"
    parsed = error_trace_pretty_parse(text)
    assert [(e[CET_OP], e[CET_DISPLAY_NAME]) for e in parsed] == [
        (CET_OP_CALL, "a"), (CET_OP_CALL, "b"), (CET_OP_RETURN, "b"), (CET_OP_RETURN, "a"),
    ]


def test_pretty_parse_reads_auxiliary_operations():
    text = ("    1\t|main\n"
            "    2\t| ASSUME(x > 0)\n"
            "    3\t| ASSUME(!(y))\n"
            "    4\t| ASSIGN: 'a = 1'\n"
            "    5\t| NOTE: 'note'\n"
            "    6\t| WARN: 'warn'\n"
            "    0\t|__ERROR__\n")
    parsed = error_trace_pretty_parse(text)
    by_op = {}
    for elem in parsed:
        by_op.setdefault(elem[CET_OP], []).append(elem)
    assert len(by_op[CET_OP_ASSUME]) == 2
    assert by_op[CET_OP_ASSUME][0][CET_SOURCE] == "x > 0"
    assert by_op[CET_OP_ASSUME][0][CET_DISPLAY_NAME] is True
    assert by_op[CET_OP_ASSUME][1][CET_DISPLAY_NAME] is False
    assert by_op[CET_OP_ASSIGN][0][CET_DISPLAY_NAME] == "a = 1"
    assert by_op[CET_OP_NOTE][0][CET_DISPLAY_NAME] == "note"
    assert by_op[CET_OP_WARN][0][CET_DISPLAY_NAME] == "warn"


def test_pretty_parse_raises_on_garbage():
    with pytest.raises(ValueError):
        error_trace_pretty_parse("this is not an error trace at all !!!")


# --------------------------------------------------------------------------- #
# process_args                                                               #
# --------------------------------------------------------------------------- #

def test_process_args_splits_and_sorts_string_lists():
    args = {TAG_ADDITIONAL_MODEL_FUNCTIONS: "worker,main,foo"}
    process_args(args)
    assert args[TAG_ADDITIONAL_MODEL_FUNCTIONS] == ["foo", "main", "worker"]


def test_process_args_sorts_list_in_place():
    args = {TAG_FILTERED_MODEL_FUNCTIONS: ["z", "a", "m"]}
    process_args(args)
    assert args[TAG_FILTERED_MODEL_FUNCTIONS] == ["a", "m", "z"]


def test_process_args_as_str_joins_lists():
    args = {TAG_ADDITIONAL_MODEL_FUNCTIONS: "b,a"}
    process_args(args, as_str=True)
    assert args[TAG_ADDITIONAL_MODEL_FUNCTIONS] == "a,b"


def test_process_args_removes_empty_values():
    args = {TAG_USE_NOTES: "", TAG_USE_WARNS: False, TAG_IGNORE_NOTES_TEXT: None}
    # Use a value-less dict comprehension-safe construction.
    process_args(args)
    assert TAG_USE_NOTES not in args
    assert TAG_USE_WARNS not in args
    assert TAG_IGNORE_NOTES_TEXT not in args


def test_process_args_keeps_boolean_flags():
    args = {TAG_USE_NOTES: True}
    process_args(args)
    assert args[TAG_USE_NOTES] is True


def test_process_args_is_idempotent():
    args = {TAG_ADDITIONAL_MODEL_FUNCTIONS: "b, a ,c"}
    process_args(args)
    first = copy.deepcopy(args)
    process_args(args)
    assert args == first


# --------------------------------------------------------------------------- #
# compare_edited_traces / compare_converted_traces                            #
# --------------------------------------------------------------------------- #

def test_compare_edited_traces_equal():
    trace = calls(0, "a", "b") + returns(0, "b", "a")
    is_equal, similarity = compare_edited_traces(trace, trace, COMPARISON_FUNCTION_EQUAL, 100)
    assert is_equal is True
    assert similarity == 1.0


def test_compare_edited_traces_accepts_json_strings():
    trace = calls(0, "a", "b")
    is_equal, similarity = compare_edited_traces(
        json.dumps(trace), json.dumps(trace), COMPARISON_FUNCTION_EQUAL, 100)
    assert is_equal is True
    assert similarity == 1.0


def test_compare_edited_traces_multi_thread_round_trip():
    trace = calls(0, "a") + calls(1, "b") + returns(1, "b") + returns(0, "a")
    is_equal, similarity = compare_edited_traces(trace, trace, COMPARISON_FUNCTION_EQUAL, 100)
    assert is_equal is True
    assert similarity == 1.0


def test_compare_edited_traces_threshold():
    edited = calls(0, "a", "b")
    compared = calls(0, "b")
    # included but not equal -> include passes, equal fails
    is_equal, _ = compare_edited_traces(edited, compared, COMPARISON_FUNCTION_INCLUDE, 100)
    assert is_equal is False


def test_compare_converted_traces_equal_and_threshold():
    trace = calls(0, "a", "b")
    assert compare_converted_traces(trace, trace, COMPARISON_FUNCTION_EQUAL, 100) is True
    assert compare_converted_traces(trace, json.dumps(trace), COMPARISON_FUNCTION_EQUAL, 100) is True


def test_compare_converted_traces_different():
    assert compare_converted_traces(calls(0, "a"), calls(0, "b"), COMPARISON_FUNCTION_EQUAL, 100) is False
