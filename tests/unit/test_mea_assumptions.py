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
Regression tests for comparing error traces by assumptions (conditions).

``CONVERSION_FUNCTION_CONDITIONS`` extracts ASSUME elements and the comparison
filter compares the condition expressions per thread.  The pretty-printed form of
an assumption uses a leading '!' to mark a condition that is not covered
(``ASSUME(!(x > 0))``).  That '!' is an artifact of printing and must be ignored
by the comparison, otherwise the same trace compares differently after the
``error_trace_pretty_print``/``error_trace_pretty_parse`` round-trip performed by
``compare_edited_traces``.
"""

import pytest

from reports.mea.core import (
    convert_error_trace,
    compare_error_traces,
    CET_OP,
    CET_OP_ASSUME,
    CET_DISPLAY_NAME,
    CET_SOURCE,
    CONVERSION_FUNCTION_CONDITIONS,
    COMPARISON_FUNCTION_EQUAL,
)
from reports.mea.wrapper import (
    error_trace_pretty_print,
    error_trace_pretty_parse,
    compare_converted_traces,
    compare_edited_traces,
)


def condition_edge(thread=0, source="x > 0", condition=True, line=1):
    return {
        "thread": thread,
        "source": source,
        "start line": line,
        "condition": condition,
    }


def trace_with_conditions(*edges):
    return {"funcs": {}, "edges": list(edges)}


def convert(*edges):
    return convert_error_trace(trace_with_conditions(*edges), CONVERSION_FUNCTION_CONDITIONS, {})


def expressions(converted):
    return [(elem[CET_OP], elem[CET_SOURCE]) for elem in converted]


# --------------------------------------------------------------------------- #
# The round-trip performed by compare_edited_traces must not change the trace  #
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "condition,source",
    [
        (True, "x > 0"),
        (False, "x > 0"),
        (True, "!(x > 0)"),
        (False, "!(x > 0)"),
    ],
)
def test_round_trip_keeps_assumption_comparable(condition, source):
    converted = convert(condition_edge(source=source, condition=condition))
    round_tripped = error_trace_pretty_parse(error_trace_pretty_print(converted))
    assert compare_converted_traces(converted, round_tripped,
                                    COMPARISON_FUNCTION_EQUAL, 100) is True


def test_same_false_condition_is_equal():
    # Regression: a not-covered condition used to be printed as "ASSUME(!(x > 0))"
    # and parsed back as the expression "(x > 0)" (or "(!(x > 0))"), so an
    # identical trace compared as different.
    converted = convert(condition_edge(source="x > 0", condition=False))
    is_equal, similarity = compare_edited_traces(converted, converted,
                                                 COMPARISON_FUNCTION_EQUAL, 100)
    assert is_equal is True
    assert similarity == 1.0


def test_same_negated_condition_is_equal():
    for condition in (True, False):
        converted = convert(condition_edge(source="!(x > 0)", condition=condition))
        is_equal, similarity = compare_edited_traces(converted, converted,
                                                     COMPARISON_FUNCTION_EQUAL, 100)
        assert is_equal is True
        assert similarity == 1.0


# --------------------------------------------------------------------------- #
# The synthetic '!' (not-covered marker) is ignored                           #
# --------------------------------------------------------------------------- #

def test_excessive_bang_on_false_condition_is_ignored():
    # Same expression, one condition covered and one not: the extra '!' that the
    # pretty printer adds for the not-covered condition must not affect matching.
    covered = convert(condition_edge(source="x > 0", condition=True))
    not_covered = convert(condition_edge(source="x > 0", condition=False))
    assert compare_converted_traces(covered, not_covered,
                                    COMPARISON_FUNCTION_EQUAL, 100) is True


def test_leading_bang_in_source_is_ignored():
    negated = convert(condition_edge(source="!(x > 0)", condition=False))
    plain = convert(condition_edge(source="x > 0", condition=True))
    assert compare_converted_traces(negated, plain,
                                    COMPARISON_FUNCTION_EQUAL, 100) is True


def test_missing_bang_after_round_trip_is_ignored():
    # A covered condition whose source already starts with '!' is printed without an
    # additional marker and used to lose its '!' during parsing.
    converted = convert(condition_edge(source="!(x > 0)", condition=True))
    round_tripped = error_trace_pretty_parse(error_trace_pretty_print(converted))
    assert compare_converted_traces(converted, round_tripped,
                                    COMPARISON_FUNCTION_EQUAL, 100) is True


# --------------------------------------------------------------------------- #
# Different assumptions are still different                                   #
# --------------------------------------------------------------------------- #

def test_different_assumptions_are_not_equal():
    first = convert(condition_edge(source="x > 0", condition=True))
    second = convert(condition_edge(source="y <= 0", condition=True))
    assert not compare_converted_traces(first, second,
                                        COMPARISON_FUNCTION_EQUAL, 100)


def test_extra_assumption_is_not_equal():
    one = convert(condition_edge(source="x > 0", condition=True))
    two = convert(condition_edge(source="x > 0", condition=True),
                  condition_edge(source="y > 0", condition=True, line=2))
    assert not compare_converted_traces(one, two, COMPARISON_FUNCTION_EQUAL, 100)


# --------------------------------------------------------------------------- #
# Multiple conditions and multiple threads                                    #
# --------------------------------------------------------------------------- #

def test_multiple_conditions_are_compared_as_a_list():
    first = convert(
        condition_edge(source="x > 0", condition=True, line=1),
        condition_edge(source="y > 0", condition=False, line=2),
        condition_edge(source="z == 1", condition=True, line=3),
    )
    same = convert(
        condition_edge(source="x > 0", condition=False, line=1),
        condition_edge(source="y > 0", condition=True, line=2),
        condition_edge(source="z == 1", condition=False, line=3),
    )
    assert compare_converted_traces(first, same, COMPARISON_FUNCTION_EQUAL, 100) is True
    is_equal, similarity = compare_edited_traces(first, same,
                                                 COMPARISON_FUNCTION_EQUAL, 100)
    assert is_equal is True
    assert similarity == 1.0


def test_conditions_of_different_threads_are_separate():
    # Thread 0 has one condition, thread 1 has another; each thread's assumption list
    # is compared independently.
    trace = convert(
        condition_edge(thread=0, source="x > 0", condition=True, line=1),
        condition_edge(thread=1, source="y > 0", condition=False, line=2),
    )
    assert expressions(trace) == [
        (CET_OP_ASSUME, "x > 0"),
        (CET_OP_ASSUME, "y > 0"),
    ]
    is_equal, similarity = compare_edited_traces(trace, trace,
                                                 COMPARISON_FUNCTION_EQUAL, 100)
    assert is_equal is True
    assert similarity == 1.0


def test_conditions_are_grouped_per_thread():
    # Two conditions on two threads are two separate assumption lists, while both
    # conditions on a single thread are one combined list -- these must not match.
    split = convert(
        condition_edge(thread=0, source="x > 0", condition=True, line=1),
        condition_edge(thread=1, source="y > 0", condition=True, line=2),
    )
    combined = convert(
        condition_edge(thread=0, source="x > 0", condition=True, line=1),
        condition_edge(thread=0, source="y > 0", condition=True, line=2),
    )
    assert not compare_converted_traces(split, combined,
                                        COMPARISON_FUNCTION_EQUAL, 100)


def test_similarity_of_partially_matching_threads():
    both = convert(
        condition_edge(thread=0, source="x > 0", condition=True, line=1),
        condition_edge(thread=1, source="y > 0", condition=True, line=2),
    )
    only_first = convert(condition_edge(thread=0, source="x > 0", condition=True))
    # Two independent "threads" on the left, one matching on the right: 1 / 2.
    assert compare_error_traces(both, only_first, COMPARISON_FUNCTION_EQUAL) == 0.5
