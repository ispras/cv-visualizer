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

"""Shared helpers and library-independent oracles for MEA error-trace tests."""

import random
import re

from reports.mea.core import (
    ASSIGN_MARK,
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
    DEFAULT_PROPERTY_CHECKS_TEXT,
)

NAME_POOL = ["main", "foo", "bar", "helper", "handler", "worker", "drv", "check"]


# --------------------------------------------------------------------------- #
# Trace builders                                                              #
# --------------------------------------------------------------------------- #

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


def strip_suffix(name):
    return re.sub(r"_(\d+)$", "", name)


def ops(result):
    return [e[CET_OP] for e in result]


def names(result):
    return [e[CET_DISPLAY_NAME] for e in result]


def threads(result):
    return [e[CET_THREAD] for e in result]


def as_tuples(result, with_id=True):
    if with_id:
        return [(e[CET_OP], e[CET_DISPLAY_NAME], e[CET_THREAD], e[CET_ID]) for e in result]
    return [(e[CET_OP], e[CET_DISPLAY_NAME], e[CET_THREAD]) for e in result]


# --------------------------------------------------------------------------- #
# Random error trace generator (deterministic by seed)                        #
# --------------------------------------------------------------------------- #

def random_error_trace(seed, n_threads=2, max_depth=4, max_events=24):
    """
    Build a syntactically valid error trace with several (possibly interleaved) threads.

    Every thread starts and finishes with balanced function calls (enter/return pairs),
    and may additionally contain condition/assignment/note/warn edges.  Generated names
    sometimes carry ``_<number>`` suffixes to exercise generated-name handling.
    """
    rng = random.Random(seed)
    funcs = {}
    next_func = [1]

    def new_func():
        func_id = next_func[0]
        next_func[0] += 1
        func_name = rng.choice(NAME_POOL)
        if rng.random() < 0.25:
            func_name = "{}_{}".format(func_name, rng.randint(0, 9))
        funcs[func_id] = func_name
        return func_id

    per_thread = {}
    for thread in range(n_threads):
        events = []
        stack = []
        count = rng.randint(1, max_events)
        for _ in range(count):
            if stack and (len(stack) >= max_depth or rng.random() < 0.4):
                events.append({"kind": "return", "func": stack.pop(), "thread": thread})
            elif stack and rng.random() < 0.3:
                events.append({"kind": rng.choice(["condition", "assign", "note", "warn"]),
                               "thread": thread})
            else:
                func_id = new_func()
                stack.append(func_id)
                events.append({"kind": "enter", "func": func_id, "thread": thread})
        while stack:
            events.append({"kind": "return", "func": stack.pop(), "thread": thread})
        per_thread[thread] = events

    indexes = {thread: 0 for thread in range(n_threads)}
    remaining = sum(len(evs) for evs in per_thread.values())
    order = []
    while remaining:
        candidates = [t for t in range(n_threads) if indexes[t] < len(per_thread[t])]
        thread = rng.choice(candidates)
        order.append(per_thread[thread][indexes[thread]])
        indexes[thread] += 1
        remaining -= 1

    edges = []
    for number, event in enumerate(order):
        line = number + 1
        item = edge(thread=event["thread"], source="file{}.c".format(event["thread"]), line=line)
        if event["kind"] == "enter":
            item["enter"] = event["func"]
        elif event["kind"] == "return":
            item["return"] = event["func"]
        elif event["kind"] == "condition":
            item["condition"] = "cond_{}".format(line)
        elif event["kind"] == "assign":
            item["source"] = "var_{} = {}".format(line, line)
        elif event["kind"] == "note":
            item["note"] = "note_{}".format(line)
        elif event["kind"] == "warn":
            item["warn"] = "warn_{}".format(line)
        edges.append(item)
    return make_trace(funcs, edges)


# --------------------------------------------------------------------------- #
# Oracles                                                                     #
# --------------------------------------------------------------------------- #

def expected_call_tree(funcs, edges):
    """Elements produced by the call-tree conversion (no doubled enter/return edges)."""
    result = []
    counter = 0
    for item in edges:
        if "entry_point" in item or "ignore MEA" in item:
            continue
        if "enter" in item:
            name = strip_suffix(funcs[item["enter"]])
            if not name:
                continue
            result.append((CET_OP_CALL, name, item["thread"], counter))
        elif "return" in item:
            name = strip_suffix(funcs[item["return"]])
            if not name:
                continue
            result.append((CET_OP_RETURN, name, item["thread"], counter))
        counter += 1
    return result


def expected_conditions(edges):
    return [(CET_OP_ASSUME, item["condition"], item["thread"], index)
            for index, item in enumerate(edges) if "condition" in item]


def expected_assignments(edges):
    return [(CET_OP_ASSIGN, item["source"], item["thread"], index)
            for index, item in enumerate(edges)
            if "source" in item and ASSIGN_MARK in item["source"]]


def expected_notes(edges, use_notes=False, use_warns=False, ignore_text=False):
    if not use_notes and not use_warns:
        use_notes = use_warns = True
    result = []
    for index, item in enumerate(edges):
        text = DEFAULT_PROPERTY_CHECKS_TEXT
        if "note" in item:
            if not ignore_text:
                note = item["note"]
                text = note.get("value", note) if isinstance(note, dict) else note
            if use_notes:
                result.append((CET_OP_NOTE, text, item["thread"], index))
        elif "warn" in item:
            if not ignore_text:
                text = item["warn"]
            if use_warns:
                result.append((CET_OP_WARN, text, item["thread"], index))
    return result
