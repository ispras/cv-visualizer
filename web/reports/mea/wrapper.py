#
# CVV is a continuous verification visualizer.
# Copyright (c) 2019-2023 ISP RAS (http://www.ispras.ru)
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

# This library implements wrapper functions for MEA in CV (such as error traces parsing, printing, caching, etc.).


import json
from io import BytesIO

import reports
from marks.models import ErrorTraceConvertionCache, ConvertedTraces, MarkUnsafe, MarkUnsafeReport
from reports.mea.core import *
from reports.models import ReportUnsafe
from web.utils import ArchiveFileContent, BridgeException, file_get_or_create
from web.vars import ERROR_TRACE_FILE

CONVERSION_FUNCTIONS = [
    {'name': CONVERSION_FUNCTION_MODEL_FUNCTIONS, 'id': 0},
    {'name': CONVERSION_FUNCTION_CALL_TREE, 'id': 1},
    {'name': CONVERSION_FUNCTION_CONDITIONS, 'id': 2},
    {'name': CONVERSION_FUNCTION_ASSIGNMENTS, 'id': 3},
    {'name': CONVERSION_FUNCTION_NOTES, 'id': 4},
    {'name': CONVERSION_FUNCTION_FULL, 'id': 5}
]

COMPARISON_FUNCTIONS = [
    {'name': COMPARISON_FUNCTION_EQUAL, 'id': 0},
    {'name': COMPARISON_FUNCTION_INCLUDE, 'id': 1},
    {'name': COMPARISON_FUNCTION_INCLUDE_WITH_ERROR, 'id': 2},
    {'name': COMPARISON_FUNCTION_INCLUDE_PARTIAL, 'id': 3},
    {'name': COMPARISON_FUNCTION_INCLUDE_PARTIAL_ORDERED, 'id': 4},
    {'name': COMPARISON_FUNCTION_SKIP, 'id': 5},
]

ET_FILE_NAME = 'converted-error-trace.json'

CODE_LINE_SEPARATOR = "|"
CODE_LINE_SEPARATOR_FOR_REGEXP = "\|"
FUNCTION_CALL_SEPARATOR = " "
CET_END = "__ERROR__"

DEBUG_ERROR_TRACE_COMPARISON = False
DISABLE_CACHE = False  # Use this flag for debugging MEA filters


def process_args(args: dict, as_str=False):
    for tag in [TAG_ADDITIONAL_MODEL_FUNCTIONS, TAG_FILTERED_MODEL_FUNCTIONS, TAG_USE_NOTES, TAG_USE_WARNS,
                TAG_IGNORE_NOTES_TEXT]:
        if tag in args:
            contents = args.get(tag, "")
            if contents:
                if isinstance(contents, str):
                    contents = contents.split(",")
                if isinstance(contents, list):
                    contents.sort()
                    if as_str:
                        contents = ",".join(contents)
                args[tag] = contents
            else:
                del args[tag]


def get_or_convert_error_trace(unsafe, conversion_function: str, args: dict) -> list:
    """
    Convert error trace for unsafe report and cache results, so the result can be reused later.
    """
    if isinstance(unsafe, ReportUnsafe):
        report_unsafe = unsafe
    elif isinstance(unsafe, MarkUnsafe):
        report_unsafe = unsafe.report
        if not report_unsafe:
            most_likely_report_id = MarkUnsafeReport.objects.filter(mark__id=unsafe.id).values_list('report')
            if most_likely_report_id:
                report_unsafe = ReportUnsafe.objects.get(id=most_likely_report_id[0][0])
                unsafe.report = report_unsafe
                unsafe.save()
    else:
        raise BridgeException("Unknown type of unsafe: {}".format(unsafe))

    if not report_unsafe:
        raise BridgeException("There is no unsafe report for this mark")
    if not args:
        args = {}

    process_args(args)
    args_str = json.dumps(args, sort_keys=True)

    def apply_new_conversion_function() -> list:
        parsed_trace = json.loads(
            ArchiveFileContent(report_unsafe, 'error_trace', ERROR_TRACE_FILE).content.decode('utf8'))
        return convert_error_trace(parsed_trace, conversion_function, args)

    if not DISABLE_CACHE:
        try:
            with ErrorTraceConvertionCache.objects.filter(
                    unsafe=report_unsafe, function=conversion_function, args=args_str).last().converted.file as fp:
                converted_error_trace = fp.read().decode('utf8')
        except:
            if DEBUG_ERROR_TRACE_COMPARISON:
                print("No cache for {}, {}, {}".format(report_unsafe, conversion_function, args_str))
            converted_error_trace = apply_new_conversion_function()
            et_file = dump_converted_error_trace(converted_error_trace)
            ErrorTraceConvertionCache.objects.create(unsafe=report_unsafe, function=conversion_function, converted=et_file,
                                                     args=args_str)
    else:
        converted_error_trace = apply_new_conversion_function()
    return converted_error_trace


