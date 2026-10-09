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

"""Unit tests for reports.mea.core (error-trace conversion and comparison)."""

import pytest

from reports.mea.core import (
    convert_error_trace,
    compare_error_traces,
    is_equivalent,
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
    CONVERSION_FUNCTION_CONDITIONS,
    CONVERSION_FUNCTION_ASSIGNMENTS,
    CONVERSION_FUNCTION_NOTES,
    CONVERSION_FUNCTION_FULL,
    COMPARISON_FUNCTION_EQUAL,
    COMPARISON_FUNCTION_INCLUDE,
    COMPARISON_FUNCTION_INCLUDE_WITH_ERROR,
    COMPARISON_FUNCTION_INCLUDE_PARTIAL,
    COMPARISON_FUNCTION_INCLUDE_PARTIAL_ORDERED,
    COMPARISON_FUNCTION_SKIP,
    TAG_USE_NOTES,
    TAG_USE_WARNS,
    TAG_IGNORE_NOTES_TEXT,
    TAG_FILTERED_MODEL_FUNCTIONS,
    DEFAULT_PROPERTY_CHECKS_TEXT,
)


def convert(trace, function, args=None):
    # ``convert_error_trace`` has a faulty ``args=dict`` default, so always pass a dict.
    return convert_error_trace(trace, function, {} if args is None else args)


def edge(thread=0, source="m.c", line=1, enter=None, ret=None, enter_ret=None,
         condition=None, note=None, warn=None, entry_point=False, ignore_mea=False):
    result = {"thread": thread, "source": source, "start line": line}
    if enter is not None:
        result["enter"] = enter
    if ret is not None:
        result["return"] = ret
    if enter_ret is not None:
        result["enter"], result["return"] = enter_ret
    if condition is not None:
        result["condition"] = condition
    if note is not None:
        result["note"] = note
    if warn is not None:
        result["warn"] = warn
    if entry_point:
        result["entry_point"] = True
    if ignore_mea:
        result["ignore MEA"] = True
    return result


def make_trace(funcs=None, edges=None):
    return {"funcs": funcs or {}, "edges": edges or []}


def cet(op, thread, name, source="src", line=1, cid=0):
    return {
        CET_OP: op,
        CET_THREAD: thread,
        CET_DISPLAY_NAME: name,
        CET_SOURCE: source,
        CET_LINE: line,
        CET_ID: cid,
    }


def ops(result):
    return [e[CET_OP] for e in result]


def names(result):
    return [e[CET_DISPLAY_NAME] for e in result]


# --------------------------------------------------------------------------- #
# convert_error_trace                                                         #
# --------------------------------------------------------------------------- #

def test_call_tree_conversion():
    trace = make_trace(
        {1: "main", 2: "foo"},
        [edge(enter=1, line=1), edge(enter=2, line=2), edge(ret=2, line=3), edge(ret=1, line=4)],
    )
    result = convert(trace, CONVERSION_FUNCTION_CALL_TREE)
    assert ops(result) == [CET_OP_CALL, CET_OP_CALL, CET_OP_RETURN, CET_OP_RETURN]
    assert names(result) == ["main", "foo", "foo", "main"]
    assert [e[CET_ID] for e in result] == [0, 1, 2, 3]


def test_call_tree_strips_generated_name_suffix():
    trace = make_trace({1: "main_12"}, [edge(enter=1)])
    result = convert(trace, CONVERSION_FUNCTION_CALL_TREE)
    assert names(result) == ["main"]


def test_call_tree_skips_entry_point_and_ignore_mea():
    trace = make_trace(
        {1: "main", 2: "ignored"},
        [edge(enter=1, entry_point=True), edge(enter=2, ignore_mea=True)],
    )
    assert convert(trace, CONVERSION_FUNCTION_CALL_TREE) == []


def test_call_tree_skips_empty_function_name():
    trace = make_trace({1: ""}, [edge(enter=1)])
    assert convert(trace, CONVERSION_FUNCTION_CALL_TREE) == []


