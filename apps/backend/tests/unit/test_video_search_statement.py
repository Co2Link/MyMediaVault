from uuid import uuid4

from sqlalchemy.dialects import mssql

from app.videos.service import build_video_search_statement


def test_video_search_statement_compiles_for_mssql_with_pagination() -> None:
    statement = build_video_search_statement(uuid4(), q=None, rating=None, status=None).offset(0).limit(25)

    compiled = str(statement.compile(dialect=mssql.dialect()))

    assert "ORDER BY" in compiled
    assert "ROW_NUMBER()" in compiled or "OFFSET" in compiled