def automatic_error_trace_editing(unsafe_report: ReportUnsafe) -> tuple:
    conversion_function = DEFAULT_CONVERSION_FUNCTION
    args = {TAG_IGNORE_NOTES_TEXT: True}
    converted_error_trace = __load_json(get_or_convert_error_trace(unsafe_report, conversion_function, args))
    visual_error_trace_json = __load_json(reports.utils.get_error_trace_content(unsafe_report))
    visual_error_trace = convert_error_trace(visual_error_trace_json, conversion_function, args)

    if visual_error_trace == converted_error_trace:
        comparison_function = DEFAULT_COMPARISON_FUNCTION
    else:
        comparison_function = COMPARISON_FUNCTION_INCLUDE_PARTIAL_ORDERED
    is_note_changed = False
    edited_error_trace = list()
    for elem in visual_error_trace:
        if elem[CET_OP] == CET_OP_NOTE:
            elem_id = elem[CET_ID]
            edited_note = elem[CET_DISPLAY_NAME]
            basic_note = None
            for basic_elem in converted_error_trace:
                if basic_elem[CET_ID] == elem_id:
                    if basic_elem[CET_OP] == CET_OP_NOTE:
                        basic_note = basic_elem[CET_DISPLAY_NAME]
                    break
            if not edited_note == basic_note:
                if basic_note:
                    is_note_changed = True
                    elem[CET_DISPLAY_NAME] = basic_note
                    edited_error_trace.append(elem)
                else:
                    # New note - cannot compare with other traces.
                    pass
            else:
                is_note_changed = True
                edited_error_trace.append(elem)
        else:
            edited_error_trace.append(elem)
    if not is_note_changed:
        args = {}

    for cv in [CONVERSION_FUNCTION_MODEL_FUNCTIONS, CONVERSION_FUNCTION_CALL_TREE]:
        converted_error_trace = __load_json(get_or_convert_error_trace(unsafe_report, cv, args))
        is_equal = compare_edited_traces(edited_error_trace, converted_error_trace, comparison_function,
                                         DEFAULT_SIMILARITY_THRESHOLD)[0]
        if is_equal:
            conversion_function = cv
            break
    return is_equal, edited_error_trace, conversion_function, args, comparison_function


def get_or_convert_error_trace_auto(unsafe_id: int, conversion_function: str, args: dict) -> list:
    if not args:
        args = {}
    process_args(args)
    args_str = json.dumps(args, sort_keys=True)
    report_unsafe = ReportUnsafe.objects.get(id=unsafe_id)

    def convert_error_trace_auto():
        parsed_trace = json.loads(
            ArchiveFileContent(report_unsafe, 'error_trace', ERROR_TRACE_FILE).content.decode('utf8'))
        return convert_error_trace(parsed_trace, conversion_function, args)

    if not DISABLE_CACHE:
        try:
            with ErrorTraceConvertionCache.objects.filter(
                    unsafe=report_unsafe, function=conversion_function, args=args_str).last().converted.file as fp:
                converted_error_trace = fp.read().decode('utf8')
        except:
            converted_error_trace = convert_error_trace_auto()
            et_file = dump_converted_error_trace(converted_error_trace)
            converted_error_trace = json.dumps(converted_error_trace)
            ErrorTraceConvertionCache.objects.create(unsafe=report_unsafe, function=conversion_function,
                                                     converted=et_file, args=args_str)
    else:
        converted_error_trace = convert_error_trace_auto()
        converted_error_trace = json.dumps(converted_error_trace)
    return converted_error_trace


