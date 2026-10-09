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

"""Unit tests for the DB-free parts of reports.comparison (InternalLeaf)."""

from reports.comparison import InternalLeaf


def make_leaf(**kwargs):
    kwargs.setdefault("verdict", "unsafe")
    kwargs.setdefault("cpu_time", 10)
    kwargs.setdefault("parent_report_id", 1)
    return InternalLeaf(**kwargs)


def test_cpu_time_none_becomes_zero():
    assert make_leaf(cpu_time=None).cpu_time == 0
    assert make_leaf(cpu_time=0).cpu_time == 0


def test_cpu_time_is_kept():
    assert make_leaf(cpu_time=42).cpu_time == 42


def test_add_attrs_aggregates_values_and_ids():
    leaf = make_leaf()
    leaf.add_attrs("team", "a", 1)
    leaf.add_attrs("team", "b", 2)
    leaf.add_attrs("team", "a", 3)
    assert leaf.attrs_vals["team"] == {"a", "b"}
    assert leaf.attrs_ids == {1, 2, 3}


def test_add_unused_attrs():
    leaf = make_leaf()
    leaf.add_unused_attrs("extra", "x")
    leaf.add_unused_attrs("extra", "y")
    assert leaf.unused_attrs_vals["extra"] == {"x", "y"}


def test_serialize_attrs_all_and_core():
    leaf = make_leaf()
    leaf.add_attrs("a", "1", 1)
    leaf.add_attrs("b", "2", 2)
    all_attrs, core_attrs = leaf.serialize_attrs(core_attrs={"a"})
    assert all_attrs == "1/2"
    assert core_attrs == "1"


def test_serialize_attrs_values_are_sorted():
    leaf = make_leaf()
    leaf.add_attrs("a", "z", 1)
    leaf.add_attrs("a", "a", 2)
    all_attrs, _ = leaf.serialize_attrs()
    assert all_attrs == "a/z"


def test_serialize_attrs_empty():
    assert make_leaf().serialize_attrs() == ("", "")


def test_is_attr_true_when_subset_matches():
    leaf = make_leaf()
    leaf.add_attrs("team", "a", 1)
    assert leaf.is_attr({"team": {"a", "b"}}) is True


def test_is_attr_false_when_values_missing():
    leaf = make_leaf()
    leaf.add_attrs("team", "a", 1)
    assert leaf.is_attr({"team": {"b"}}) is False


def test_is_attr_false_when_names_do_not_intersect():
    leaf = make_leaf()
    leaf.add_attrs("team", "a", 1)
    assert leaf.is_attr({"other": {"a"}}) is False


def test_str_representation():
    leaf = make_leaf(verdict="safe", cpu_time=5)
    leaf.add_attrs("a", "1", 1)
    assert str(leaf) == "[safe, 5, 1]"
