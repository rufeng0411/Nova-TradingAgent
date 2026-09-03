"""Database configuration and session management."""

import logging
import os
from datetime import datetime, timezone
from typing import Generator

from sqlalchemy import (
    Boolean,
    BigInteger,
    DECIMAL,
    Date,
    create_engine,
    Column,
    String,
    DateTime,
    Text,
    Integer,
    Float,
    JSON,
    UniqueConstraint,
    event,
    text,
    Index,
    inspect,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# Database URL - default to SQLite for simplicity
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tradingagents.db")
MARKETDATA_DATABASE_URL = (os.getenv("MARKETDATA_DATABASE_URL") or "").strip() or DATABASE_URL


def _int_env(name: str, default: int, *, min_v: int = 1, max_v: int = 200) -> int:
    """Parse bounded int from env; invalid or empty falls back to default."""
    raw = (os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        v = int(raw, 10)
    except ValueError:
        return default
    return max(min_v, min(max_v, v))


# SQLAlchemy pool for non-SQLite engines (MySQL / Postgres). Tune via env; keep total
# connections (pool_size + max_overflow) below MySQL max_connections minus headroom.
_DEFAULT_DB_POOL_SIZE = 40
_DEFAULT_DB_MAX_OVERFLOW = 30
_DEFAULT_DB_POOL_TIMEOUT = 60

_DB_POOL_SIZE = _int_env("TA_DB_POOL_SIZE", _DEFAULT_DB_POOL_SIZE, min_v=1, max_v=200)
_DB_MAX_OVERFLOW = _int_env("TA_DB_MAX_OVERFLOW", _DEFAULT_DB_MAX_OVERFLOW, min_v=0, max_v=200)
_DB_POOL_TIMEOUT = _int_env("TA_DB_POOL_TIMEOUT", _DEFAULT_DB_POOL_TIMEOUT, min_v=5, max_v=600)

_MD_POOL_SIZE = _int_env(
    "TA_MARKETDATA_DB_POOL_SIZE",
    _DB_POOL_SIZE,
    min_v=1,
    max_v=200,
)
_MD_MAX_OVERFLOW = _int_env(
    "TA_MARKETDATA_DB_MAX_OVERFLOW",
    _DB_MAX_OVERFLOW,
    min_v=0,
    max_v=200,
)
_MD_POOL_TIMEOUT = _int_env(
    "TA_MARKETDATA_DB_POOL_TIMEOUT",
    _DB_POOL_TIMEOUT,
    min_v=5,
    max_v=600,
)


def _sqlalchemy_connect_args(url: str) -> dict:
    """Per-dialect connect_args. MySQL+pymysql: bounded connect timeout to avoid startup hanging forever."""
    if not url or url.startswith("sqlite"):
        return {}
    u = url.lower()
    if "+pymysql" in u or ("mysql" in u and "pymysql" in u):
        return {"connect_timeout": 25}
    return {}


# Create engine
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False,
        pool_size=10,
        max_overflow=20,
        pool_timeout=60,
        pool_recycle=3600,
    )

    def _can_use_wal() -> bool:
        """Check if WAL mode is safe: db's parent dir must be writable for -shm/-wal files."""
        import pathlib
        db_path = DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
        parent = pathlib.Path(db_path).resolve().parent
        return os.access(parent, os.W_OK)

    _use_wal = _can_use_wal()

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        if _use_wal:
            cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()
else:
    # For PostgreSQL/MySQL, pool sizing is env-driven (see TA_DB_*).
    engine = create_engine(
        DATABASE_URL,
        echo=False,
        connect_args=_sqlalchemy_connect_args(DATABASE_URL),
        pool_pre_ping=True,
        pool_size=_DB_POOL_SIZE,
        max_overflow=_DB_MAX_OVERFLOW,
        pool_timeout=_DB_POOL_TIMEOUT,
        pool_recycle=3600,
    )

# Marketdata engine - defaults to business DB when not configured separately.
if MARKETDATA_DATABASE_URL == DATABASE_URL:
    marketdata_engine = engine
elif MARKETDATA_DATABASE_URL.startswith("sqlite"):
    marketdata_engine = create_engine(
        MARKETDATA_DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False,
        pool_size=10,
        max_overflow=20,
        pool_timeout=60,
        pool_recycle=3600,
    )
else:
    marketdata_engine = create_engine(
        MARKETDATA_DATABASE_URL,
        echo=False,
        connect_args=_sqlalchemy_connect_args(MARKETDATA_DATABASE_URL),
        pool_pre_ping=True,
        pool_size=_MD_POOL_SIZE,
        max_overflow=_MD_MAX_OVERFLOW,
        pool_timeout=_MD_POOL_TIMEOUT,
        pool_recycle=3600,
    )

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
MarketdataSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=marketdata_engine)

# Base class for models
Base = declarative_base()
MarketdataBase = declarative_base()
logger = logging.getLogger(__name__)
MARKETDATA_DB_HEALTHY = False
MARKETDATA_JSON = JSON().with_variant(JSONB, "postgresql")