def compare_edited_traces(edited_error_trace: list, compared_error_trace: list, comparison_function: str,
                          similarity_threshold: int) -> (bool, float):
    edited_error_trace = __load_json(edited_error_trace)
    compared_error_trace = error_trace_pretty_parse(error_trace_pretty_print(__load_json(compared_error_trace)))
    if DEBUG_ERROR_TRACE_COMPARISON:
        print("***************** Edited trace *****************")
        print(json.dumps(edited_error_trace, sort_keys=True, indent=4))
        print("**************** Compared trace ****************")
        print(json.dumps(compared_error_trace, sort_keys=True, indent=4))
        print("************** Edited trace (str) **************")
        print(error_trace_pretty_print(edited_error_trace))
        print("************* Compared trace (str) *************")
        print(error_trace_pretty_print(compared_error_trace))
    similarity = compare_error_traces(edited_error_trace, compared_error_trace, comparison_function)
    is_equal = is_equivalent(similarity, similarity_threshold)
    return is_equal, similarity


def compare_converted_traces(cet_1: list, cet_2: list, comparison_function: str, similarity_threshold: int) -> bool:
    cet_1 = __load_json(cet_1)
    cet_2 = __load_json(cet_2)
    similarity = compare_error_traces(cet_1, cet_2, comparison_function)
    is_equal = is_equivalent(similarity, similarity_threshold)
    return is_equal


def __load_json(et):
    if isinstance(et, str):
        et = json.loads(et)
    return et


def obtain_pretty_error_trace(converted_error_trace: list, unsafe, conversion_function: str, args: dict) -> str:
    try:
        # If trace is in new format, then just process it.
        return error_trace_pretty_print(converted_error_trace)
    except:
        # In case of old format create new converted error trace.
        converted_error_trace = get_or_convert_error_trace(unsafe, conversion_function, args)
        return error_trace_pretty_print(converted_error_trace)


def error_trace_pretty_print(converted_error_trace: list) -> str:
    """
    Print converted error trace (list of elements) for the user.
    """
    result = ""
    level = 0
    cur_thread = -1
    stack = list()
    if isinstance(converted_error_trace, str):
        converted_error_trace = json.loads(converted_error_trace)

    # Thread '0' is a normal thread.
    for elem in converted_error_trace:
        elem['thread'] = str(elem['thread'])

    for elem in converted_error_trace:
        op = elem[CET_OP]
        thread = elem[CET_THREAD]
        if cur_thread == -1:
            cur_thread = str(thread)
        elif not cur_thread == thread:
            cur_thread = str(thread)
            result += "{}\t{}{}{}\n".format("    0", CODE_LINE_SEPARATOR, FUNCTION_CALL_SEPARATOR * level, CET_END)
            level = 0
        name = elem[CET_DISPLAY_NAME]
        source = elem[CET_SOURCE]
        line = elem[CET_LINE]
        str_line_len = len(str(line))
        if str_line_len == 2:
            line = "   {}".format(line)
        elif str_line_len == 1:
            line = "    {}".format(line)
        elif str_line_len == 3:
            line = "  {}".format(line)
        elif str_line_len == 4:
            line = " {}".format(line)

        if op == CET_OP_RETURN:
            last_call = stack.pop()
            if name == last_call:
                level -= 1
            else:
                if DEBUG_ERROR_TRACE_COMPARISON:
                    print("Warning: there was no call for function {}. Last called function is {}. "
                          "Current id is {}".format(name, last_call, elem[CET_ID]))
                stack.append(last_call)
                continue
        # Pretty print.
        if op == CET_OP_CALL:
            result += "{}\t{}{}{}\n".format(line, CODE_LINE_SEPARATOR, FUNCTION_CALL_SEPARATOR * level, name)
        elif op in [CET_OP_ASSIGN, CET_OP_ASSUME, CET_OP_NOTE, CET_OP_WARN]:
            if level > 0:
                # with function calls
                spaces = " " * level
            else:
                spaces = " " * int(cur_thread)
            if op == CET_OP_ASSUME:
                if name:
                    result += "{}\t{}{}{}({})\n".format(line, CODE_LINE_SEPARATOR, spaces, op, source)
                else:
                    result += "{}\t{}{}{}(!({}))\n".format(line, CODE_LINE_SEPARATOR, spaces, op, source)
            elif op == CET_OP_ASSIGN:
                result += "{}\t{}{}{}: '{}'\n".format(line, CODE_LINE_SEPARATOR, spaces, op, source)
            else:
                result += "{}\t{}{}{}: '{}'\n".format(line, CODE_LINE_SEPARATOR, spaces, op, name)
        if op == CET_OP_CALL:
            level += 1
            stack.append(name)
    result += "{}\t{}{}{}\n".format("    0", CODE_LINE_SEPARATOR, FUNCTION_CALL_SEPARATOR * level, CET_END)
    return result


