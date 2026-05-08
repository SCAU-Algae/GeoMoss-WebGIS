"""
PostgreSQL 数据库适配层 — 兼容 sqlite3 调用风格。
提供 get_auth_db_connection() 返回兼容 connection 对象，
支持 .execute(sql, params) + ? 占位符自动转 %s + Row 字典访问。
"""

import logging
import os
import re
from contextlib import contextmanager
from typing import Optional

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://webgis:webgis_dev_2026@127.0.0.1:5432/webgis",
)


def _sqlite_to_pg(sql: str) -> str:
    """将 SQLite SQL 转换为 PostgreSQL 兼容 SQL。"""
    # 0. PRAGMA table_info(x) → information_schema.columns 查询
    pragma_match = re.match(
        r"^\s*PRAGMA\s+table_info\s*\(\s*['\"]?(\w+)['\"]?\s*\)\s*$",
        sql, re.IGNORECASE
    )
    if pragma_match:
        table = pragma_match.group(1)
        return (
            f"SELECT column_name AS name FROM information_schema.columns "
            f"WHERE table_name='{table}' AND table_schema='public' ORDER BY ordinal_position"
        )

    # 1. 替换 ? 占位符为 %s（不在字符串字面量内）
    sql = _replace_placeholders(sql)
    # 2. INTEGER PRIMARY KEY AUTOINCREMENT → SERIAL PRIMARY KEY
    sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    # 3. REAL → DOUBLE PRECISION
    sql = re.sub(r'\bREAL\b', 'DOUBLE PRECISION', sql)
    # 4. SQLite datetime('now') → PostgreSQL NOW()
    sql = re.sub(r"datetime\('now'\)", 'NOW()', sql, flags=re.IGNORECASE)
    return sql


def _replace_placeholders(sql: str) -> str:
    """将 SQL 中的 ? 占位符替换为 %s，跳过字符串内的 ?。"""
    result = []
    in_string = False
    string_char = None
    i = 0
    while i < len(sql):
        ch = sql[i]
        if in_string:
            result.append(ch)
            if ch == string_char and (i == 0 or sql[i - 1] != '\\'):
                in_string = False
                string_char = None
            i += 1
        elif ch in ("'", '"'):
            result.append(ch)
            in_string = True
            string_char = ch
            i += 1
        elif ch == '?':
            result.append('%s')
            i += 1
        else:
            result.append(ch)
            i += 1
    return ''.join(result)


class PgRow:
    """模拟 sqlite3.Row 对象，支持索引和键名访问。"""

    def __init__(self, data: dict):
        self._data = data
        self._keys = list(data.keys())

    def keys(self):
        return self._keys

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._data[self._keys[key]]
        return self._data[key]

    def __iter__(self):
        return iter(self._data.values())

    def __len__(self):
        return len(self._data)

    def __contains__(self, key):
        return key in self._data

    def get(self, key, default=None):
        if isinstance(key, int):
            if key < len(self._keys):
                return self._data[self._keys[key]]
            return default
        return self._data.get(key, default)

    def __repr__(self):
        return f"PgRow({self._data})"


class PgCursor:
    """模拟 sqlite3.Cursor，将 psycopg2 RealDictRow 转为 PgRow。"""

    def __init__(self, pg_cursor):
        self._cur = pg_cursor
        self.rowcount = pg_cursor.rowcount
        self.lastrowid = None

    def fetchone(self) -> Optional[PgRow]:
        row = self._cur.fetchone()
        if row is None:
            return None
        return PgRow(dict(row))

    def fetchall(self) -> list[PgRow]:
        return [PgRow(dict(r)) for r in self._cur.fetchall()]

    def close(self):
        self._cur.close()