def get_db() -> Generator[Session, None, None]:
    """Get database session (for FastAPI Depends)."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class get_db_ctx:
    """Context manager for manual DB session usage.

    Usage:
        with get_db_ctx() as db:
            db.query(...)
    """

    def __init__(self) -> None:
        self.db: Session | None = None

    def __enter__(self) -> Session:
        self.db = SessionLocal()
        return self.db

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.db is not None:
            if exc_type is not None:
                self.db.rollback()
            self.db.close()


class get_marketdata_db_ctx:
    """Context manager for marketdata DB session usage."""

    def __init__(self) -> None:
        self.db: Session | None = None

    def __enter__(self) -> Session:
        self.db = MarketdataSessionLocal()
        return self.db

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.db is not None:
            if exc_type is not None:
                self.db.rollback()
            self.db.close()


def is_marketdata_db_healthy() -> bool:
    return MARKETDATA_DB_HEALTHY


def init_db() -> None:
    """Initialize database tables."""
    global MARKETDATA_DB_HEALTHY
    Base.metadata.create_all(bind=engine)
    _ensure_report_schema()
    _ensure_user_schema()
    _ensure_system_legacy_user_and_reports()
    _ensure_admin_extensions_schema()
    _ensure_analysis_job_schema()
    _ensure_fast_analysis_schema()
    _ensure_report_outcome_schema()
    _ensure_llm_provider_config_schema()
    _ensure_trading_memory_log_schema()
    _ensure_qlib_eval_schema()
    try:
        MarketdataBase.metadata.create_all(bind=marketdata_engine)
        _ensure_marketdata_schema()
        MARKETDATA_DB_HEALTHY = True
    except Exception as e:
        logger.warning(
            "[init_db] marketdata create_all failed, fallback to vendor network path: %s",
            e,
        )
        MARKETDATA_DB_HEALTHY = False


def _ensure_analysis_job_schema() -> None:
    """Indexes for analysis job/event tables (SQLite create_all may omit some)."""
    if not DATABASE_URL.startswith("sqlite"):
        return
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_job_events_job_id_seq ON job_events(job_id, seq)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_analysis_jobs_status_lease ON analysis_jobs(status, lease_until)"
                )
            )
    except Exception as e:
        logger.warning("ensure_analysis_job_schema: %s", e)


def _ensure_fast_analysis_schema() -> None:
    """Indexes for fast analysis tables."""
    try:
        with engine.begin() as conn:
            dialect = engine.dialect.name
            if dialect == "sqlite":
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_fast_analyses_user_created "
                        "ON fast_analyses(user_id, created_at)"
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_fast_analyses_symbol_trade_date "
                        "ON fast_analyses(symbol, trade_date)"
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_fast_analyses_user_symbol_created "
                        "ON fast_analyses(user_id, symbol, created_at)"
                    )
                )
            else:
                for sql in (
                    "CREATE INDEX ix_fast_analyses_user_created ON fast_analyses(user_id, created_at)",
                    "CREATE INDEX ix_fast_analyses_symbol_trade_date ON fast_analyses(symbol, trade_date)",
                    "CREATE INDEX ix_fast_analyses_user_symbol_created ON fast_analyses(user_id, symbol, created_at)",
                ):
                    try:
                        conn.execute(text(sql))
                    except Exception:
                        pass
    except Exception as e:
        logger.warning("ensure_fast_analysis_schema: %s", e)


def _ensure_report_outcome_schema() -> None:
    """Indexes for report outcome table."""
    try:
        with engine.begin() as conn:
            dialect = engine.dialect.name
            if dialect == "sqlite":
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_report_outcomes_user_created "
                        "ON report_outcomes(user_id, created_at)"
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_report_outcomes_kind_release "
                        "ON report_outcomes(task_kind, release_version)"
                    )
                )
            else:
                try:
                    conn.execute(
                        text(
                            "CREATE INDEX ix_report_outcomes_user_created "
                            "ON report_outcomes(user_id, created_at)"
                        )
                    )
                except Exception:
                    pass
                try:
                    conn.execute(
                        text(
                            "CREATE INDEX ix_report_outcomes_kind_release "
                            "ON report_outcomes(task_kind, release_version)"
                        )
                    )
                except Exception:
                    pass
    except Exception as e:
        logger.warning("ensure_report_outcome_schema: %s", e)


def _ensure_admin_extensions_schema() -> None:
    """SQLite: composite indexes + any post-create_all DDL."""
    if not DATABASE_URL.startswith("sqlite"):
        return
    try:
        with engine.begin() as conn:
            conn.execute(
                text("CREATE INDEX IF NOT EXISTS ix_access_logs_path_created ON access_logs(path, created_at)")
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_credit_tx_type_created ON credit_transactions(type, created_at)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_subscriptions_created ON subscriptions(created_at)"
                )
            )
    except Exception as e:
        logger.warning("ensure_admin_extensions_schema: %s", e)


def _ensure_report_schema() -> None:
    """Add lightweight columns for existing deployments without migrations."""
    try:
        with engine.begin() as conn:
            dialect = engine.dialect.name
            if dialect == "sqlite":
                columns = {row[1] for row in conn.execute(text("PRAGMA table_info(reports)"))}
            else:
                columns = {col["name"] for col in inspect(conn).get_columns("reports")}

            def _add_text_column(name: str) -> None:
                conn.execute(text(f"ALTER TABLE reports ADD COLUMN {name} TEXT"))

            def _add_varchar_column(name: str, size: int, default: str | None = None) -> None:
                if default is None:
                    conn.execute(text(f"ALTER TABLE reports ADD COLUMN {name} VARCHAR({size})"))
                else:
                    conn.execute(
                        text(
                            f"ALTER TABLE reports ADD COLUMN {name} VARCHAR({size}) "
                            f"DEFAULT '{default}'"
                        )
                    )

            def _add_json_column(name: str) -> None:
                if dialect == "sqlite":
                    conn.execute(text(f"ALTER TABLE reports ADD COLUMN {name} TEXT"))
                elif dialect == "postgresql":
                    conn.execute(text(f"ALTER TABLE reports ADD COLUMN {name} JSONB"))
                else:
                    conn.execute(text(f"ALTER TABLE reports ADD COLUMN {name} JSON NULL"))

            if "direction" not in columns:
                _add_varchar_column("direction", 50)
            if "status" not in columns:
                _add_varchar_column("status", 20, "completed")
            if "error" not in columns:
                _add_text_column("error")
            if "analyst_traces" not in columns:
                _add_json_column("analyst_traces")
            if "macro_report" not in columns:
                _add_text_column("macro_report")
            if "smart_money_report" not in columns:
                _add_text_column("smart_money_report")
            if "game_theory_report" not in columns:
                _add_text_column("game_theory_report")
            if "volume_price_report" not in columns:
                _add_text_column("volume_price_report")
            if "data_sources_json" not in columns:
                _add_json_column("data_sources_json")
            if "final_decision_summary" not in columns:
                _add_text_column("final_decision_summary")
            if "release_version" not in columns:
                _add_varchar_column("release_version", 40)
            if "rating_5tier" not in columns:
                _add_varchar_column("rating_5tier", 16)
            if dialect == "sqlite":
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_reports_user_created "
                        "ON reports(user_id, created_at)"
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_reports_user_symbol_created "
                        "ON reports(user_id, symbol, created_at)"
                    )
                )
            else:
                try:
                    conn.execute(
                        text(
                            "CREATE INDEX ix_reports_user_created "
                            "ON reports(user_id, created_at)"
                        )
                    )
                except Exception:
                    pass
                try:
                    conn.execute(
                        text(
                            "CREATE INDEX ix_reports_user_symbol_created "
                            "ON reports(user_id, symbol, created_at)"
                        )
                    )
                except Exception:
                    pass
    except Exception as e:
        logger.error("Failed to ensure report schema: %s", e)


def _ensure_llm_provider_config_schema() -> None:
    """Ensure llm_provider_config table exists via create_all; indexes for lookups."""
    try:
        with engine.begin() as conn:
            dialect = engine.dialect.name
            if dialect == "sqlite":
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_llm_provider_config_user "
                        "ON llm_provider_config(user_id, provider, region)"
                    )
                )
            else:
                try:
                    conn.execute(
                        text(
                            "CREATE INDEX ix_llm_provider_config_user "
                            "ON llm_provider_config(user_id, provider, region)"
                        )
                    )
                except Exception:
                    pass
    except Exception as e:
        logger.warning("ensure_llm_provider_config_schema: %s", e)


def _ensure_trading_memory_log_schema() -> None:
    """Indexes for trading_memory_log two-phase queries."""
    try:
        with engine.begin() as conn:
            dialect = engine.dialect.name
            if dialect == "sqlite":
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_trading_memory_log_user_ticker "
                        "ON trading_memory_log(user_id, ticker, trade_date)"
                    )
                )
            else:
                try:
                    conn.execute(
                        text(
                            "CREATE INDEX ix_trading_memory_log_user_ticker "
                            "ON trading_memory_log(user_id, ticker, trade_date)"
                        )
                    )
                except Exception:
                    pass
    except Exception as e:
        logger.warning("ensure_trading_memory_log_schema: %s", e)


def _ensure_qlib_eval_schema() -> None:
    """Indexes for qlib evaluation tables."""
    try:
        with engine.begin() as conn:
            dialect = engine.dialect.name
            if dialect == "sqlite":
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_qlib_eval_runs_type_created "
                        "ON qlib_eval_runs(run_type, created_at)"
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_qlib_eval_metrics_release_kind "
                        "ON qlib_eval_metrics(release_version, metric_kind)"
                    )
                )
            else:
                for sql in (
                    "CREATE INDEX ix_qlib_eval_runs_type_created ON qlib_eval_runs(run_type, created_at)",
                    "CREATE INDEX ix_qlib_eval_metrics_release_kind ON qlib_eval_metrics(release_version, metric_kind)",
                ):
                    try:
                        conn.execute(text(sql))
                    except Exception:
                        pass
    except Exception as e:
        logger.warning("ensure_qlib_eval_schema: %s", e)


def _ensure_user_schema() -> None:
    """Add columns to users table for existing SQLite deployments without migrations."""
    if DATABASE_URL.startswith("sqlite"):
        try:
            with engine.begin() as conn:
                columns = {row[1] for row in conn.execute(text("PRAGMA table_info(users)"))}
                if "last_login_ip" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN last_login_ip VARCHAR(45)"))
                if "email_report_enabled" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN email_report_enabled BOOLEAN NOT NULL DEFAULT 1"))
                if "wecom_report_enabled" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN wecom_report_enabled BOOLEAN NOT NULL DEFAULT 1"))
                llm_columns = {row[1] for row in conn.execute(text("PRAGMA table_info(user_llm_configs)"))}
                if "wecom_webhook_encrypted" not in llm_columns:
                    conn.execute(text("ALTER TABLE user_llm_configs ADD COLUMN wecom_webhook_encrypted TEXT"))
                if "default_analysts" not in llm_columns:
                    conn.execute(text("ALTER TABLE user_llm_configs ADD COLUMN default_analysts TEXT"))
                if "username" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN username VARCHAR(50)"))
                if "password_hash" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255)"))
                if "phone_encrypted" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN phone_encrypted TEXT"))
                if "display_name" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN display_name VARCHAR(100)"))
                if "role" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'user'"))
                if "status" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active'"))
                if "credits" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN credits INTEGER NOT NULL DEFAULT 0"))
                if "total_credits_consumed" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN total_credits_consumed INTEGER NOT NULL DEFAULT 0"))
                if "current_subscription_id" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN current_subscription_id VARCHAR(36)"))
                if "admin_permissions" not in columns:
                    conn.execute(text("ALTER TABLE users ADD COLUMN admin_permissions TEXT"))
        except Exception as e:
            logger.error("Failed to ensure user schema: %s", e)

    _migrate_tokens_to_hashed()
    _migrate_api_keys_reencrypt()


def _ensure_marketdata_schema() -> None:
    """Best-effort marketdata additive DDL for evolving columns/indexes."""
    if marketdata_engine.dialect.name == "sqlite":
        return
    try:
        with marketdata_engine.begin() as conn:
            dialect = marketdata_engine.dialect.name
            existing_tables = set(inspect(conn).get_table_names())
            if "marketdata_stk_factor_pro" in existing_tables:
                columns = {col["name"] for col in inspect(conn).get_columns("marketdata_stk_factor_pro")}
                pending_cols: list[tuple[str, str]] = [
                    ("fd_amount", "DECIMAL(20,4)"),
                    ("main_net_flow", "DECIMAL(20,4)"),
                    ("limit_up_days", "INTEGER"),
                    ("limit_up_height", "INTEGER"),
                    ("bid1_vol", "DECIMAL(20,4)"),
                    ("ask1_vol", "DECIMAL(20,4)"),
                ]
                for col_name, ddl in pending_cols:
                    if col_name in columns:
                        continue
                    conn.execute(
                        text(
                            f"ALTER TABLE marketdata_stk_factor_pro "
                            f"ADD COLUMN {col_name} {ddl}"
                        )
                    )
            if dialect == "postgresql" and "marketdata_stk_factor_pro" in existing_tables:
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_marketdata_stk_factor_pro_trade_date_main_flow "
                        "ON marketdata_stk_factor_pro(trade_date, main_net_flow DESC)"
                    )
                )
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_marketdata_stk_factor_pro_trade_date_fd_amount "
                        "ON marketdata_stk_factor_pro(trade_date, fd_amount DESC)"
                    )
                )
    except Exception as e:
        logger.warning("ensure_marketdata_schema: %s", e)


def _migrate_tokens_to_hashed() -> None:
    """Migrate plaintext API tokens to HMAC-SHA256 hashed storage."""
    import hashlib, hmac
    try:
        with engine.begin() as conn:
            # Add token_hint column if missing (SQLite only, MySQL handles via create_all)
            if DATABASE_URL.startswith("sqlite"):
                token_cols = {row[1] for row in conn.execute(text("PRAGMA table_info(user_tokens)"))}
                if "token_hint" not in token_cols:
                    conn.execute(text("ALTER TABLE user_tokens ADD COLUMN token_hint VARCHAR(8)"))

            # Detect un-migrated rows: plaintext tokens start with "ta-sk-"
            rows = conn.execute(text("SELECT id, token FROM user_tokens WHERE token LIKE 'ta-sk-%'")).fetchall()
            if not rows:
                return
            from api.services.auth_service import _secret_key
            key = _secret_key().encode("utf-8")
            for row_id, plaintext in rows:
                token_hash = hmac.new(key, plaintext.encode("utf-8"), hashlib.sha256).hexdigest()
                hint = plaintext[-4:]
                conn.execute(
                    text("UPDATE user_tokens SET token = :hash, token_hint = :hint WHERE id = :id"),
                    {"hash": token_hash, "hint": hint, "id": row_id},
                )
            logger.info("[security] Migrated %s API tokens from plaintext to hashed storage.", len(rows))
    except Exception as e:
        logger.error("Token hash migration failed: %s", e)


def _migrate_api_keys_reencrypt() -> None:
    """Re-encrypt user secrets when TA_APP_SECRET_KEY changes.

    On startup, if a custom secret is configured, tries to decrypt each secret
    with the current secret. If that fails, tries the default secret (old data).
    If the default key works, re-encrypts with the current key and writes back.
    """
    from api.services.auth_service import (
        is_custom_secret_configured, decrypt_secret,
        decrypt_secret_with_fallback, encrypt_secret,
    )
    if not is_custom_secret_configured():
        return
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT user_id, api_key_encrypted, wecom_webhook_encrypted
                    FROM user_llm_configs
                    WHERE api_key_encrypted IS NOT NULL OR wecom_webhook_encrypted IS NOT NULL
                    """
                )
            ).fetchall()
            if not rows:
                return
            # Quick check: if the first row decrypts fine, likely all are OK already.
            _, first_api_key, first_wecom_webhook = rows[0]
            first_secret = first_api_key or first_wecom_webhook
            if first_secret and decrypt_secret(first_secret) is not None and len(rows) < 50:
                # Small dataset, still verify all — but for large sets, skip if first is OK
                pass
            migrated = 0
            for user_id, encrypted_api_key, encrypted_wecom_webhook in rows:
                for column_name, encrypted_value in (
                    ("api_key_encrypted", encrypted_api_key),
                    ("wecom_webhook_encrypted", encrypted_wecom_webhook),
                ):
                    if not encrypted_value:
                        continue
                    if decrypt_secret(encrypted_value) is not None:
                        continue
                    plaintext = decrypt_secret_with_fallback(encrypted_value)
                    if plaintext is None:
                        logger.warning(
                            "[security] Cannot decrypt %s for user %s with any known key. Skipping.",
                            column_name,
                            user_id,
                        )
                        continue
                    new_encrypted = encrypt_secret(plaintext)
                    if column_name == "api_key_encrypted":
                        conn.execute(
                            text("UPDATE user_llm_configs SET api_key_encrypted = :enc WHERE user_id = :uid"),
                            {"enc": new_encrypted, "uid": user_id},
                        )
                    elif column_name == "wecom_webhook_encrypted":
                        conn.execute(
                            text("UPDATE user_llm_configs SET wecom_webhook_encrypted = :enc WHERE user_id = :uid"),
                            {"enc": new_encrypted, "uid": user_id},
                        )
                    migrated += 1
            if migrated:
                logger.info("[security] Re-encrypted %s user secret(s) with new TA_APP_SECRET_KEY.", migrated)
    except Exception as e:
        logger.error("User secret re-encryption migration failed: %s", e)