def error_trace_pretty_parse(pretty_error_trace: str) -> list:
    """
    Parse input string (result of error_trace_pretty_print() plus user changes) into converted error trace.
    """
    converted_error_trace = []
    cur_thread = 0
    cur_level = -1
    stack = list()
    not_parsed = None
    for line in pretty_error_trace.splitlines():
        if not_parsed:
            line = not_parsed + line.strip()
            not_parsed = None
        else:
            line = line.strip()
        m = re.match(r'^\s*(\d+)\s*{}({}*)(\w+)$'.format(CODE_LINE_SEPARATOR_FOR_REGEXP, FUNCTION_CALL_SEPARATOR), line)
        if m:
            line = m.group(1)
            level = len(m.group(2))
            func = m.group(3)
            if level == cur_level:
                ret_func = stack.pop()
                converted_error_trace.append({
                    CET_OP: CET_OP_RETURN,
                    CET_THREAD: cur_thread,
                    CET_SOURCE: None,
                    CET_DISPLAY_NAME: ret_func,
                    CET_ID: 0,
                    CET_LINE: line
                })
            elif level < cur_level:
                for i in range(cur_level - level + 1):
                    ret_func = stack.pop()
                    converted_error_trace.append({
                        CET_OP: CET_OP_RETURN,
                        CET_THREAD: cur_thread,
                        CET_SOURCE: None,
                        CET_DISPLAY_NAME: ret_func,
                        CET_ID: 0,
                        CET_LINE: line
                    })
            if func == CET_END:
                cur_thread += 1
                cur_level = -1
            else:
                converted_error_trace.append({
                    CET_OP: CET_OP_CALL,
                    CET_THREAD: cur_thread,
                    CET_SOURCE: None,
                    CET_DISPLAY_NAME: func,
                    CET_ID: 0,
                    CET_LINE: line
                })
                cur_level = level
                stack.append(func)
            continue
        m = re.match(r'^\s*(\d+)\s*{}({}*){}\((!?)(.+)\)$'.format(CODE_LINE_SEPARATOR_FOR_REGEXP,
                                                                  FUNCTION_CALL_SEPARATOR, CET_OP_ASSUME), line)
        if m:
            line = m.group(1)
            level = len(m.group(2))
            is_false = bool(m.group(3))
            assume = m.group(4)
            converted_error_trace.append({
                CET_OP: CET_OP_ASSUME,
                CET_THREAD: cur_thread,
                CET_SOURCE: assume,
                CET_DISPLAY_NAME: not is_false,
                CET_ID: 0,
                CET_LINE: line
            })
            continue
        m = re.match(r'^\s*(\d+)\s*{}({}*)(\w+): \'(.+)\'$'.format(CODE_LINE_SEPARATOR_FOR_REGEXP,
                                                                   FUNCTION_CALL_SEPARATOR), line)
        if m:
            line = m.group(1)
            level = len(m.group(2))
            op = m.group(3)
            text = m.group(4)
            converted_error_trace.append({
                CET_OP: op,
                CET_THREAD: cur_thread,
                CET_SOURCE: text,
                CET_DISPLAY_NAME: text,
                CET_ID: 0,
                CET_LINE: line
            })
            continue
        not_parsed = line
    if not_parsed:
        raise ValueError("Cannot parse line '{}' in edited error trace".format(line))
    return converted_error_trace


def dump_converted_error_trace(converted_error_trace):
    """
    Print converted error trace into file.
    """
    return file_get_or_create(
        BytesIO(
            json.dumps(converted_error_trace, ensure_ascii=False, sort_keys=True, indent=4).encode('utf8')),
        ET_FILE_NAME, ConvertedTraces)[0]