class PgConnection:
    """模拟 sqlite3.Connection，包装 psycopg2 connection。"""

    def __init__(self, pg_conn):
        self._conn = pg_conn
        self.row_factory = None  # 兼容 sqlite3 的 row_factory 赋值

    def execute(self, sql: str, params: tuple = ()) -> PgCursor:
        pg_sql = _sqlite_to_pg(sql)
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        try:
            cur.execute(pg_sql, params)
            pc = PgCursor(cur)
            # 尝试获取 lastrowid（INSERT RETURNING id 或 SERIAL）
            if pg_sql.strip().upper().startswith("INSERT"):
                try:
                    # 尝试从 RETURNING 获取，如果没有则尝试 lastval()
                    pass
                except Exception:
                    pass
            return pc
        except Exception:
            cur.close()
            raise

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

    def cursor(self):
        """直接获取 PgCursor（兼容直接 cursor() 调用）。"""
        return PgCursor(self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self.commit()
        else:
            self.rollback()
        self.close()
        return False


def _pg_connection():
    conn = psycopg2.connect(DATABASE_URL, connect_timeout=10, options='-c client_encoding=UTF8')
    conn.autocommit = False
    return conn


@contextmanager
def get_auth_db_connection():
    """与 sqlite3 兼容的连接工厂：返回 PgConnection 包装对象。"""
    raw = _pg_connection()
    wrapper = PgConnection(raw)
    try:
        yield wrapper
        raw.commit()
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()


def _column_exists(pg_conn, table: str, column: str) -> bool:
    """检查 PostgreSQL 表中是否存在指定列。"""
    cur = pg_conn.cursor()
    cur.execute(
        "SELECT EXISTS(SELECT 1 FROM information_schema.columns "
        "WHERE table_name=%s AND column_name=%s)",
        (table, column),
    )
    result = cur.fetchone()[0]
    cur.close()
    return result


def init_db():
    """
    幂等数据库初始化 — 使用原生 psycopg2 连接（不经兼容层，直接用 %s）。
    """
    raw = _pg_connection()
    try:
        cur = raw.cursor()

        def safe(sql, params=()):
            try:
                cur.execute(sql, params)
                return True
            except Exception as e:
                logger.warning("SQL 警告: %s | %s", str(e)[:200], sql[:120])
                raw.rollback()
                return False

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'registered',
                avatar_index INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
        """)
        if not _column_exists(raw, "users", "avatar_index"):
            safe("ALTER TABLE users ADD COLUMN avatar_index INTEGER NOT NULL DEFAULT 0")
        if not _column_exists(raw, "users", "email"):
            safe("ALTER TABLE users ADD COLUMN email TEXT DEFAULT ''")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                role TEXT NOT NULL,
                guest_uid TEXT,
                guest_device_id TEXT,
                ip TEXT,
                user_agent TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            )
        """)
        for col in ("guest_uid", "guest_device_id"):
            if not _column_exists(raw, "sessions", col):
                safe(f"ALTER TABLE sessions ADD COLUMN {col} TEXT")
        for idx_sql in (
            "CREATE INDEX IF NOT EXISTS idx_sessions_username ON sessions(username)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_expires_at ON sessions(expires_at)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_guest_uid ON sessions(guest_uid)",
        ):
            safe(idx_sql)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_metrics (
                username TEXT PRIMARY KEY,
                login_count INTEGER NOT NULL DEFAULT 0,
                total_login_seconds INTEGER NOT NULL DEFAULT 0,
                total_api_calls INTEGER NOT NULL DEFAULT 0,
                total_visit_count INTEGER NOT NULL DEFAULT 0,
                last_login_at TEXT,
                last_logout_at TEXT,
                updated_at TEXT NOT NULL
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS api_usage_daily (
                username TEXT NOT NULL,
                role TEXT NOT NULL,
                usage_date TEXT NOT NULL,
                calls INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (username, usage_date)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_visits (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL,
                ip TEXT,
                city TEXT,
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                visit_time TEXT NOT NULL,
                user_agent TEXT,
                created_at TEXT NOT NULL
            )
        """)
        for idx_sql in (
            "CREATE INDEX IF NOT EXISTS idx_user_visits_username ON user_visits(username)",
            "CREATE INDEX IF NOT EXISTS idx_user_visits_created_at ON user_visits(created_at)",
        ):
            safe(idx_sql)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS visit_tracking_events (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'guest',
                guest_uid TEXT,
                quota_subject TEXT,
                ip TEXT,
                ip_city TEXT,
                ip_region TEXT,
                ip_country TEXT,
                latitude DOUBLE PRECISION,
                longitude DOUBLE PRECISION,
                coord_source TEXT NOT NULL DEFAULT 'unknown',
                geo_permission TEXT NOT NULL DEFAULT 'unknown',
                gps_accuracy DOUBLE PRECISION,
                gps_error TEXT,
                gps_timestamp TEXT,
                encoded_pos TEXT NOT NULL DEFAULT '0',
                visit_time TEXT NOT NULL,
                user_agent TEXT,
                created_at TEXT NOT NULL,
                supabase_sync_status TEXT NOT NULL DEFAULT 'skipped',
                supabase_sync_error TEXT,
                supabase_synced_at TEXT
            )
        """)
        for idx_sql in (
            "CREATE INDEX IF NOT EXISTS idx_visit_username ON visit_tracking_events(username)",
            "CREATE INDEX IF NOT EXISTS idx_visit_created_at ON visit_tracking_events(created_at)",
            "CREATE INDEX IF NOT EXISTS idx_visit_source ON visit_tracking_events(coord_source)",
            "CREATE INDEX IF NOT EXISTS idx_visit_guest_uid ON visit_tracking_events(guest_uid)",
            "CREATE INDEX IF NOT EXISTS idx_visit_quota ON visit_tracking_events(quota_subject)",
        ):
            safe(idx_sql)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS guest_identity_records (
                id SERIAL PRIMARY KEY,
                guest_uid TEXT UNIQUE NOT NULL,
                username TEXT NOT NULL DEFAULT 'user',
                role TEXT NOT NULL DEFAULT 'guest',
                guest_device_id TEXT,
                ip TEXT,
                coord_source TEXT NOT NULL DEFAULT 'unknown',
                geo_permission TEXT NOT NULL DEFAULT 'unknown',
                encoded_pos TEXT NOT NULL DEFAULT '0',
                last_latitude DOUBLE PRECISION,
                last_longitude DOUBLE PRECISION,
                user_agent TEXT,
                visit_count INTEGER NOT NULL DEFAULT 0,
                first_seen_at TEXT NOT NULL DEFAULT '',
                last_seen_at TEXT NOT NULL DEFAULT ''
            )
        """)
        for idx_sql in (
            "CREATE INDEX IF NOT EXISTS idx_guest_last_seen ON guest_identity_records(last_seen_at)",
            "CREATE INDEX IF NOT EXISTS idx_guest_encoded_pos ON guest_identity_records(encoded_pos)",
        ):
            safe(idx_sql)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS announcements (
                id SERIAL PRIMARY KEY,
                message TEXT NOT NULL,
                created_by TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS announcement_dismissals (
                username TEXT NOT NULL,
                announcement_id INTEGER NOT NULL,
                dismissed_at TEXT NOT NULL,
                PRIMARY KEY (username, announcement_id)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_messages (
                id SERIAL PRIMARY KEY,
                username TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                is_visible INTEGER NOT NULL DEFAULT 1
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                username TEXT PRIMARY KEY,
                default_basemap TEXT NOT NULL DEFAULT '',
                language TEXT NOT NULL DEFAULT 'zh-CN',
                unit_system TEXT NOT NULL DEFAULT 'metric',
                preferred_agent_model TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            )
        """)
        safe("CREATE INDEX IF NOT EXISTS idx_pref_updated ON user_preferences(updated_at)")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS system_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS api_keys (
                key_name TEXT PRIMARY KEY,
                key_value TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT ''
            )
        """)

        safe("""
            INSERT INTO system_config (key, value, updated_at)
            VALUES ('admin_contact', %s, NOW()::text)
            ON CONFLICT (key) DO NOTHING
        """, ("管理员联系方式：请联系系统管理员",))

        # Agent Chat 相关表
        cur.execute("""
            CREATE TABLE IF NOT EXISTS agent_chat_usage_daily (
                quota_subject TEXT NOT NULL,
                role TEXT NOT NULL,
                usage_date TEXT NOT NULL,
                calls INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (quota_subject, usage_date)
            )
        """)
        safe("CREATE INDEX IF NOT EXISTS idx_agent_chat_usage_role_date ON agent_chat_usage_daily(role, usage_date)")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS agent_user_config (
                username TEXT PRIMARY KEY,
                api_key TEXT,
                base_url TEXT,
                model TEXT,
                system_prompt TEXT,
                timeout_seconds INTEGER,
                max_tokens INTEGER,
                temperature DOUBLE PRECISION,
                updated_at TEXT NOT NULL,
                updated_by TEXT
            )
        """)
        safe("CREATE INDEX IF NOT EXISTS idx_agent_user_config_updated_at ON agent_user_config(updated_at)")

        # 管理员地理数据生产链路：行政区划、3D 图层、后台任务。
        cur.execute("""
            CREATE TABLE IF NOT EXISTS admin_boundary_datasets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                source_filename TEXT NOT NULL DEFAULT '',
                storage_path TEXT NOT NULL DEFAULT '',
                field_code TEXT NOT NULL,
                field_name TEXT NOT NULL,
                field_level TEXT NOT NULL DEFAULT '',
                fields_json TEXT NOT NULL DEFAULT '[]',
                feature_count INTEGER NOT NULL DEFAULT 0,
                bbox_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'ready',
                created_by TEXT NOT NULL DEFAULT 'admin',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        safe("CREATE INDEX IF NOT EXISTS idx_boundary_status ON admin_boundary_datasets(status)")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS admin_boundary_features (
                id SERIAL PRIMARY KEY,
                dataset_id TEXT NOT NULL,
                code TEXT NOT NULL,
                name TEXT NOT NULL,
                level TEXT NOT NULL DEFAULT '',
                bbox_json TEXT NOT NULL DEFAULT '[]',
                geometry_json TEXT NOT NULL DEFAULT '{}',
                properties_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                UNIQUE(dataset_id, code)
            )
        """)
        if not _column_exists(raw, "admin_boundary_features", "geometry_json"):
            safe("ALTER TABLE admin_boundary_features ADD COLUMN geometry_json TEXT NOT NULL DEFAULT '{}'")
        safe("CREATE INDEX IF NOT EXISTS idx_boundary_features_dataset ON admin_boundary_features(dataset_id)")
        safe("CREATE INDEX IF NOT EXISTS idx_boundary_features_code ON admin_boundary_features(code)")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS three_d_layers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                tileset_url TEXT NOT NULL DEFAULT '',
                storage_path TEXT NOT NULL DEFAULT '',
                source_filename TEXT NOT NULL DEFAULT '',
                boundary_dataset_id TEXT NOT NULL DEFAULT '',
                height_field TEXT NOT NULL DEFAULT '',
                classification_field TEXT NOT NULL DEFAULT '',
                color_ramp TEXT NOT NULL DEFAULT 'greens',
                base_color TEXT NOT NULL DEFAULT '#68c282',
                opacity DOUBLE PRECISION NOT NULL DEFAULT 1.0,
                feature_count INTEGER NOT NULL DEFAULT 0,
                bbox_json TEXT NOT NULL DEFAULT '[]',
                metadata_json TEXT NOT NULL DEFAULT '{}',
                sort_order INTEGER NOT NULL DEFAULT 0,
                published_at TEXT NOT NULL DEFAULT '',
                created_by TEXT NOT NULL DEFAULT 'admin',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        safe("CREATE INDEX IF NOT EXISTS idx_three_d_layers_status ON three_d_layers(status)")
        safe("CREATE INDEX IF NOT EXISTS idx_three_d_layers_sort ON three_d_layers(sort_order, updated_at)")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS terrain_layers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                source_path TEXT NOT NULL DEFAULT '',
                cropped_path TEXT NOT NULL DEFAULT '',
                tile_url_template TEXT NOT NULL DEFAULT '',
                bounds_json TEXT NOT NULL DEFAULT '[]',
                min_height DOUBLE PRECISION NOT NULL DEFAULT 0,
                max_height DOUBLE PRECISION NOT NULL DEFAULT 0,
                width INTEGER NOT NULL DEFAULT 0,
                height INTEGER NOT NULL DEFAULT 0,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                sort_order INTEGER NOT NULL DEFAULT 0,
                published_at TEXT NOT NULL DEFAULT '',
                created_by TEXT NOT NULL DEFAULT 'admin',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
        """)
        safe("CREATE INDEX IF NOT EXISTS idx_terrain_layers_status ON terrain_layers(status)")
        safe("CREATE INDEX IF NOT EXISTS idx_terrain_layers_sort ON terrain_layers(sort_order, updated_at)")

        cur.execute("""
            CREATE TABLE IF NOT EXISTS geodata_processing_jobs (
                job_id TEXT PRIMARY KEY,
                job_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'queued',
                phase TEXT NOT NULL DEFAULT 'queued',
                progress DOUBLE PRECISION NOT NULL DEFAULT 0,
                message TEXT NOT NULL DEFAULT '',
                layer_id TEXT NOT NULL DEFAULT '',
                dataset_id TEXT NOT NULL DEFAULT '',
                result_json TEXT NOT NULL DEFAULT '{}',
                error TEXT NOT NULL DEFAULT '',
                cancel_requested INTEGER NOT NULL DEFAULT 0,
                created_by TEXT NOT NULL DEFAULT 'admin',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                finished_at TEXT NOT NULL DEFAULT ''
            )
        """)
        safe("CREATE INDEX IF NOT EXISTS idx_geodata_jobs_status ON geodata_processing_jobs(status, updated_at)")
        safe("CREATE INDEX IF NOT EXISTS idx_geodata_jobs_layer ON geodata_processing_jobs(layer_id)")

        raw.commit()
        logger.info("PostgreSQL 数据库初始化完成")
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()