# Internal user id for rows created before multi-tenant user_id was enforced
SYSTEM_LEGACY_USER_ID = "00000000-0000-4000-8000-000000000001"
SYSTEM_LEGACY_USER_EMAIL = "system-legacy@internal.local"


def _ensure_system_legacy_user_and_reports() -> None:
    """Create placeholder user and attach orphan reports (user_id NULL) for isolation."""
    try:
        with get_db_ctx() as db:
            u = db.query(UserDB).filter(UserDB.id == SYSTEM_LEGACY_USER_ID).first()
            if not u:
                now = datetime.now(timezone.utc)
                bogus_hash = "$2b$12$" + "0" * 53  # not a valid bcrypt login hash
                db.add(
                    UserDB(
                        id=SYSTEM_LEGACY_USER_ID,
                        email=SYSTEM_LEGACY_USER_EMAIL,
                        username="system_legacy",
                        password_hash=bogus_hash,
                        is_active=False,
                        role="system",
                        status="inactive",
                        credits=0,
                        total_credits_consumed=0,
                        created_at=now,
                        updated_at=now,
                    )
                )
                db.commit()
            n = (
                db.query(ReportDB)
                .filter(ReportDB.user_id.is_(None))
                .update({ReportDB.user_id: SYSTEM_LEGACY_USER_ID}, synchronize_session=False)
            )
            if n:
                db.commit()
                logger.info("[schema] Assigned %s orphan reports to system legacy user.", n)
    except Exception as e:
        logger.error("Failed system legacy user / report migration: %s", e)


