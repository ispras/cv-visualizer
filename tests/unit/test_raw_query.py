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

"""Unit tests for web.rawQuery (dialect-aware raw SQL builder)."""

import pytest

from jobs.models import Job, JobHistory
from web import rawQuery
from web.rawQuery import RawQuery, RawJoin

JOB = Job._meta.db_table
HIST = JobHistory._meta.db_table


def use_mysql(monkeypatch):
    monkeypatch.setattr(rawQuery, "get_db_engine", lambda: rawQuery.DB_MYSQL)


def use_postgres(monkeypatch):
    monkeypatch.setattr(rawQuery, "get_db_engine", lambda: rawQuery.DB_POSTGRESQL)


# --------------------------------------------------------------------------- #
# helpers                                                                     #
# --------------------------------------------------------------------------- #

def test_is_model_accepts_model_class_only():
    assert rawQuery.is_model(Job) is True
    assert rawQuery.is_model(Job()) is False
    assert rawQuery.is_model(42) is False


def test_table_name_requires_model():
    with pytest.raises(ValueError):
        RawQuery("not a model").table_name


# --------------------------------------------------------------------------- #
# fields                                                                      #
# --------------------------------------------------------------------------- #

def test_select_string_field():
    query = RawQuery(Job)
    query.select("id")
    assert query.sql == 'SELECT "{}"."id" FROM "{}"'.format(JOB, JOB)


def test_select_tuple_with_table_and_alias():
    query = RawQuery(Job)
    query.select(("id", JobHistory, "history_id"))
    assert '"{}"."id" AS "history_id"'.format(HIST) in query.sql


def test_select_rejects_unknown_field_format():
    with pytest.raises(ValueError):
        RawQuery(Job).select(123)


def test_select_rejects_unknown_table_type():
    with pytest.raises(ValueError):
        RawQuery(Job).select(("id", "not a model"))


def test_select_rejects_unnamed_subquery():
    subquery = RawQuery(JobHistory)
    with pytest.raises(ValueError):
        RawQuery(Job).select(("id", subquery))


# --------------------------------------------------------------------------- #
# where / having / group_by / order_by                                        #
# --------------------------------------------------------------------------- #

def test_where_with_arguments():
    query = RawQuery(Job)
    query.select("id")
    query.where("{0} = %s", "id", args_list=[5])
    assert 'WHERE ("{}"."id" = %s)'.format(JOB) in query.sql
    assert query.sql_args == [5]


def test_group_by_and_having():
    query = RawQuery(Job)
    query.select("id")
    query.group_by("id")
    query.having("COUNT({0}) > %s", "id", args_list=[3])
    assert 'GROUP BY "{}"."id"'.format(JOB) in query.sql
    assert 'HAVING (COUNT("{}"."id") > %s)'.format(JOB) in query.sql
    assert query.sql_args == [3]


def test_order_by_appends_nulls_last_for_postgres(monkeypatch):
    use_postgres(monkeypatch)
    query = RawQuery(Job)
    query.order_by("id", "DESC")
    assert query.sql.endswith('ORDER BY "{}"."id" DESC NULLS LAST'.format(JOB))


def test_order_by_omits_nulls_last_for_mysql(monkeypatch):
    use_mysql(monkeypatch)
    query = RawQuery(Job)
    query.order_by("id", "ASC")
    assert query.sql.rstrip().endswith('ORDER BY "{}"."id" ASC'.format(JOB))
    assert "NULLS LAST" not in query.sql


def test_order_by_aggregation_sql(monkeypatch):
    use_postgres(monkeypatch)
    query = RawQuery(Job)
    query.order_by_aggregation("COUNT({0})", "DESC", "id")
    assert 'ORDER BY COUNT("{}"."id") DESC NULLS LAST'.format(JOB) in query.sql


# --------------------------------------------------------------------------- #
# aggregates                                                                  #
# --------------------------------------------------------------------------- #

def test_aggregate_postgres_array_agg(monkeypatch):
    use_postgres(monkeypatch)
    query = RawQuery(Job)
    query.aggregate("ids", "ARRAY_AGG({0})", "id")
    assert 'ARRAY_AGG("{}"."id") AS "ids"'.format(JOB) in query.sql


def test_aggregate_mysql_uses_group_concat(monkeypatch):
    use_mysql(monkeypatch)
    query = RawQuery(Job)
    query.aggregate("ids", "ARRAY_AGG({0})", "id")
    assert 'GROUP_CONCAT("{}"."id") AS "ids"'.format(JOB) in query.sql


def test_sql_args_order_fields_where_having():
    query = RawQuery(Job)
    query.aggregate("ids", "ARRAY_AGG({0})", "id", args_list=[3])
    query.where("{0} = %s", "id", args_list=[1])
    query.having("COUNT({0}) > %s", "id", args_list=[2])
    assert query.sql_args == [3, 1, 2]


# --------------------------------------------------------------------------- #
# joins                                                                       #
# --------------------------------------------------------------------------- #

def test_join_model_to_model_with_field_names():
    query = RawQuery(Job)
    query.join("INNER", JobHistory, "id", "job_id")
    assert 'INNER JOIN "{}" ON ("{}"."id" = "{}"."job_id")'.format(HIST, HIST, JOB) in query.sql


def test_join_model_to_model_with_tuple_pairs():
    query = RawQuery(Job)
    query.join("LEFT", JobHistory, ("id", "job_id"))
    assert 'LEFT JOIN "{}" ON ("{}"."id" = "{}"."job_id")'.format(HIST, HIST, JOB) in query.sql


def test_join_rejects_bad_clause_arguments():
    query = RawQuery(Job)
    query.join("INNER", JobHistory, "id")
    with pytest.raises(ValueError):
        query.sql


def test_join_subquery_gets_generated_name_and_recursive_args():
    subquery = RawQuery(JobHistory)
    subquery.select("id")
    subquery.where("{0} = %s", "job_id", args_list=[9])
    query = RawQuery(Job)
    query.join("INNER", subquery, "id", "job_id")
    assert subquery.name == "T1"
    assert 'INNER JOIN (SELECT' in query.sql
    assert '"T1"' in query.sql
    assert query.sql_args == [9]


def test_raw_join_exposes_join_args():
    subquery = RawQuery(JobHistory)
    subquery.where("x = %s", "id", args_list=[7])
    join = RawJoin("INNER", subquery, "id", "job_id")
    assert join.join_args == [7]
    assert join.subquery is subquery