def test_call_tree_unknown_function_defaults_to_model_functions():
    trace = make_trace({1: "main"}, [edge(enter=1)])
    explicit = convert(trace, CONVERSION_FUNCTION_CALL_TREE)
    default = convert(trace, "no such conversion function")
    assert default == explicit


def test_conditions_conversion():
    trace = make_trace({1: "main"}, [edge(enter=1, line=1), edge(condition="x > 0", line=2)])
    result = convert(trace, CONVERSION_FUNCTION_CONDITIONS)
    assert ops(result) == [CET_OP_ASSUME]
    assert names(result) == ["x > 0"]


def test_assignments_conversion():
    trace = make_trace(
        {},
        [edge(source="a = 1", line=1), edge(source="no assignment here", line=2)],
    )
    result = convert(trace, CONVERSION_FUNCTION_ASSIGNMENTS)
    assert ops(result) == [CET_OP_ASSIGN]
    assert names(result) == ["a = 1"]


def test_notes_use_notes_flag():
    trace = make_trace({}, [edge(note="hello")])
    result = convert(trace, CONVERSION_FUNCTION_NOTES, {TAG_USE_NOTES: True})
    assert ops(result) == [CET_OP_NOTE]
    assert names(result) == ["hello"]


def test_notes_warns_flag():
    trace = make_trace({}, [edge(warn="careful")])
    result = convert(trace, CONVERSION_FUNCTION_NOTES, {TAG_USE_WARNS: True})
    assert ops(result) == [CET_OP_WARN]
    assert names(result) == ["careful"]


def test_notes_dict_note_value_is_used():
    trace = make_trace({}, [edge(note={"value": "text", "level": 1})])
    result = convert(trace, CONVERSION_FUNCTION_NOTES, {TAG_USE_NOTES: True})
    assert names(result) == ["text"]


def test_notes_ignore_text_uses_default_placeholder():
    trace = make_trace({}, [edge(note="secret")])
    result = convert(trace, CONVERSION_FUNCTION_NOTES, {TAG_IGNORE_NOTES_TEXT: True})
    assert names(result) == [DEFAULT_PROPERTY_CHECKS_TEXT]


def test_notes_default_includes_notes_and_warns():
    trace = make_trace({}, [edge(note="n", line=1), edge(warn="w", line=2)])
    result = convert(trace, CONVERSION_FUNCTION_NOTES)
    assert set(ops(result)) == {CET_OP_NOTE, CET_OP_WARN}


def test_full_conversion_is_sorted_by_id():
    trace = make_trace(
        {1: "main"},
        [
            edge(enter=1, line=1),
            edge(condition="x > 0", line=2),
            edge(note="n", line=3),
            edge(source="a = 1", line=4),
            edge(ret=1, line=5),
        ],
    )
    result = convert(trace, CONVERSION_FUNCTION_FULL, {TAG_USE_NOTES: True})
    assert result == sorted(result, key=lambda e: e[CET_ID])


def test_use_notes_appends_notes_to_call_tree_conversion():
    trace = make_trace(
        {1: "main"},
        [edge(enter=1, line=1), edge(ret=1, line=2), edge(note="n", line=3)],
    )
    result = convert(trace, CONVERSION_FUNCTION_CALL_TREE, {TAG_USE_NOTES: True})
    assert CET_OP_NOTE in ops(result)
    assert result == sorted(result, key=lambda e: e[CET_ID])


def test_filtered_model_functions_removes_subtree():
    trace = make_trace(
        {1: "main", 2: "skipme", 3: "leaf"},
        [
            edge(enter=1, line=1),
            edge(enter=2, line=2),
            edge(enter=3, line=3),
            edge(ret=3, line=4),
            edge(ret=2, line=5),
            edge(ret=1, line=6),
        ],
    )
    result = convert(
        trace, CONVERSION_FUNCTION_CALL_TREE, {TAG_FILTERED_MODEL_FUNCTIONS: {"skipme"}}
    )
    assert names(result) == ["main", "main"]


# --------------------------------------------------------------------------- #
# compare_error_traces                                                        #
# --------------------------------------------------------------------------- #