# Report Model
class ReportDB(Base):
    """Report database model."""
    
    __tablename__ = "reports"
    __table_args__ = (
        Index("ix_reports_user_created", "user_id", "created_at"),
        Index("ix_reports_user_symbol_created", "user_id", "symbol", "created_at"),
    )
    
    id = Column(String(36), primary_key=True, index=True)
    user_id = Column(String(64), index=True, nullable=True)  # For future multi-user support
    symbol = Column(String(20), index=True, nullable=False)
    trade_date = Column(String(20), nullable=False)
    
    # Task lifecycle info
    status = Column(String(20), default="completed", index=True)  # pending, running, completed, failed
    error = Column(Text, nullable=True)
    
    # Decision info
    decision = Column(String(50), nullable=True)  # BUY, SELL, HOLD, etc.
    direction = Column(String(50), nullable=True)  # 看多、偏多、中性、偏空、看空
    confidence = Column(Integer, nullable=True)  # 0-100
    target_price = Column(Float, nullable=True)
    stop_loss_price = Column(Float, nullable=True)
    
    # Analysis price info
    analysis_price = Column(Float, nullable=True)
    analysis_price_time = Column(String(20), nullable=True) # e.g., "2026-05-06 13:55"
    
    # Full analysis results stored as JSON
    result_data = Column(JSON, nullable=True)
    data_sources_json = Column(JSON, nullable=True)

    # LLM-extracted structured data
    risk_items = Column(JSON, nullable=True)   # [{"name": "...", "level": "high|medium|low", "description": "..."}]
    key_metrics = Column(JSON, nullable=True)  # [{"name": "...", "value": "...", "status": "good|neutral|bad"}]
    analyst_traces = Column(JSON, nullable=True) # [{"agent": "...", "verdict": "...", "key_finding": "..."}]

    # Individual reports (for quick access)
    market_report = Column(Text, nullable=True)
    sentiment_report = Column(Text, nullable=True)
    news_report = Column(Text, nullable=True)
    fundamentals_report = Column(Text, nullable=True)
    macro_report = Column(Text, nullable=True)
    smart_money_report = Column(Text, nullable=True)
    volume_price_report = Column(Text, nullable=True)
    game_theory_report = Column(Text, nullable=True)
    investment_plan = Column(Text, nullable=True)
    trader_investment_plan = Column(Text, nullable=True)
    final_trade_decision = Column(Text, nullable=True)
    # LLM 生成的「要点梳理」短摘要（约 300–400 字）；完整结论见 final_trade_decision
    final_decision_summary = Column(Text, nullable=True)
    release_version = Column(String(40), nullable=True)
    rating_5tier = Column(String(16), nullable=True)

    # Metadata
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    @property
    def data_sources(self):
        return self.data_sources_json
    
    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "symbol": self.symbol,
            "trade_date": self.trade_date,
            "decision": self.decision,
            "direction": self.direction,
            "confidence": self.confidence,
            "target_price": self.target_price,
            "stop_loss_price": self.stop_loss_price,
            "analysis_price": self.analysis_price,
            "analysis_price_time": self.analysis_price_time,
            "result_data": self.result_data,
            "data_sources_json": self.data_sources_json,
            "risk_items": self.risk_items,
            "key_metrics": self.key_metrics,
            "analyst_traces": self.analyst_traces,
            "market_report": self.market_report,
            "sentiment_report": self.sentiment_report,
            "news_report": self.news_report,
            "fundamentals_report": self.fundamentals_report,
            "macro_report": self.macro_report,
            "smart_money_report": self.smart_money_report,
            "volume_price_report": self.volume_price_report,
            "game_theory_report": self.game_theory_report,
            "investment_plan": self.investment_plan,
            "trader_investment_plan": self.trader_investment_plan,
            "final_trade_decision": self.final_trade_decision,
            "final_decision_summary": self.final_decision_summary,
            "release_version": self.release_version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class ReportOutcomeDB(Base):
    """Per-report accuracy outcomes across time horizons."""

    __tablename__ = "report_outcomes"

    id = Column(String(36), primary_key=True, index=True)  # same as reports.id
    user_id = Column(String(64), index=True, nullable=False)
    task_kind = Column(String(40), nullable=False, default="full_analysis", index=True)
    symbol = Column(String(20), index=True, nullable=False)
    trade_date = Column(String(20), nullable=False)
    release_version = Column(String(40), nullable=False, default="dev")

    baseline_price = Column(Float, nullable=True)
    baseline_source = Column(String(24), nullable=True)
    atr20 = Column(Float, nullable=True)
    atr_window_end = Column(String(20), nullable=True)

    outcomes_json = Column(JSON, nullable=True)  # {t1:{...}, t3:{...}}
    weighted_score = Column(Float, nullable=True)
    settled_count = Column(Integer, nullable=False, default=0)
    total_windows = Column(Integer, nullable=False, default=0)
    primary_horizon = Column(String(8), nullable=True)
    primary_status = Column(String(16), nullable=True)

    last_evaluated_at = Column(DateTime(timezone=True), nullable=True)
    next_evaluate_after = Column(DateTime(timezone=True), nullable=True, index=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_report_outcomes_user_created", "user_id", "created_at"),
        Index("ix_report_outcomes_kind_release", "task_kind", "release_version"),
    )


class QlibEvalRunDB(Base):
    """Quant evaluation sandbox run metadata (not on default analysis chain)."""

    __tablename__ = "qlib_eval_runs"

    id = Column(String(36), primary_key=True, index=True)
    run_type = Column(String(32), nullable=False, default="sandbox")  # sandbox | sweep | baseline
    release_version = Column(String(40), nullable=False, default="dev", index=True)
    status = Column(String(24), nullable=False, default="pending")
    panel_rows = Column(Integer, nullable=True)
    manifest_json = Column(JSON, nullable=True)
    result_json = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    created_by = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_qlib_eval_runs_type_created", "run_type", "created_at"),
    )


class QlibEvalMetricsDB(Base):
    """Aggregated IC / hit-rate / gate metrics per run and release version."""

    __tablename__ = "qlib_eval_metrics"

    id = Column(String(36), primary_key=True, index=True)
    run_id = Column(String(36), index=True, nullable=False)
    release_version = Column(String(40), nullable=False, default="dev", index=True)
    metric_kind = Column(String(32), nullable=False, default="baseline")  # baseline | sweep | gate
    label_horizon = Column(String(8), nullable=True)
    ic = Column(Float, nullable=True)
    rank_ic = Column(Float, nullable=True)
    hit_rate_pct = Column(Float, nullable=True)
    coverage_pct = Column(Float, nullable=True)
    gate_passed = Column(Boolean, nullable=False, default=False)
    details_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_qlib_eval_metrics_release_kind", "release_version", "metric_kind"),
    )


class AnalysisJobDB(Base):
    """Durable analysis job metadata for resume after API restart."""

    __tablename__ = "analysis_jobs"

    id = Column(String(64), primary_key=True, index=True)
    user_id = Column(String(64), index=True, nullable=True)
    status = Column(String(32), nullable=False, default="pending", index=True)
    request_payload = Column(JSON, nullable=True)
    resume_state = Column(JSON, nullable=True)
    lease_until = Column(DateTime(timezone=True), nullable=True, index=True)
    lease_owner = Column(String(64), nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    last_event_seq = Column(Integer, nullable=False, default=0)
    symbol = Column(String(32), nullable=True)
    trade_date = Column(String(16), nullable=True)
    error = Column(Text, nullable=True)
    request_source = Column(String(64), nullable=True)
    decision = Column(String(64), nullable=True)
    dry_run = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class FastAnalysisDB(Base):
    """Fast-analysis 2-minute snapshot result."""

    __tablename__ = "fast_analyses"

    id = Column(String(36), primary_key=True, index=True)
    user_id = Column(String(64), index=True, nullable=False)
    symbol = Column(String(32), index=True, nullable=False)
    symbol_name = Column(String(120), nullable=True)
    trade_date = Column(String(16), nullable=False, index=True)
    job_id = Column(String(64), nullable=True, index=True)
    status = Column(String(24), nullable=False, default="running", index=True)
    triggered_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    finished_at = Column(DateTime(timezone=True), nullable=True)
    elapsed_ms = Column(Integer, nullable=True)
    model_provider = Column(String(64), nullable=True)
    model_name = Column(String(128), nullable=True)
    prompt_tokens = Column(Integer, nullable=True)
    completion_tokens = Column(Integer, nullable=True)
    cost_credit_points = Column(Integer, nullable=True)
    request_context_json = Column(JSON, nullable=True)
    snapshot_json = Column(JSON, nullable=True)
    features_json = Column(JSON, nullable=True)
    kline_features_json = Column(JSON, nullable=True)
    verdict_json = Column(JSON, nullable=True)
    time_phased_json = Column(JSON, nullable=True)
    position_advice_json = Column(JSON, nullable=True)
    executability_json = Column(JSON, nullable=True)
    kline_insight_json = Column(JSON, nullable=True)
    overnight_context_id = Column(String(64), nullable=True)
    disclaimer_version = Column(String(32), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_fast_analyses_user_created", "user_id", "created_at"),
        Index("ix_fast_analyses_symbol_trade_date", "symbol", "trade_date"),
        # 覆盖 /v1/fast-analyses/recent?symbol=... 的 (user_id, symbol, created_at DESC) 路径，
        # 让两阶段查询的 id 检索直接走索引顺序，避免 MySQL filesort + 大 JSON 列触发 1038。
        Index("ix_fast_analyses_user_symbol_created", "user_id", "symbol", "created_at"),
    )


class UserTaskQueueDB(Base):
    """Per-user queued heavy analysis tasks (not-yet-dispatched only)."""

    __tablename__ = "user_task_queue"

    id = Column(String(36), primary_key=True, index=True)
    user_id = Column(String(64), nullable=False, index=True)
    job_id = Column(String(64), nullable=False, unique=True, index=True)
    task_kind = Column(String(40), nullable=False, default="full_analysis")
    queue_status = Column(String(20), nullable=False, default="queued")  # queued | paused
    sort_order = Column(Integer, nullable=False, default=0)
    title = Column(String(200), nullable=True)
    description = Column(Text, nullable=True)
    symbol = Column(String(32), nullable=True)
    trade_date = Column(String(16), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_user_task_queue_user_sort", "user_id", "sort_order"),
        Index("ix_user_task_queue_user_status", "user_id", "queue_status"),
    )


class JobEventDB(Base):
    """Append-only SSE event log for replay (Last-Event-ID / ?after=)."""

    __tablename__ = "job_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String(64), nullable=False, index=True)
    seq = Column(Integer, nullable=False)
    event = Column(String(128), nullable=False)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("job_id", "seq", name="uq_job_events_job_seq"),)


