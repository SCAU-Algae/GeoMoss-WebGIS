"""
管理员专属接口：数据库 CRUD、公告发布、联系方式配置。
"""

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from api.auth import get_auth_db_connection, require_admin

IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class InsertRowRequest(BaseModel):
    row: Dict[str, Any]


class UpdateRowRequest(BaseModel):
    where: Dict[str, Any]
    values: Dict[str, Any]


class DeleteRowRequest(BaseModel):
    where: Dict[str, Any]


class PublishAnnouncementRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class UpdateContactRequest(BaseModel):
    contact: str = Field(..., min_length=1, max_length=500)


def _db_connection():
    return get_auth_db_connection()


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_identifier(name: str) -> str:
    raw = str(name or "").strip()
    if not IDENTIFIER_PATTERN.fullmatch(raw):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"非法标识符: {name}",
        )
    return raw


def _quote_identifier(name: str) -> str:
    safe = _validate_identifier(name)
    return f'"{safe}"'


def _normalize_sql_value(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return value


def _table_columns_sync(conn, table_name: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT
            c.column_name AS name,
            c.data_type AS type,
            CASE WHEN c.is_nullable = 'NO' THEN 1 ELSE 0 END AS notnull,
            CASE WHEN tc.constraint_type = 'PRIMARY KEY' THEN 1 ELSE 0 END AS pk
        FROM information_schema.columns c
        LEFT JOIN information_schema.key_column_usage kcu
            ON c.table_schema = kcu.table_schema
            AND c.table_name = kcu.table_name
            AND c.column_name = kcu.column_name
        LEFT JOIN information_schema.table_constraints tc
            ON kcu.constraint_schema = tc.constraint_schema
            AND kcu.constraint_name = tc.constraint_name
            AND tc.constraint_type = 'PRIMARY KEY'
        WHERE c.table_schema = 'public' AND c.table_name = ?
        ORDER BY c.ordinal_position ASC
        """,
        (table_name,),
    ).fetchall()
    return [
        {
            "name": str(dict(row).get("name") or ""),
            "type": str(dict(row).get("type") or ""),
            "notnull": int(dict(row).get("notnull") or 0),
            "pk": int(dict(row).get("pk") or 0),
        }
        for row in rows
    ]


def _resolve_order_column(columns: List[Dict[str, Any]]) -> str:
    names = [str(item.get("name") or "") for item in columns]
    for preferred in ("updated_at", "created_at", "id"):
        if preferred in names:
            return _quote_identifier(preferred)
    pk = next((item for item in columns if int(item.get("pk") or 0) == 1 and item.get("name")), None)
    if pk:
        return _quote_identifier(str(pk["name"]))
    return "ctid"


def _list_tables_sync() -> List[Dict[str, Any]]:
    with _db_connection() as conn:
        table_rows = conn.execute(
            """
            SELECT table_name AS name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name ASC
            """
        ).fetchall()

        result: List[Dict[str, Any]] = []
        for table_row in table_rows:
            table_name = str(dict(table_row).get("name") or "")
            if not table_name:
                continue

            result.append(
                {
                    "name": table_name,
                    "columns": _table_columns_sync(conn, table_name),
                }
            )

    return result


def _list_table_rows_sync(table_name: str, limit: int, offset: int) -> List[Dict[str, Any]]:
    safe_table = _quote_identifier(table_name)
    safe_limit = max(1, min(int(limit), 200))
    safe_offset = max(0, int(offset))

    with _db_connection() as conn:
        columns = _table_columns_sync(conn, table_name)
        order_column = _resolve_order_column(columns)
        rows = conn.execute(
            f"SELECT ctid::text AS __rowid, * FROM {safe_table} ORDER BY {order_column} DESC LIMIT ? OFFSET ?",
            (safe_limit, safe_offset),
        ).fetchall()

    return [dict(row) for row in rows]


def _build_where_clause(where: Dict[str, Any]) -> Dict[str, Any]:
    if not where:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="where 条件不能为空",
        )

    clauses: List[str] = []
    values: List[Any] = []

    for key, value in where.items():
        if key == "__rowid":
            clauses.append("ctid = ?::tid")
            values.append(str(value))
            continue

        col = _quote_identifier(key)
        clauses.append(f"{col} = ?")
        values.append(_normalize_sql_value(value))

    return {
        "sql": " AND ".join(clauses),
        "values": values,
    }


def _insert_row_sync(table_name: str, row: Dict[str, Any]) -> int:
    if not row:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="插入数据不能为空",
        )

    keys = [_validate_identifier(k) for k in row.keys()]
    cols = ", ".join(_quote_identifier(k) for k in keys)
    holders = ", ".join(["?"] * len(keys))
    values = [_normalize_sql_value(row[k]) for k in keys]

    safe_table = _quote_identifier(table_name)
    sql = f"INSERT INTO {safe_table} ({cols}) VALUES ({holders})"

    with _db_connection() as conn:
        cursor = conn.execute(sql, values)
        conn.commit()
        return int(cursor.lastrowid or 0)


def _update_rows_sync(table_name: str, where: Dict[str, Any], values_payload: Dict[str, Any]) -> int:
    if not values_payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="更新字段不能为空",
        )

    safe_table = _quote_identifier(table_name)
    where_sql = _build_where_clause(where)

    set_parts: List[str] = []
    set_values: List[Any] = []
    for key, value in values_payload.items():
        if key == "__rowid":
            continue
        col = _quote_identifier(key)
        set_parts.append(f"{col} = ?")
        set_values.append(_normalize_sql_value(value))

    if not set_parts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="没有可更新字段",
        )

    sql = f"UPDATE {safe_table} SET {', '.join(set_parts)} WHERE {where_sql['sql']}"

    with _db_connection() as conn:
        cursor = conn.execute(sql, set_values + where_sql["values"])
        conn.commit()
        return int(cursor.rowcount or 0)


def _delete_rows_sync(table_name: str, where: Dict[str, Any]) -> int:
    safe_table = _quote_identifier(table_name)
    where_sql = _build_where_clause(where)

    sql = f"DELETE FROM {safe_table} WHERE {where_sql['sql']}"

    with _db_connection() as conn:
        cursor = conn.execute(sql, where_sql["values"])
        conn.commit()
        return int(cursor.rowcount or 0)


def _publish_announcement_sync(message: str, admin_username: str) -> int:
    now_iso = _iso_now()

    with _db_connection() as conn:
        conn.execute(
            "UPDATE announcements SET is_active = 0, updated_at = ? WHERE is_active = 1",
            (now_iso,),
        )

        cursor = conn.execute(
            """
            INSERT INTO announcements (message, created_by, is_active, created_at, updated_at)
            VALUES (?, ?, 1, ?, ?)
            """,
            (message, admin_username, now_iso, now_iso),
        )
        conn.commit()
        return int(cursor.lastrowid or 0)


def _update_admin_contact_sync(contact: str) -> None:
    now_iso = _iso_now()

    with _db_connection() as conn:
        conn.execute(
            """
            INSERT INTO system_config (key, value, updated_at)
            VALUES ('admin_contact', ?, ?)
            ON CONFLICT(key)
            DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (contact, now_iso),
        )
        conn.commit()


def _row_count(conn, table_name: str, where_sql: str = "1=1", params: tuple = ()) -> int:
    try:
        row = conn.execute(f"SELECT COUNT(*) AS cnt FROM {_quote_identifier(table_name)} WHERE {where_sql}", params).fetchone()
        return int((dict(row).get("cnt") if row else 0) or 0)
    except Exception:
        return 0


def _fetch_limited(conn, sql: str, params: tuple = ()) -> List[Dict[str, Any]]:
    try:
        rows = conn.execute(sql, params).fetchall()
        return [dict(row) for row in rows]
    except Exception:
        return []


def _get_admin_overview_sync() -> Dict[str, Any]:
    now_iso = _iso_now()
    with _db_connection() as conn:
        table_count = conn.execute(
            "SELECT COUNT(*) AS cnt FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
        ).fetchone()

        total_users = _row_count(conn, "users")
        total_sessions = _row_count(conn, "sessions")
        online_sessions = _row_count(conn, "sessions", "expires_at > ?", (now_iso,))
        total_messages = _row_count(conn, "user_messages")
        visible_messages = _row_count(conn, "user_messages", "is_visible = 1")
        active_announcement = _row_count(conn, "announcements", "is_active = 1")
        total_visits = _row_count(conn, "user_visits")
        total_visit_events = _row_count(conn, "visit_tracking_events")
        total_guest_identities = _row_count(conn, "guest_identity_records")
        total_three_d_layers = _row_count(conn, "three_d_layers")
        published_three_d_layers = _row_count(conn, "three_d_layers", "status = ?", ("published",))
        processing_jobs = _row_count(
            conn,
            "geodata_processing_jobs",
            "status IN (?, ?, ?)",
            ("queued", "processing", "running"),
        )

        role_rows = _fetch_limited(
            conn,
            """
            SELECT role, COUNT(*) AS cnt
            FROM users
            GROUP BY role
            ORDER BY cnt DESC, role ASC
            """
        )
        online_role_rows = _fetch_limited(
            conn,
            """
            SELECT role, COUNT(*) AS cnt
            FROM sessions
            WHERE expires_at > ?
            GROUP BY role
            ORDER BY cnt DESC, role ASC
            """,
            (now_iso,),
        )
        recent_users = _fetch_limited(
            conn,
            """
            SELECT
                u.username,
                u.role,
                u.avatar_index,
                u.created_at,
                COALESCE(m.login_count, 0) AS login_count,
                COALESCE(m.total_visit_count, 0) AS total_visit_count,
                COALESCE(m.total_api_calls, 0) AS total_api_calls,
                m.last_login_at,
                m.last_logout_at
            FROM users u
            LEFT JOIN user_metrics m ON m.username = u.username
            ORDER BY u.created_at DESC
            LIMIT 12
            """
        )
        active_sessions = _fetch_limited(
            conn,
            """
            SELECT username, role, ip, user_agent, created_at, expires_at
            FROM sessions
            WHERE expires_at > ?
            ORDER BY created_at DESC
            LIMIT 12
            """,
            (now_iso,),
        )
        recent_visits = _fetch_limited(
            conn,
            """
            SELECT username, role, ip_city, ip_region, ip_country, coord_source, geo_permission, visit_time, created_at
            FROM visit_tracking_events
            ORDER BY id DESC
            LIMIT 12
            """
        )
        top_users = _fetch_limited(
            conn,
            """
            SELECT username, login_count, total_visit_count, total_api_calls, last_login_at, updated_at
            FROM user_metrics
            ORDER BY total_api_calls DESC, total_visit_count DESC, username ASC
            LIMIT 12
            """
        )
        geodata_jobs = _fetch_limited(
            conn,
            """
            SELECT job_id, job_type, status, phase, progress, message, layer_id, dataset_id, updated_at, finished_at
            FROM geodata_processing_jobs
            ORDER BY updated_at DESC
            LIMIT 8
            """
        )
        three_d_layers = _fetch_limited(
            conn,
            """
            SELECT id, name, status, feature_count, published_at, updated_at
            FROM three_d_layers
            ORDER BY sort_order ASC, updated_at DESC
            LIMIT 8
            """
        )

    return {
        "table_count": int((dict(table_count).get("cnt") if table_count else 0) or 0),
        "total_users": total_users,
        "total_sessions": total_sessions,
        "online_sessions": online_sessions,
        "total_messages": total_messages,
        "visible_messages": visible_messages,
        "active_announcement": active_announcement,
        "total_visits": total_visits,
        "total_visit_events": total_visit_events,
        "total_guest_identities": total_guest_identities,
        "total_three_d_layers": total_three_d_layers,
        "published_three_d_layers": published_three_d_layers,
        "processing_jobs": processing_jobs,
        "users_by_role": role_rows,
        "online_by_role": online_role_rows,
        "recent_users": recent_users,
        "active_sessions": active_sessions,
        "recent_visits": recent_visits,
        "top_users": top_users,
        "geodata_jobs": geodata_jobs,
        "three_d_layers": three_d_layers,
        "snapshot_at": now_iso,
    }


router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/overview")
async def get_admin_overview(
    _session: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    data = await asyncio.to_thread(_get_admin_overview_sync)
    return {"status": "success", "data": data}


@router.get("/db/tables")
async def list_tables(
    _session: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    tables = await asyncio.to_thread(_list_tables_sync)
    return {
        "status": "success",
        "data": tables,
    }


@router.get("/db/table/{table_name}/rows")
async def list_table_rows(
    table_name: str,
    limit: int = Query(default=30, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _session: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    rows = await asyncio.to_thread(_list_table_rows_sync, table_name, limit, offset)
    return {
        "status": "success",
        "data": rows,
    }


@router.post("/db/table/{table_name}/insert")
async def insert_table_row(
    table_name: str,
    payload: InsertRowRequest,
    _session: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    row_id = await asyncio.to_thread(_insert_row_sync, table_name, payload.row)
    return {
        "status": "success",
        "message": "插入成功",
        "data": {"row_id": row_id},
    }


@router.post("/db/table/{table_name}/update")
async def update_table_rows(
    table_name: str,
    payload: UpdateRowRequest,
    _session: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    affected = await asyncio.to_thread(
        _update_rows_sync,
        table_name,
        payload.where,
        payload.values,
    )
    return {
        "status": "success",
        "message": "更新完成",
        "data": {"affected": affected},
    }


@router.post("/db/table/{table_name}/delete")
async def delete_table_rows(
    table_name: str,
    payload: DeleteRowRequest,
    _session: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    affected = await asyncio.to_thread(_delete_rows_sync, table_name, payload.where)
    return {
        "status": "success",
        "message": "删除完成",
        "data": {"affected": affected},
    }


@router.post("/announcement/publish")
async def publish_announcement(
    payload: PublishAnnouncementRequest,
    session: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    message_text = str(payload.message or "").strip()
    if not message_text:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="公告内容不能为空",
        )

    created_id = await asyncio.to_thread(
        _publish_announcement_sync,
        message_text,
        str(session.get("username") or "admin"),
    )

    return {
        "status": "success",
        "message": "公告发布成功",
        "data": {"id": created_id},
    }


@router.post("/config/contact")
async def update_admin_contact(
    payload: UpdateContactRequest,
    _session: Dict[str, Any] = Depends(require_admin),
) -> Dict[str, Any]:
    contact = str(payload.contact or "").strip()
    if not contact:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="联系方式不能为空",
        )

    await asyncio.to_thread(_update_admin_contact_sync, contact)

    return {
        "status": "success",
        "message": "管理员联系方式已更新",
    }