def test_compare_equal_identical_single_thread():
    et1 = [cet(CET_OP_CALL, 0, "main"), cet(CET_OP_CALL, 0, "foo")]
    et2 = [cet(CET_OP_CALL, 0, "main"), cet(CET_OP_CALL, 0, "foo")]
    assert compare_error_traces(et1, et2, COMPARISON_FUNCTION_EQUAL) == 1.0


def test_compare_equal_different_threads():
    et1 = [cet(CET_OP_CALL, 0, "main")]
    et2 = [cet(CET_OP_CALL, 0, "foo")]
    assert compare_error_traces(et1, et2, COMPARISON_FUNCTION_EQUAL) == 0.0


def test_compare_include_subset_is_full_match():
    et1 = [cet(CET_OP_CALL, 0, "main")]
    et2 = [cet(CET_OP_CALL, 0, "main"), cet(CET_OP_CALL, 0, "foo")]
    assert compare_error_traces(et1, et2, COMPARISON_FUNCTION_INCLUDE) == 1.0


def test_compare_partial_include():
    et1 = [cet(CET_OP_CALL, 0, "main"), cet(CET_OP_CALL, 0, "foo")]
    et2 = [cet(CET_OP_CALL, 0, "main"), cet(CET_OP_CALL, 0, "bar"), cet(CET_OP_CALL, 0, "foo")]
    assert compare_error_traces(et1, et2, COMPARISON_FUNCTION_INCLUDE_PARTIAL) == 1.0
    assert compare_error_traces(et1, et2, COMPARISON_FUNCTION_INCLUDE_PARTIAL_ORDERED) == 1.0


def test_compare_partial_ordered_rejects_out_of_order():
    et1 = [cet(CET_OP_CALL, 0, "foo"), cet(CET_OP_CALL, 0, "main")]
    et2 = [cet(CET_OP_CALL, 0, "main"), cet(CET_OP_CALL, 0, "foo")]
    assert compare_error_traces(et1, et2, COMPARISON_FUNCTION_INCLUDE_PARTIAL) == 1.0
    assert compare_error_traces(et1, et2, COMPARISON_FUNCTION_INCLUDE_PARTIAL_ORDERED) == 0.0


def test_compare_skip_returns_similarity_from_thread_count():
    et1 = [cet(CET_OP_CALL, 0, "main")]
    et2 = [cet(CET_OP_CALL, 1, "foo")]
    assert compare_error_traces(et1, et2, COMPARISON_FUNCTION_SKIP) == 1.0


def test_compare_include_with_error_appends_warn():
    et1 = [cet(CET_OP_CALL, 0, "main")]
    et2 = [cet(CET_OP_CALL, 0, "main")]
    assert compare_error_traces(et1, et2, COMPARISON_FUNCTION_INCLUDE_WITH_ERROR) == 1.0


def test_compare_empty_traces_are_equivalent():
    assert compare_error_traces([], [], COMPARISON_FUNCTION_EQUAL) == 1.0


def test_compare_empty_vs_nonempty():
    assert compare_error_traces([], [cet(CET_OP_CALL, 0, "main")], COMPARISON_FUNCTION_EQUAL) == 0.0


def test_compare_unknown_function_defaults_to_equal():
    et1 = [cet(CET_OP_CALL, 0, "main")]
    et2 = [cet(CET_OP_CALL, 0, "main")]
    assert compare_error_traces(et1, et2, "no such comparison") == 1.0


def test_compare_multi_thread_jaccard():
    et1 = [cet(CET_OP_CALL, 0, "a"), cet(CET_OP_CALL, 1, "b")]
    et2 = [cet(CET_OP_CALL, 0, "a"), cet(CET_OP_CALL, 2, "c")]
    assert compare_error_traces(et1, et2, COMPARISON_FUNCTION_EQUAL) == 0.33


# --------------------------------------------------------------------------- #
# is_equivalent                                                               #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "similarity,threshold,expected",
    [
        (1.0, 100, True),
        (0.99, 100, False),
        (0.5, 50, True),
        (0.49, 50, False),
        (0.0, 0, False),
        (0.0, 100, False),
    ],
)
def test_is_equivalent(similarity, threshold, expected):
    assert is_equivalent(similarity, threshold) == expected