class UserDB(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_login_at = Column(DateTime, nullable=True)
    last_login_ip = Column(String(45), nullable=True)
    email_report_enabled = Column(Boolean, default=True, nullable=False, server_default="1")
    wecom_report_enabled = Column(Boolean, default=True, nullable=False, server_default="1")
    username = Column(String(50), unique=True, index=True, nullable=True)
    password_hash = Column(String(255), nullable=True)
    phone_encrypted = Column(Text, nullable=True)
    display_name = Column(String(100), nullable=True)
    role = Column(String(20), default="user", nullable=False, server_default="user")
    status = Column(String(20), default="active", nullable=False, server_default="active")
    credits = Column(Integer, default=0, nullable=False, server_default="0")
    total_credits_consumed = Column(Integer, default=0, nullable=False, server_default="0")
    current_subscription_id = Column(String(36), nullable=True)
    admin_permissions = Column(JSON, nullable=True)  # e.g. ["ops","finance","superadmin"]; null = all for role=admin


class EmailVerificationCodeDB(Base):
    __tablename__ = "email_verification_codes"

    id = Column(String(36), primary_key=True, index=True)
    email = Column(String(255), index=True, nullable=False)
    code_hash = Column(String(255), nullable=False)
    purpose = Column(String(50), default="login", nullable=False)
    expires_at = Column(DateTime, nullable=False)
    consumed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class LlmProviderConfigDB(Base):
    """Per-user LLM routing preferences — no api_key stored."""

    __tablename__ = "llm_provider_config"
    __table_args__ = (
        Index("ix_llm_provider_config_user", "user_id", "provider", "region"),
    )

    id = Column(String(36), primary_key=True, index=True)
    user_id = Column(String(64), index=True, nullable=False)
    provider = Column(String(50), nullable=False)
    region = Column(String(16), nullable=False, default="cn")
    deep_model = Column(String(255), nullable=True)
    quick_model = Column(String(255), nullable=True)
    custom_model_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class TradingMemoryLogDB(Base):
    """Persistent decision log for upgrade memory feature."""

    __tablename__ = "trading_memory_log"
    __table_args__ = (
        Index("ix_trading_memory_log_user_ticker", "user_id", "ticker", "trade_date"),
        Index("ix_trading_memory_log_status", "status"),
    )

    id = Column(String(36), primary_key=True, index=True)
    user_id = Column(String(64), index=True, nullable=False)
    ticker = Column(String(32), index=True, nullable=False)
    trade_date = Column(String(20), nullable=False)
    rating_5tier = Column(String(16), nullable=True)
    decision_md = Column(Text, nullable=True)
    reflection_md = Column(Text, nullable=True)
    outcome_raw_pct = Column(Float, nullable=True)
    outcome_alpha_pct = Column(Float, nullable=True)
    holding_days = Column(Integer, nullable=True)
    status = Column(String(16), nullable=False, default="pending")
    benchmark_ticker = Column(String(32), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class UserLLMConfigDB(Base):
    __tablename__ = "user_llm_configs"

    user_id = Column(String(36), primary_key=True, index=True)
    llm_provider = Column(String(50), nullable=True)
    backend_url = Column(String(500), nullable=True)
    quick_think_llm = Column(String(255), nullable=True)
    deep_think_llm = Column(String(255), nullable=True)
    max_debate_rounds = Column(Integer, nullable=True)
    max_risk_discuss_rounds = Column(Integer, nullable=True)
    api_key_encrypted = Column(Text, nullable=True)
    wecom_webhook_encrypted = Column(Text, nullable=True)
    default_analysts = Column(Text, nullable=True)  # JSON list, e.g. '["market","social",...]'
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class UserPreferenceDB(Base):
    __tablename__ = "user_preferences"

    user_id = Column(String(36), primary_key=True, index=True)
    risk_profile = Column(String(20), nullable=False, default="balanced", server_default="balanced")
    fast_model = Column(String(128), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class UserTokenDB(Base):
    __tablename__ = "user_tokens"

    id = Column(String(36), primary_key=True, index=True)
    user_id = Column(String(36), index=True, nullable=False)
    name = Column(String(50), nullable=False)
    token = Column(String(128), unique=True, index=True, nullable=False)
    token_hint = Column(String(8), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class VersionStatsDB(Base):
    __tablename__ = "version_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    version = Column(String(50), nullable=True)
    nonce = Column(String(64), nullable=True)
    remote_ip = Column(String(45), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class WatchlistItemDB(Base):
    """User watchlist items."""
    __tablename__ = "watchlist_items"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(64), index=True, nullable=False)
    symbol = Column(String(20), nullable=False)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint('user_id', 'symbol', name='uq_watchlist_user_symbol'),)


class ScheduledAnalysisDB(Base):
    """Scheduled daily analysis tasks."""
    __tablename__ = "scheduled_analyses"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(64), index=True, nullable=False)
    symbol = Column(String(20), nullable=False)
    horizon = Column(String(10), default="short")
    trigger_time = Column(String(5), default="20:00")
    is_active = Column(Boolean, default=True)
    last_run_date = Column(String(10), nullable=True)
    last_run_status = Column(String(10), nullable=True)
    last_report_id = Column(String(36), nullable=True)
    consecutive_failures = Column(Integer, default=0)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint('user_id', 'symbol', name='uq_scheduled_user_symbol'),)


class SponsorDB(Base):
    """Sponsor records managed by admin project."""
    __tablename__ = "sponsors"

    id = Column(String(36), primary_key=True, index=True)
    sponsor_type = Column(String(20), nullable=False, index=True)  # money | token
    name = Column(String(100), nullable=False)
    github = Column(String(100), nullable=True)
    avatar = Column(String(500), nullable=True)
    email = Column(String(255), nullable=True)
    provider = Column(String(100), nullable=True)       # token sponsor: provider name
    amount = Column(Float, nullable=True)                # admin-only, NOT exposed in public API
    date = Column(String(10), nullable=False)
    sort_order = Column(Integer, default=0)
    is_visible = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class FeedbackDB(Base):
    """User feedback / message board."""
    __tablename__ = "feedbacks"

    id = Column(String(36), primary_key=True, index=True)
    user_id = Column(String(64), index=True, nullable=False)
    user_email = Column(String(255), nullable=False)
    subject = Column(String(200), nullable=False)
    content = Column(Text, nullable=False)
    admin_reply = Column(Text, nullable=True)
    replied_at = Column(DateTime, nullable=True)
    is_read = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ImportedPortfolioPositionDB(Base):
    """Imported current holdings snapshot plus recent trade points for a symbol."""

    __tablename__ = "imported_portfolio_positions"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(64), index=True, nullable=False)
    source = Column(String(32), default="manual", nullable=False)
    symbol = Column(String(20), nullable=False)
    security_name = Column(String(80), nullable=True)
    current_position = Column(Float, nullable=True)
    available_position = Column(Float, nullable=True)
    average_cost = Column(Float, nullable=True)
    market_value = Column(Float, nullable=True)
    current_position_pct = Column(Float, nullable=True)
    trade_points_json = Column(JSON, nullable=True)
    trade_points_count = Column(Integer, default=0, nullable=False)
    latest_trade_at = Column(String(32), nullable=True)
    latest_trade_action = Column(String(16), nullable=True)
    last_imported_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        UniqueConstraint('user_id', 'source', 'symbol', name='uq_imported_portfolio_user_source_symbol'),
    )


