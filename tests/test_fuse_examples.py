"""Behavioral tests demonstrating spec + delta + fuse composition."""

from __future__ import annotations

import inspect

from src.signia._core import fuse
#from signia import fuse


# --- shared specs used across entrypoints ---

def BaseConn_spec(
    *,
    host: str,
    user: str,
    password: str,
    database: str,
    port: int = 1025,
    ssl: bool = True,
    timeout: float = 30.0,
    schema: str | None = None,
    role: str | None = None,
    warehouse: str | None = None,
) -> None:
    ...


def Teradata_delta(*, tmode: str = "ANSI") -> None:
    ...


def Snowflake_delta(*, authenticator: str = "externalbrowser") -> None:
    ...


def Query_spec(*, query_text: str, enable_cache: bool = False) -> None:
    ...


class QueryRunner:
    """Minimal orchestrator used in the tests."""

    def __init__(self) -> None:
        self.connection_args: dict[str, object] = {}
        self.query_args: dict[str, object] = {}
        self.sections: dict[str, dict[str, object]] = {}

    @fuse(BaseConn_spec, Teradata_delta, Query_spec, publish="method")
    def configure(self, base, td, query):
        # Each proxy exposes the section it owns; store copies for assertions.
        self.sections = {
            "base": dict(base.kw),
            "td": dict(td.kw),
            "query": dict(query.kw),
        }
        self.connection_args = {**self.sections["base"], **self.sections["td"]}
        self.query_args = self.sections["query"]
        return self


@fuse(BaseConn_spec, Teradata_delta, Query_spec)
def run_teradata(base, td, query):
    runner = QueryRunner().configure(
        **base.kw,
        **td.kw,
        **query.kw,
    )
    return {
        "connection": runner.connection_args,
        "query": runner.query_args,
    }


@fuse(BaseConn_spec, Snowflake_delta, Query_spec)
def run_snowflake(base, snowflake, query):
    return {
        "connection": {**base.kw, **snowflake.kw},
        "query": dict(query.kw),
    }


def test_method_signature_and_slices():
    runner = QueryRunner()

    configured = runner.configure(
        host="db.example.com",
        user="alice",
        password="secret",
        database="analytics",
        query_text="SELECT 1",
    )

    assert configured is runner

    signature = inspect.signature(QueryRunner.configure)
    assert list(signature.parameters) == [
        "self",
        "host",
        "user",
        "password",
        "database",
        "port",
        "ssl",
        "timeout",
        "schema",
        "role",
        "warehouse",
        "tmode",
        "query_text",
        "enable_cache",
    ]

    assert runner.sections["base"] == {
        "host": "db.example.com",
        "user": "alice",
        "password": "secret",
        "database": "analytics",
        "port": 1025,
        "ssl": True,
        "timeout": 30.0,
        "schema": None,
        "role": None,
        "warehouse": None,
    }
    assert runner.sections["td"] == {"tmode": "ANSI"}
    assert runner.sections["query"] == {
        "query_text": "SELECT 1",
        "enable_cache": False,
    }


def test_function_signature_and_execution():
    result = run_teradata(
        host="db.example.com",
        user="alice",
        password="secret",
        database="analytics",
        query_text="SELECT 42",
        enable_cache=True,
        tmode="TERA",
    )

    signature = inspect.signature(run_teradata)
    assert list(signature.parameters) == [
        "host",
        "user",
        "password",
        "database",
        "port",
        "ssl",
        "timeout",
        "schema",
        "role",
        "warehouse",
        "tmode",
        "query_text",
        "enable_cache",
    ]

    assert result == {
        "connection": {
            "host": "db.example.com",
            "user": "alice",
            "password": "secret",
            "database": "analytics",
            "port": 1025,
            "ssl": True,
            "timeout": 30.0,
            "schema": None,
            "role": None,
            "warehouse": None,
            "tmode": "TERA",
        },
        "query": {
            "query_text": "SELECT 42",
            "enable_cache": True,
        },
    }


def test_new_delta_reuses_base_spec_defaults():
    result = run_snowflake(
        host="db.example.com",
        user="alice",
        password="secret",
        database="analytics",
        query_text="SELECT 7",
    )

    signature = inspect.signature(run_snowflake)
    assert list(signature.parameters) == [
        "host",
        "user",
        "password",
        "database",
        "port",
        "ssl",
        "timeout",
        "schema",
        "role",
        "warehouse",
        "authenticator",
        "query_text",
        "enable_cache",
    ]

    assert result == {
        "connection": {
            "host": "db.example.com",
            "user": "alice",
            "password": "secret",
            "database": "analytics",
            "port": 1025,
            "ssl": True,
            "timeout": 30.0,
            "schema": None,
            "role": None,
            "warehouse": None,
            "authenticator": "externalbrowser",
        },
        "query": {
            "query_text": "SELECT 7",
            "enable_cache": False,
        },
    }

def test_chain():
    run_teradata(host="db.example.com",
        user="alice",
        password="secret",
        database="analytics",
        query_text="SELECT 42",
        enable_cache=True,
        tmode="TERA",)
    print(run_teradata.__signature__)

if __name__=='__main__':
    test_chain()
    run_teradata()
