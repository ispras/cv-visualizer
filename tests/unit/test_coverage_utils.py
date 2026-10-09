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

"""Unit tests for the pure helpers of reports.coverage."""

from reports.coverage import coverage_color, get_legend, json_to_html, TABLE_STAT_COLOR


# --------------------------------------------------------------------------- #
# coverage_color                                                              #
# --------------------------------------------------------------------------- #

def test_coverage_color_zero_is_red():
    assert coverage_color(0) == "#ebadad"


def test_coverage_color_nonzero_is_green():
    assert coverage_color(1) == "#adebad"
    assert coverage_color(100) == "#adebad"


# --------------------------------------------------------------------------- #
# get_legend                                                                  #
# --------------------------------------------------------------------------- #

def test_get_legend_empty_for_zero_max():
    assert get_legend(0, "lines") == []


def test_get_legend_rounds_down_to_hundreds():
    legend = get_legend(250, "lines")
    assert legend[0][0] == 200


def test_get_legend_keeps_max_below_hundred():
    legend = get_legend(73, "lines")
    assert legend[0][0] == 73


def test_get_legend_default_size():
    legend = get_legend(50, "lines")
    assert len(legend) == 5
    assert all(isinstance(cov, int) and color.startswith("#") for cov, color in legend)


def test_get_legend_with_zero_appends_zero_entry():
    legend = get_legend(50, "lines", with_zero=True)
    assert legend[-1][0] == 0
    assert legend[-1][1] == coverage_color(0)


def test_get_legend_never_has_zero_coverage_without_flag():
    legend = get_legend(50, "lines")
    assert all(cov != 0 for cov, _ in legend)


def test_get_legend_custom_number():
    legend = get_legend(100, "funcs", number=3)
    assert len(legend) == 3


# --------------------------------------------------------------------------- #
# json_to_html                                                                #
# --------------------------------------------------------------------------- #

def test_json_to_html_wraps_numbers_and_text():
    html = json_to_html({"answer": 42})
    assert "COVJsonNum" in html
    assert "COVJsonText" in html
    assert "42" in html


def test_json_to_html_escapes_markup():
    html = json_to_html({"a": "<b>&"})
    assert "&lt;b&gt;" in html
    assert "&amp;" in html
    assert "<b>" not in html


def test_json_to_html_handles_nested_structures():
    html = json_to_html({"items": [{"name": "x"}], "values": [1, 2]})
    assert "COVJsonLine" in html
    assert "items" in html


def test_json_to_html_scalar():
    assert "COVJsonLine" in json_to_html("plain")
    assert "COVJsonNum" in json_to_html(7)


def test_table_stat_color_constant():
    assert len(TABLE_STAT_COLOR) == 5