class PlanDB(Base):
    __tablename__ = "plans"

    id = Column(String(36), primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)
    name = Column(String(200), nullable=False)
    price_cents = Column(Integer, default=0, nullable=False, server_default="0")
    currency = Column(String(10), default="CNY", nullable=False, server_default="CNY")
    period_days = Column(Integer, default=30, nullable=False, server_default="30")
    monthly_credits = Column(Integer, default=0, nullable=False, server_default="0")
    features_json = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False, server_default="1")
    sort_order = Column(Integer, default=0, nullable=False, server_default="0")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class SubscriptionDB(Base):
    __tablename__ = "subscriptions"

    id = Column(String(36), primary_key=True, index=True)
    user_id = Column(String(36), index=True, nullable=False)
    plan_id = Column(String(36), index=True, nullable=False)
    status = Column(String(30), default="pending", nullable=False, server_default="pending")
    started_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    auto_renew = Column(Boolean, default=False, nullable=False, server_default="0")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class CreditTransactionDB(Base):
    __tablename__ = "credit_transactions"

    id = Column(String(36), primary_key=True, index=True)
    user_id = Column(String(36), index=True, nullable=False)
    delta = Column(Integer, nullable=False)
    type = Column(String(40), nullable=False)
    reason = Column(String(255), nullable=True)
    ref_type = Column(String(40), nullable=True)
    ref_id = Column(String(64), nullable=True)
    balance_after = Column(Integer, nullable=False)
    operator_id = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (Index("ix_credit_tx_user_created", "user_id", "created_at"),)


class AccessLogDB(Base):
    __tablename__ = "access_logs"

    id = Column(String(36), primary_key=True, index=True)
    user_id = Column(String(64), nullable=True, index=True)
    ip = Column(String(45), nullable=True)
    method = Column(String(10), nullable=True)
    path = Column(String(512), nullable=True)
    status_code = Column(Integer, nullable=True)
    latency_ms = Column(Integer, nullable=True)
    user_agent = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_access_logs_created_at", "created_at"),
        Index("ix_access_logs_path_created", "path", "created_at"),
    )


class SystemFeatureDB(Base):
    """Runtime feature flags (DB overrides + env defaults merged in service)."""

    __tablename__ = "system_features"

    key = Column(String(80), primary_key=True)
    value_json = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_by = Column(String(36), nullable=True)


