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
Thorough unit tests for reports.mea.core.

They cover every conversion and comparison function, all of their parameters,
multiple/interleaved threads and a set of small low-level regression tests that
pin down bugs which are hard to reproduce on real (large) error traces.
"""

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
    CONVERSION_FUNCTION_MODEL_FUNCTIONS,
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
    TAG_ADDITIONAL_MODEL_FUNCTIONS,
    TAG_FILTERED_MODEL_FUNCTIONS,
    TAG_NOTES_LEVEL,
    TAG_USE_NOTES,
    TAG_USE_WARNS,
    TAG_IGNORE_NOTES_TEXT,
    DEFAULT_PROPERTY_CHECKS_TEXT,
)
from mea_utils import (
    edge,
    make_trace,
    cet,
    strip_suffix,
    as_tuples,
    random_error_trace,
    expected_call_tree,
    expected_conditions,
    expected_assignments,
    expected_notes,
)

SEEDS = list(range(30))
FLAG_CASES = [
    {},
    {TAG_USE_NOTES: True},
    {TAG_USE_WARNS: True},
    {TAG_USE_NOTES: True, TAG_USE_WARNS: True},
    {TAG_IGNORE_NOTES_TEXT: True},
]
ALL_COMPARISON_FUNCTIONS = [
    COMPARISON_FUNCTION_EQUAL,
    COMPARISON_FUNCTION_INCLUDE,
    COMPARISON_FUNCTION_INCLUDE_WITH_ERROR,
    COMPARISON_FUNCTION_INCLUDE_PARTIAL,
    COMPARISON_FUNCTION_INCLUDE_PARTIAL_ORDERED,
    COMPARISON_FUNCTION_SKIP,
]


def thread_set(result):
    return {item[CET_THREAD] for item in result}


# --------------------------------------------------------------------------- #
# Random (but deterministic) conversion tests                                 #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("seed", SEEDS)
def test_call_tree_matches_oracle(seed):
    trace = random_error_trace(seed)
    result = convert_error_trace(trace, CONVERSION_FUNCTION_CALL_TREE, {})
    assert as_tuples(result) == expected_call_tree(trace["funcs"], trace["edges"])


@pytest.mark.parametrize("seed", SEEDS)
def test_conditions_match_oracle(seed):
    trace = random_error_trace(seed)
    result = convert_error_trace(trace, CONVERSION_FUNCTION_CONDITIONS, {})
    assert as_tuples(result) == expected_conditions(trace["edges"])


@pytest.mark.parametrize("seed", SEEDS)
def test_assignments_match_oracle(seed):
    trace = random_error_trace(seed)
    result = convert_error_trace(trace, CONVERSION_FUNCTION_ASSIGNMENTS, {})
    assert as_tuples(result) == expected_assignments(trace["edges"])


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("args", FLAG_CASES)
def test_notes_match_oracle(seed, args):
    trace = random_error_trace(seed)
    result = convert_error_trace(trace, CONVERSION_FUNCTION_NOTES, dict(args))
    expected = expected_notes(
        trace["edges"],
        use_notes=args.get(TAG_USE_NOTES, False),
        use_warns=args.get(TAG_USE_WARNS, False),
        ignore_text=args.get(TAG_IGNORE_NOTES_TEXT, False),
    )
    assert as_tuples(result) == expected


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("args", FLAG_CASES)
def test_full_is_sorted_union(seed, args):
    trace = random_error_trace(seed)
    result = convert_error_trace(trace, CONVERSION_FUNCTION_FULL, dict(args))
    expected = (expected_call_tree(trace["funcs"], trace["edges"]) +
                expected_conditions(trace["edges"]) +
                expected_assignments(trace["edges"]) +
                expected_notes(
                    trace["edges"],
                    use_notes=args.get(TAG_USE_NOTES, False),
                    use_warns=args.get(TAG_USE_WARNS, False),
                    ignore_text=args.get(TAG_IGNORE_NOTES_TEXT, False)))
    assert as_tuples(result) == sorted(expected, key=lambda t: t[3])


@pytest.mark.parametrize("seed", SEEDS)
def test_call_tree_thread_count_is_preserved(seed):
    trace = random_error_trace(seed, n_threads=(seed % 4) + 1)
    result = convert_error_trace(trace, CONVERSION_FUNCTION_CALL_TREE, {})
    expected_threads = {item["thread"] for item in trace["edges"]}
    assert thread_set(result) == expected_threads


@pytest.mark.parametrize("seed", SEEDS)
def test_every_element_has_all_fields(seed):
    trace = random_error_trace(seed)
    for function in (CONVERSION_FUNCTION_CALL_TREE, CONVERSION_FUNCTION_CONDITIONS,
                     CONVERSION_FUNCTION_ASSIGNMENTS, CONVERSION_FUNCTION_NOTES,
                     CONVERSION_FUNCTION_FULL):
        for item in convert_error_trace(trace, function, {}):
            assert set(item) == {CET_OP, CET_THREAD, CET_SOURCE, CET_DISPLAY_NAME, CET_LINE, CET_ID}
            assert isinstance(item[CET_ID], int)


@pytest.mark.parametrize("seed", SEEDS)
def test_use_notes_appends_and_sorts(seed):
    trace = random_error_trace(seed)
    base = convert_error_trace(trace, CONVERSION_FUNCTION_CALL_TREE, {})
    with_notes = convert_error_trace(trace, CONVERSION_FUNCTION_CALL_TREE, {TAG_USE_NOTES: True})
    assert with_notes == sorted(with_notes, key=lambda e: e[CET_ID])
    assert len(with_notes) >= len(base)
    note_ids = {e[CET_ID] for e in with_notes if e[CET_OP] == CET_OP_NOTE}
    assert note_ids <= {e[CET_ID] for e in with_notes}


# --------------------------------------------------------------------------- #
# Hand-picked conversion edge cases                                           #
# --------------------------------------------------------------------------- #

def test_entry_point_and_ignore_mea_are_skipped_but_keep_id():
    trace = make_trace(
        {1: "main", 2: "foo"},
        [edge(enter=1, line=1, entry_point=True),
         edge(enter=2, line=2, ignore_mea=True),
         edge(enter=1, line=3)],
    )
    result = convert_error_trace(trace, CONVERSION_FUNCTION_CALL_TREE, {})
    assert as_tuples(result) == [(CET_OP_CALL, "main", 0, 0)]


def test_empty_function_name_is_skipped():
    trace = make_trace({1: "", 2: "ok"}, [edge(enter=1, line=1), edge(enter=2, line=2)])
    assert as_tuples(convert_error_trace(trace, CONVERSION_FUNCTION_CALL_TREE, {})) == \
        [(CET_OP_CALL, "ok", 0, 0)]


def test_generated_suffix_is_stripped_on_enter_and_return():
    trace = make_trace({1: "main_1", 2: "foo_42"},
                       [edge(enter=1), edge(enter=2), edge(ret=2), edge(ret=1)])
    result = convert_error_trace(trace, CONVERSION_FUNCTION_CALL_TREE, {})
    assert [e[CET_DISPLAY_NAME] for e in result] == ["main", "foo", "foo", "main"]


def test_doubled_enter_return_edge_emits_extra_returns_with_stripped_names():
    # Regression: extra returns produced from the ``double_funcs`` map were not normalized.
    trace = make_trace(
        {1: "main_5", 2: "inline_7"},
        [edge(enter_ret=(2, 2), line=1), edge(ret=2, line=2)],
    )
    result = convert_error_trace(trace, CONVERSION_FUNCTION_CALL_TREE, {})
    assert as_tuples(result) == [
        (CET_OP_CALL, "inline", 0, 0),
        (CET_OP_RETURN, "inline", 0, 1),
        (CET_OP_RETURN, "inline", 0, 1),
    ]


def test_doubled_edges_are_resolved_as_a_chain():
    trace = make_trace(
        {1: "a", 2: "b", 3: "c"},
        [edge(enter_ret=(1, 2), line=1), edge(enter_ret=(2, 3), line=2), edge(ret=2, line=3)],
    )
    result = convert_error_trace(trace, CONVERSION_FUNCTION_CALL_TREE, {})
    # The closing return to ``b`` first reports ``b`` and then follows the ``b -> c``
    # doubled edge chain (all extra returns share the same edge id).
    assert as_tuples(result) == [
        (CET_OP_CALL, "a", 0, 0),
        (CET_OP_CALL, "b", 0, 1),
        (CET_OP_RETURN, "b", 0, 2),
        (CET_OP_RETURN, "c", 0, 2),
    ]


def test_default_args_does_not_crash():
    # Regression: ``args: dict = dict`` default raised TypeError.
    trace = make_trace({1: "main"}, [edge(enter=1)])
    assert [e[CET_DISPLAY_NAME] for e in convert_error_trace(trace, CONVERSION_FUNCTION_CALL_TREE)] == ["main"]


def test_unknown_conversion_function_falls_back_to_model_functions():
    trace = random_error_trace(7)
    assert convert_error_trace(trace, "nonsense", {}) == \
        convert_error_trace(trace, CONVERSION_FUNCTION_MODEL_FUNCTIONS, {})


# --------------------------------------------------------------------------- #
# Model functions                                                             #
# --------------------------------------------------------------------------- #

def test_model_functions_keeps_function_containing_a_note():
    trace = make_trace(
        {1: "main", 2: "foo", 3: "leaf"},
        [edge(enter=1), edge(enter=2, note="n"), edge(enter=3),
         edge(ret=3), edge(ret=2), edge(ret=1)],
    )
    result = convert_error_trace(trace, CONVERSION_FUNCTION_MODEL_FUNCTIONS, {})
    assert [(e[CET_OP], e[CET_DISPLAY_NAME]) for e in result] == [
        (CET_OP_CALL, "main"), (CET_OP_CALL, "foo"), (CET_OP_RETURN, "foo"), (CET_OP_RETURN, "main"),
    ]


def test_model_functions_keeps_function_with_warn():
    trace = make_trace({1: "main", 2: "bar"},
                       [edge(enter=1), edge(enter=2, warn="w"), edge(ret=2), edge(ret=1)])
    result = convert_error_trace(trace, CONVERSION_FUNCTION_MODEL_FUNCTIONS, {})
    assert [e[CET_DISPLAY_NAME] for e in result] == ["main", "bar", "bar", "main"]


def test_additional_model_functions_keep_subtree():
    trace = make_trace(
        {1: "main", 2: "foo", 3: "leaf"},
        [edge(enter=1), edge(enter=2, note="n"), edge(enter=3),
         edge(ret=3), edge(ret=2), edge(ret=1)],
    )
    result = convert_error_trace(
        trace, CONVERSION_FUNCTION_MODEL_FUNCTIONS, {TAG_ADDITIONAL_MODEL_FUNCTIONS: ["leaf"]})
    assert [e[CET_DISPLAY_NAME] for e in result] == ["main", "foo", "leaf", "leaf", "foo", "main"]


def test_notes_level_filters_out_deep_notes():
    trace = make_trace(
        {1: "main", 2: "baz"},
        [edge(enter=1), edge(enter=2, note={"value": "v", "level": 3}), edge(ret=2), edge(ret=1)],
    )
    shallow = convert_error_trace(trace, CONVERSION_FUNCTION_MODEL_FUNCTIONS, {})
    deep = convert_error_trace(trace, CONVERSION_FUNCTION_MODEL_FUNCTIONS, {TAG_NOTES_LEVEL: 5})
    assert [e[CET_DISPLAY_NAME] for e in shallow] == ["main"]
    assert [e[CET_DISPLAY_NAME] for e in deep] == ["main", "baz", "baz", "main"]


def test_generated_suffix_note_is_recognized_as_model_function():
    # Regression: model functions were detected with raw (un-normalized) names while the
    # call tree is built with normalized names, so "foo_1" was never matched as "foo".
    trace = make_trace(
        {1: "main", 2: "foo_1", 3: "leaf"},
        [edge(enter=1), edge(enter=2, note="n"), edge(enter=3),
         edge(ret=3), edge(ret=2), edge(ret=1)],
    )
    result = convert_error_trace(trace, CONVERSION_FUNCTION_MODEL_FUNCTIONS, {})
    assert [e[CET_DISPLAY_NAME] for e in result] == ["main", "foo", "foo", "main"]


def test_additional_model_functions_regex_pattern():
    trace = make_trace(
        {1: "main", 2: "foo_1", 3: "bar_2"},
        [edge(enter=1), edge(enter=2), edge(ret=2), edge(enter=3), edge(ret=3), edge(ret=1)],
    )
    result = convert_error_trace(
        trace, CONVERSION_FUNCTION_MODEL_FUNCTIONS, {TAG_ADDITIONAL_MODEL_FUNCTIONS: ["foo.*"]})
    assert [e[CET_DISPLAY_NAME] for e in result] == ["main", "foo", "foo", "main"]


def test_filtered_model_functions_removes_whole_subtree():
    trace = make_trace(
        {1: "main", 2: "skip", 3: "leaf"},
        [edge(enter=1), edge(enter=2), edge(enter=3),
         edge(ret=3), edge(ret=2), edge(ret=1)],
    )
    result = convert_error_trace(
        trace, CONVERSION_FUNCTION_CALL_TREE, {TAG_FILTERED_MODEL_FUNCTIONS: ["skip"]})
    assert [(e[CET_OP], e[CET_DISPLAY_NAME]) for e in result] == [
        (CET_OP_CALL, "main"), (CET_OP_RETURN, "main"),
    ]


def test_filtered_model_functions_are_tracked_per_thread():
    # Regression: thread id 0 is falsy, so the filtered stack used to leak across threads.
    trace = make_trace(
        {1: "outer", 2: "inner", 3: "keep"},
        [edge(enter=1, thread=0), edge(enter=2, thread=0),
         edge(enter=3, thread=1), edge(ret=3, thread=1),
         edge(ret=2, thread=0), edge(ret=1, thread=0)],
    )
    result = convert_error_trace(
        trace, CONVERSION_FUNCTION_CALL_TREE, {TAG_FILTERED_MODEL_FUNCTIONS: ["outer"]})
    assert [(e[CET_OP], e[CET_DISPLAY_NAME], e[CET_THREAD]) for e in result] == [
        (CET_OP_CALL, "keep", 1), (CET_OP_RETURN, "keep", 1),
    ]


@pytest.mark.parametrize("seed", SEEDS)
def test_model_functions_is_a_thread_preserving_subsequence(seed):
    trace = random_error_trace(seed, n_threads=(seed % 4) + 1)
    call_tree = convert_error_trace(trace, CONVERSION_FUNCTION_CALL_TREE, {})
    model_tree = convert_error_trace(trace, CONVERSION_FUNCTION_MODEL_FUNCTIONS, {})
    assert set(as_tuples(model_tree)) <= set(as_tuples(call_tree))
    assert thread_set(model_tree) == thread_set(call_tree)
    # The first element of every thread must be retained.
    first_per_thread = {}
    for item in call_tree:
        first_per_thread.setdefault(item[CET_THREAD], as_tuples([item])[0])
    for thread, first in first_per_thread.items():
        assert first in as_tuples(model_tree)


# --------------------------------------------------------------------------- #
# compare_error_traces                                                        #
# --------------------------------------------------------------------------- #

def calls(thread, *names):
    return [cet(CET_OP_CALL, thread, name, cid=i) for i, name in enumerate(names)]


def test_compare_equal_single_thread():
    assert compare_error_traces(calls(0, "a", "b"), calls(0, "a", "b"),
                                COMPARISON_FUNCTION_EQUAL) == 1.0


def test_compare_equal_multi_thread_order_independent():
    et1 = calls(0, "a") + calls(1, "b")
    et2 = calls(1, "b") + calls(0, "a")
    assert compare_error_traces(et1, et2, COMPARISON_FUNCTION_EQUAL) == 1.0


def test_compare_equal_thread_ids_do_not_matter():
    et1 = calls(0, "a") + calls(1, "b")
    et2 = calls(7, "a") + calls(9, "b")
    assert compare_error_traces(et1, et2, COMPARISON_FUNCTION_EQUAL) == 1.0


def test_compare_equal_different_thread_count_uses_jaccard():
    et1 = calls(0, "a") + calls(1, "b")
    et2 = calls(0, "a") + calls(1, "b") + calls(2, "c")
    # 2 common threads among 3 distinct -> 2 / 3
    assert compare_error_traces(et1, et2, COMPARISON_FUNCTION_EQUAL) == 0.67


def test_compare_equal_overlapping_threads():
    et1 = calls(0, "a", "c") + calls(1, "b")
    et2 = calls(0, "a", "c") + calls(1, "b")
    assert compare_error_traces(et1, et2, COMPARISON_FUNCTION_EQUAL) == 1.0
    # Interleaving elements of the same threads must not change the result.
    interleaved = calls(0, "a") + calls(1, "b") + calls(0, "c")
    assert compare_error_traces(interleaved, et1, COMPARISON_FUNCTION_EQUAL) == 1.0


def test_compare_equal_with_auxiliary_elements():
    et = [cet(CET_OP_CALL, 0, "main"), cet(CET_OP_NOTE, 0, "n"),
          cet(CET_OP_ASSUME, 0, "x")]
    assert compare_error_traces(et, et, COMPARISON_FUNCTION_EQUAL) == 1.0


def test_compare_include_contiguous_subtrace():
    et1 = calls(0, "a")
    et2 = calls(0, "a", "b")
    assert compare_error_traces(et1, et2, COMPARISON_FUNCTION_INCLUDE) == 1.0
    assert compare_error_traces(et2, et1, COMPARISON_FUNCTION_INCLUDE) == 0.0


def test_compare_include_rejects_out_of_order():
    et1 = calls(0, "b", "a")
    et2 = calls(0, "a", "b")
    assert compare_error_traces(et1, et2, COMPARISON_FUNCTION_INCLUDE) == 0.0
    assert compare_error_traces(et1, et2, COMPARISON_FUNCTION_INCLUDE_PARTIAL) == 1.0


def test_compare_include_partial_ignores_order():
    et1 = calls(0, "b", "a")
    et2 = calls(0, "a", "x", "b")
    assert compare_error_traces(et1, et2, COMPARISON_FUNCTION_INCLUDE_PARTIAL) == 1.0
    assert compare_error_traces(et1, et2, COMPARISON_FUNCTION_INCLUDE_PARTIAL_ORDERED) == 0.0


def test_compare_include_partial_ordered_accepts_in_order():
    et1 = calls(0, "a", "b")
    et2 = calls(0, "a", "x", "b")
    assert compare_error_traces(et1, et2, COMPARISON_FUNCTION_INCLUDE_PARTIAL_ORDERED) == 1.0


def test_compare_skip_ignores_content():
    et1 = calls(0, "a") + calls(1, "b")
    et2 = calls(0, "x") + calls(1, "y")
    assert compare_error_traces(et1, et2, COMPARISON_FUNCTION_SKIP) == 1.0


def test_compare_include_with_error_appends_warn():
    et1 = calls(0, "a")
    et2 = calls(0, "a")
    assert compare_error_traces(et1, et2, COMPARISON_FUNCTION_INCLUDE_WITH_ERROR) == 1.0


def test_compare_empty_traces():
    assert compare_error_traces([], [], COMPARISON_FUNCTION_EQUAL) == 1.0
    assert compare_error_traces([], calls(0, "a"), COMPARISON_FUNCTION_EQUAL) == 0.0
    assert compare_error_traces(calls(0, "a"), [], COMPARISON_FUNCTION_INCLUDE) == 0.0


def test_compare_unknown_function_defaults_to_equal():
    assert compare_error_traces(calls(0, "a"), calls(0, "a"), "nonsense") == 1.0


@pytest.mark.parametrize("seed", SEEDS)
def test_compare_is_reflexive_and_in_range(seed):
    trace = random_error_trace(seed, n_threads=(seed % 3) + 1)
    converted = convert_error_trace(trace, CONVERSION_FUNCTION_CALL_TREE, {})
    for function in ALL_COMPARISON_FUNCTIONS:
        similarity = compare_error_traces(converted, converted, function)
        assert 0.0 <= similarity <= 1.0
    assert compare_error_traces(converted, converted, COMPARISON_FUNCTION_EQUAL) == 1.0


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
        (0.67, 66, True),
        (0.67, 68, False),
    ],
)
def test_is_equivalent_values(similarity, threshold, expected):
    result = is_equivalent(similarity, threshold)
    assert result == expected
    assert isinstance(result, bool)


def test_is_equivalent_zero_is_false_not_float():
    # Regression: it used to return 0.0 (a float) instead of False.
    assert is_equivalent(0.0, 100) is False


def test_strip_suffix_helper_matches_conversion():
    trace = make_trace({1: "main_99"}, [edge(enter=1)])
    result = convert_error_trace(trace, CONVERSION_FUNCTION_CALL_TREE, {})
    assert result[0][CET_DISPLAY_NAME] == strip_suffix("main_99") == "main"