class AdminSignalDB(Base):
    """Operational signals for admin dashboard / SSE."""

    __tablename__ = "admin_signals"

    id = Column(String(36), primary_key=True, index=True)
    type = Column(String(80), nullable=False, index=True)
    severity = Column(String(20), default="info", nullable=False, index=True)
    payload_json = Column(Text, nullable=True)
    user_id = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class AdminMetricsDailyDB(Base):
    """Pre-aggregated daily metrics (optional fast path)."""

    __tablename__ = "admin_metrics_daily"
    __table_args__ = (UniqueConstraint("bucket_date", "metric_key", name="uq_admin_metrics_daily_day_key"),)

    id = Column(String(36), primary_key=True, index=True)
    bucket_date = Column(String(10), nullable=False, index=True)  # YYYY-MM-DD UTC
    metric_key = Column(String(120), nullable=False, index=True)
    value_json = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AdminExportJobDB(Base):
    __tablename__ = "admin_export_jobs"

    id = Column(String(36), primary_key=True, index=True)
    export_type = Column(String(40), nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    file_path = Column(String(512), nullable=True)
    error_message = Column(Text, nullable=True)
    created_by = Column(String(36), nullable=False, index=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime, nullable=True)
    download_token = Column(String(64), nullable=True, index=True)
    download_consumed = Column(Boolean, default=False, nullable=False, server_default="0")


class AdminIdempotencyDB(Base):
    __tablename__ = "admin_idempotency_keys"

    idempotency_key = Column(String(128), primary_key=True)
    route = Column(String(120), nullable=False)
    response_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class AdminAuditLogDB(Base):
    __tablename__ = "admin_audit_logs"

    id = Column(String(36), primary_key=True, index=True)
    admin_id = Column(String(36), index=True, nullable=False)
    action = Column(String(80), nullable=False)
    target_user_id = Column(String(64), nullable=True, index=True)
    payload_json = Column(Text, nullable=True)
    ip = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PasswordResetTokenDB(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(String(36), primary_key=True, index=True)
    user_id = Column(String(36), index=True, nullable=False)
    token_hash = Column(String(64), unique=True, index=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ip = Column(String(45), nullable=True)


class AdminConfirmTokenDB(Base):
    """Persistent admin step-up tokens (multi-worker safe)."""

    __tablename__ = "admin_confirm_tokens"

    id = Column(String(36), primary_key=True, index=True)
    token_hash = Column(String(64), unique=True, index=True, nullable=False)
    admin_id = Column(String(36), index=True, nullable=False)
    scope = Column(String(40), nullable=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    consumed_at = Column(DateTime, nullable=True)
    created_ip = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class OrderDB(Base):
    __tablename__ = "orders"

    id = Column(String(36), primary_key=True, index=True)
    order_no = Column(String(64), unique=True, index=True, nullable=False)
    user_id = Column(String(36), index=True, nullable=False)
    subject_type = Column(String(40), nullable=False)
    subject_id = Column(String(64), nullable=True)
    amount_cents = Column(Integer, nullable=False, server_default="0")
    currency = Column(String(10), default="CNY", nullable=False, server_default="CNY")
    status = Column(String(40), nullable=False, server_default="pending")
    pay_channel = Column(String(40), default="manual", nullable=False, server_default="manual")
    paid_at = Column(DateTime, nullable=True)
    refunded_cents = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class PaymentEventDB(Base):
    __tablename__ = "payment_events"

    id = Column(String(36), primary_key=True, index=True)
    order_id = Column(String(36), index=True, nullable=False)
    provider = Column(String(40), nullable=False)
    event_type = Column(String(60), nullable=False)
    provider_trade_no = Column(String(128), nullable=True, index=True)
    amount_cents = Column(Integer, nullable=False, server_default="0")
    raw_payload_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class CreditPackageDB(Base):
    __tablename__ = "credit_packages"

    id = Column(String(36), primary_key=True, index=True)
    code = Column(String(64), unique=True, index=True, nullable=False)
    name = Column(String(200), nullable=False)
    credits = Column(Integer, nullable=False, server_default="0")
    price_cents = Column(Integer, nullable=False, server_default="0")
    currency = Column(String(10), default="CNY", nullable=False, server_default="CNY")
    is_active = Column(Boolean, default=True, nullable=False, server_default="1")
    valid_days = Column(Integer, nullable=True)
    meta_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class ReconciliationRunDB(Base):
    __tablename__ = "reconciliation_runs"

    id = Column(String(36), primary_key=True, index=True)
    label = Column(String(200), nullable=False)
    status = Column(String(40), default="open", nullable=False)
    summary_json = Column(Text, nullable=True)
    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class ReconciliationItemDB(Base):
    __tablename__ = "reconciliation_items"

    id = Column(String(36), primary_key=True, index=True)
    run_id = Column(String(36), index=True, nullable=False)
    kind = Column(String(80), nullable=False)
    ref_id = Column(String(128), nullable=True)
    amount_cents = Column(Integer, nullable=True)
    note = Column(Text, nullable=True)
    status = Column(String(40), default="open", nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class UsageRecordDB(Base):
    __tablename__ = "usage_records"

    id = Column(String(36), primary_key=True, index=True)
    user_id = Column(String(36), index=True, nullable=False)
    task_id = Column(String(64), nullable=True, index=True)
    report_id = Column(String(64), nullable=True, index=True)
    credits_reserved = Column(Integer, nullable=False, server_default="0")
    credits_consumed = Column(Integer, nullable=False, server_default="0")
    tokens_prompt = Column(Integer, nullable=False, server_default="0")
    tokens_completion = Column(Integer, nullable=False, server_default="0")
    cost_cents_estimated = Column(Integer, nullable=False, server_default="0")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class AiCallLogDB(Base):
    __tablename__ = "ai_call_logs"

    id = Column(String(36), primary_key=True, index=True)
    user_id = Column(String(36), index=True, nullable=True)
    task_id = Column(String(64), nullable=True, index=True)
    provider = Column(String(80), nullable=False)
    model = Column(String(120), nullable=False)
    purpose = Column(String(80), nullable=True)
    prompt_tokens = Column(Integer, nullable=False, server_default="0")
    completion_tokens = Column(Integer, nullable=False, server_default="0")
    latency_ms = Column(Integer, nullable=True)
    status = Column(String(40), nullable=False)
    error_code = Column(String(80), nullable=True)
    prompt_preview = Column(String(512), nullable=True)
    response_preview = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)


class AdminContentBlockDB(Base):
    __tablename__ = "admin_content_blocks"

    key = Column(String(120), primary_key=True)
    title = Column(String(200), nullable=False)
    content_json = Column(Text, nullable=False)
    status = Column(String(40), default="draft", nullable=False)
    published_at = Column(DateTime, nullable=True)
    updated_by = Column(String(36), nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class AssetLibraryItemDB(Base):
    __tablename__ = "asset_library_items"

    id = Column(String(36), primary_key=True, index=True)
    name = Column(String(200), nullable=False)
    type = Column(String(40), nullable=False)
    url = Column(String(1024), nullable=False)
    storage_path = Column(String(512), nullable=True)
    tags_json = Column(Text, nullable=True)
    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class SiteMessageDB(Base):
    __tablename__ = "site_messages"

    id = Column(String(36), primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    body = Column(Text, nullable=False)
    audience = Column(String(80), default="all", nullable=False)
    status = Column(String(40), default="draft", nullable=False)
    scheduled_at = Column(DateTime, nullable=True)
    created_by = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class SiteMessageReadDB(Base):
    __tablename__ = "site_message_reads"

    id = Column(String(36), primary_key=True, index=True)
    message_id = Column(String(36), index=True, nullable=False)
    user_id = Column(String(36), index=True, nullable=False)
    read_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (UniqueConstraint("message_id", "user_id", name="uq_site_message_user_read"),)


class AppearanceSettingDB(Base):
    __tablename__ = "appearance_settings"

    key = Column(String(120), primary_key=True)
    value_json = Column(Text, nullable=False)
    updated_by = Column(String(36), nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class MarketDataDailyBarDB(MarketdataBase):
    __tablename__ = "marketdata_daily_bar"

    symbol = Column(String(16), primary_key=True)
    trade_date = Column(Date, primary_key=True)
    open = Column(DECIMAL(18, 4), nullable=True)
    high = Column(DECIMAL(18, 4), nullable=True)
    low = Column(DECIMAL(18, 4), nullable=True)
    close = Column(DECIMAL(18, 4), nullable=True)
    volume = Column(BigInteger, nullable=True)
    amount = Column(DECIMAL(20, 2), nullable=True)
    adj_factor = Column(DECIMAL(18, 6), nullable=True)
    source_primary = Column(String(32), nullable=True)
    source_secondary = Column(String(32), nullable=True)
    recon_status = Column(String(16), nullable=False, server_default="unknown")
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_marketdata_daily_bar_trade_date", "trade_date"),
        Index("ix_marketdata_daily_bar_symbol_date", "symbol", "trade_date"),
    )


class MarketDataNorthMoneyDB(MarketdataBase):
    __tablename__ = "marketdata_north_money"

    trade_date = Column(Date, primary_key=True)
    symbol = Column(String(16), primary_key=True)
    hold_amount = Column(DECIMAL(20, 2), nullable=True)
    hold_ratio = Column(DECIMAL(10, 6), nullable=True)
    net_flow = Column(DECIMAL(20, 2), nullable=True)
    raw_json = Column(MARKETDATA_JSON, nullable=True)
    source_primary = Column(String(32), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_marketdata_north_money_date", "trade_date"),
        Index("ix_marketdata_north_money_symbol_date", "symbol", "trade_date"),
    )


class MarketDataCompanyBasicDB(MarketdataBase):
    __tablename__ = "marketdata_company_basic"

    symbol = Column(String(16), primary_key=True)
    name = Column(String(128), nullable=True)
    market = Column(String(16), nullable=True)
    industry = Column(String(128), nullable=True)
    list_date = Column(Date, nullable=True)
    status = Column(String(32), nullable=True)
    raw_json = Column(MARKETDATA_JSON, nullable=True)
    source_primary = Column(String(32), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_marketdata_company_basic_name", "name"),
        Index("ix_marketdata_company_basic_industry", "industry"),
    )


class MarketDataFinancialReportDB(MarketdataBase):
    __tablename__ = "marketdata_financial_report"

    symbol = Column(String(16), primary_key=True)
    period_end = Column(Date, primary_key=True)
    report_type = Column(String(32), primary_key=True)  # balancesheet / income / cashflow
    report_date = Column(Date, nullable=True)
    raw_json = Column(MARKETDATA_JSON, nullable=True)
    source_primary = Column(String(32), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_marketdata_financial_report_symbol_period", "symbol", "period_end"),
    )


class MarketDataDisclosureDB(MarketdataBase):
    __tablename__ = "marketdata_disclosure"

    id = Column(String(80), primary_key=True)
    symbol = Column(String(16), index=True, nullable=False)
    title = Column(String(512), nullable=True)
    ann_type = Column(String(128), nullable=True)
    ann_time = Column(DateTime(timezone=True), nullable=True, index=True)
    url = Column(String(1024), nullable=True)
    raw_json = Column(MARKETDATA_JSON, nullable=True)
    source_primary = Column(String(32), nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class MarketDataMacroIndicatorDB(MarketdataBase):
    __tablename__ = "marketdata_macro_indicator"

    series_id = Column(String(64), primary_key=True)
    period = Column(String(20), primary_key=True)  # YYYY-MM or YYYY-MM-DD
    value = Column(DECIMAL(20, 6), nullable=True)
    unit = Column(String(32), nullable=True)
    source_primary = Column(String(32), nullable=True)
    raw_json = Column(MARKETDATA_JSON, nullable=True)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        Index("ix_marketdata_macro_indicator_series_period", "series_id", "period"),
    )


class MarketDataVendorCallLogDB(MarketdataBase):
    __tablename__ = "marketdata_vendor_call_log"

    id = Column(String(36), primary_key=True)
    method = Column(String(64), nullable=False, index=True)
    vendor = Column(String(64), nullable=False, index=True)
    category = Column(String(64), nullable=True, index=True)
    market = Column(String(16), nullable=True, index=True)
    status = Column(String(16), nullable=False, index=True)  # hit / fallback / error
    latency_ms = Column(Integer, nullable=True)
    error_code = Column(String(120), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)


class MarketDataReconAnomalyDB(MarketdataBase):
    __tablename__ = "marketdata_recon_anomaly"

    id = Column(String(64), primary_key=True)
    trade_date = Column(Date, nullable=False, index=True)
    symbol = Column(String(16), nullable=False, index=True)
    field = Column(String(32), nullable=False)  # close/open/volume...
    value_primary = Column(DECIMAL(20, 6), nullable=True)
    value_secondary = Column(DECIMAL(20, 6), nullable=True)
    diff_ratio = Column(DECIMAL(18, 8), nullable=True)
    severity = Column(String(16), nullable=False, server_default="medium")
    source_primary = Column(String(32), nullable=False)
    source_secondary = Column(String(32), nullable=False)
    details = Column(MARKETDATA_JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)

    __table_args__ = (
        Index("ix_marketdata_recon_anomaly_date_symbol", "trade_date", "symbol"),
    )


class MarketDataDailyBasicDB(MarketdataBase):
    __tablename__ = "marketdata_daily_basic"

    symbol = Column(String(16), primary_key=True)
    trade_date = Column(Date, primary_key=True)
    pe = Column(DECIMAL(20, 6), nullable=True)
    pb = Column(DECIMAL(20, 6), nullable=True)
    ps = Column(DECIMAL(20, 6), nullable=True)
    total_mv = Column(DECIMAL(24, 4), nullable=True)
    circ_mv = Column(DECIMAL(24, 4), nullable=True)
    turnover_rate = Column(DECIMAL(20, 6), nullable=True)
    free_share = Column(DECIMAL(24, 4), nullable=True)
    source_primary = Column(String(32), nullable=True)
    raw_json = Column(MARKETDATA_JSON, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_marketdata_daily_basic_date", "trade_date"),
        Index("ix_marketdata_daily_basic_symbol_date", "symbol", "trade_date"),
    )


class MarketDataLimitListDB(MarketdataBase):
    __tablename__ = "marketdata_limit_list"

    symbol = Column(String(16), primary_key=True)
    trade_date = Column(Date, primary_key=True)
    limit_type = Column(String(8), nullable=True)
    fd_amount = Column(DECIMAL(24, 4), nullable=True)
    open_times = Column(Integer, nullable=True)
    lu_time = Column(String(16), nullable=True)
    last_time = Column(String(16), nullable=True)
    status = Column(String(32), nullable=True)
    source_primary = Column(String(32), nullable=True)
    raw_json = Column(MARKETDATA_JSON, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_marketdata_limit_list_date", "trade_date"),
        Index("ix_marketdata_limit_list_date_type", "trade_date", "limit_type"),
    )


class MarketDataMoneyflowDB(MarketdataBase):
    __tablename__ = "marketdata_moneyflow"

    symbol = Column(String(16), primary_key=True)
    trade_date = Column(Date, primary_key=True)
    buy_sm = Column(DECIMAL(24, 4), nullable=True)
    buy_md = Column(DECIMAL(24, 4), nullable=True)
    buy_lg = Column(DECIMAL(24, 4), nullable=True)
    buy_elg = Column(DECIMAL(24, 4), nullable=True)
    sell_sm = Column(DECIMAL(24, 4), nullable=True)
    sell_md = Column(DECIMAL(24, 4), nullable=True)
    sell_lg = Column(DECIMAL(24, 4), nullable=True)
    sell_elg = Column(DECIMAL(24, 4), nullable=True)
    net_sm = Column(DECIMAL(24, 4), nullable=True)
    net_md = Column(DECIMAL(24, 4), nullable=True)
    net_lg = Column(DECIMAL(24, 4), nullable=True)
    net_elg = Column(DECIMAL(24, 4), nullable=True)
    source_primary = Column(String(32), nullable=True)
    raw_json = Column(MARKETDATA_JSON, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_marketdata_moneyflow_date", "trade_date"),
        Index("ix_marketdata_moneyflow_symbol_date", "symbol", "trade_date"),
    )


class MarketDataMarginDetailDB(MarketdataBase):
    __tablename__ = "marketdata_margin_detail"

    symbol = Column(String(16), primary_key=True)
    trade_date = Column(Date, primary_key=True)
    rzye = Column(DECIMAL(24, 4), nullable=True)
    rzmre = Column(DECIMAL(24, 4), nullable=True)
    rqye = Column(DECIMAL(24, 4), nullable=True)
    rqmcl = Column(DECIMAL(24, 4), nullable=True)
    source_primary = Column(String(32), nullable=True)
    raw_json = Column(MARKETDATA_JSON, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_marketdata_margin_detail_date", "trade_date"),
        Index("ix_marketdata_margin_detail_symbol_date", "symbol", "trade_date"),
    )


class MarketDataTopListDB(MarketdataBase):
    __tablename__ = "marketdata_top_list"

    trade_date = Column(Date, primary_key=True)
    symbol = Column(String(16), primary_key=True)
    rank = Column(Integer, primary_key=True)
    close = Column(DECIMAL(20, 6), nullable=True)
    pct_change = Column(DECIMAL(20, 6), nullable=True)
    turnover_rate = Column(DECIMAL(20, 6), nullable=True)
    l_buy = Column(DECIMAL(24, 4), nullable=True)
    l_sell = Column(DECIMAL(24, 4), nullable=True)
    source_primary = Column(String(32), nullable=True)
    raw_json = Column(MARKETDATA_JSON, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_marketdata_top_list_date", "trade_date"),
        Index("ix_marketdata_top_list_symbol_date", "symbol", "trade_date"),
    )


class MarketDataTopInstDB(MarketdataBase):
    __tablename__ = "marketdata_top_inst"

    trade_date = Column(Date, primary_key=True)
    symbol = Column(String(16), primary_key=True)
    exalter = Column(String(128), primary_key=True)
    buy = Column(DECIMAL(24, 4), nullable=True)
    sell = Column(DECIMAL(24, 4), nullable=True)
    net = Column(DECIMAL(24, 4), nullable=True)
    source_primary = Column(String(32), nullable=True)
    raw_json = Column(MARKETDATA_JSON, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_marketdata_top_inst_date", "trade_date"),
        Index("ix_marketdata_top_inst_symbol_date", "symbol", "trade_date"),
    )


class MarketDataHsgtTop10DB(MarketdataBase):
    __tablename__ = "marketdata_hsgt_top10"

    trade_date = Column(Date, primary_key=True)
    symbol = Column(String(16), primary_key=True)
    market_type = Column(String(16), nullable=True)
    rank = Column(Integer, nullable=True)
    hold_amount = Column(DECIMAL(24, 4), nullable=True)
    net_buy = Column(DECIMAL(24, 4), nullable=True)
    source_primary = Column(String(32), nullable=True)
    raw_json = Column(MARKETDATA_JSON, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_marketdata_hsgt_top10_date", "trade_date"),
        Index("ix_marketdata_hsgt_top10_symbol_date", "symbol", "trade_date"),
    )


class MarketDataStkFactorProDB(MarketdataBase):
    __tablename__ = "marketdata_stk_factor_pro"

    symbol = Column(String(16), primary_key=True)
    trade_date = Column(Date, primary_key=True)
    fd_amount = Column(DECIMAL(24, 4), nullable=True)
    bid1_vol = Column(DECIMAL(24, 4), nullable=True)
    ask1_vol = Column(DECIMAL(24, 4), nullable=True)
    main_net_flow = Column(DECIMAL(24, 4), nullable=True)
    super_large_net = Column(DECIMAL(24, 4), nullable=True)
    large_net = Column(DECIMAL(24, 4), nullable=True)
    mid_net = Column(DECIMAL(24, 4), nullable=True)
    small_net = Column(DECIMAL(24, 4), nullable=True)
    limit_up_days = Column(Integer, nullable=True)
    limit_up_height = Column(Integer, nullable=True)
    net_subscribe = Column(DECIMAL(24, 4), nullable=True)
    turnover_rate_z = Column(DECIMAL(24, 4), nullable=True)
    amplitude_pct = Column(DECIMAL(24, 4), nullable=True)
    vol_ratio = Column(DECIMAL(24, 4), nullable=True)
    source_primary = Column(String(32), nullable=True)
    raw_json = Column(MARKETDATA_JSON, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_marketdata_stk_factor_pro_date", "trade_date"),
        Index("ix_marketdata_stk_factor_pro_symbol_date", "symbol", "trade_date"),
        Index("ix_marketdata_stk_factor_pro_trade_date_main_flow", "trade_date", "main_net_flow"),
        Index("ix_marketdata_stk_factor_pro_trade_date_fd_amount", "trade_date", "fd_amount"),
    )


class MarketDataCyqPerfDB(MarketdataBase):
    __tablename__ = "marketdata_cyq_perf"

    symbol = Column(String(16), primary_key=True)
    trade_date = Column(Date, primary_key=True)
    his_low = Column(DECIMAL(20, 6), nullable=True)
    his_high = Column(DECIMAL(20, 6), nullable=True)
    cost_5pct = Column(DECIMAL(20, 6), nullable=True)
    cost_15pct = Column(DECIMAL(20, 6), nullable=True)
    cost_50pct = Column(DECIMAL(20, 6), nullable=True)
    cost_85pct = Column(DECIMAL(20, 6), nullable=True)
    cost_95pct = Column(DECIMAL(20, 6), nullable=True)
    weight_avg = Column(DECIMAL(20, 6), nullable=True)
    winner_rate = Column(DECIMAL(20, 6), nullable=True)
    source_primary = Column(String(32), nullable=True)
    raw_json = Column(MARKETDATA_JSON, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_marketdata_cyq_perf_date", "trade_date"),
        Index("ix_marketdata_cyq_perf_symbol_date", "symbol", "trade_date"),
    )


class MarketDataFinaIndicatorDB(MarketdataBase):
    __tablename__ = "marketdata_fina_indicator"

    symbol = Column(String(16), primary_key=True)
    end_date = Column(Date, primary_key=True)
    roe = Column(DECIMAL(20, 6), nullable=True)
    gross_margin = Column(DECIMAL(20, 6), nullable=True)
    debt_ratio = Column(DECIMAL(20, 6), nullable=True)
    source_primary = Column(String(32), nullable=True)
    raw_json = Column(MARKETDATA_JSON, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_marketdata_fina_indicator_symbol_end_date", "symbol", "end_date"),
    )


class MarketDataForecastDB(MarketdataBase):
    __tablename__ = "marketdata_forecast"

    symbol = Column(String(16), primary_key=True)
    end_date = Column(Date, primary_key=True)
    ann_date = Column(Date, primary_key=True)
    source_primary = Column(String(32), nullable=True)
    raw_json = Column(MARKETDATA_JSON, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class MarketDataExpressDB(MarketdataBase):
    __tablename__ = "marketdata_express"

    symbol = Column(String(16), primary_key=True)
    end_date = Column(Date, primary_key=True)
    ann_date = Column(Date, primary_key=True)
    source_primary = Column(String(32), nullable=True)
    raw_json = Column(MARKETDATA_JSON, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class MarketDataHolderNumberDB(MarketdataBase):
    __tablename__ = "marketdata_holdernumber"

    symbol = Column(String(16), primary_key=True)
    end_date = Column(Date, primary_key=True)
    holder_num = Column(DECIMAL(24, 4), nullable=True)
    source_primary = Column(String(32), nullable=True)
    raw_json = Column(MARKETDATA_JSON, nullable=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

