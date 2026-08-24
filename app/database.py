"""Database configuration and setup."""

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

# Create engine
engine = create_engine(
    settings.DATABASE_URL,
    connect_args=(
        {
            "check_same_thread": False,
            # Wait for a busy database instead of failing instantly with
            # "database is locked". The monitoring run writes from a
            # background thread while the dashboard is being used; the
            # default 5s is not enough to ride out a slow commit.
            "timeout": 30,
        }
        if "sqlite" in settings.DATABASE_URL
        else {}
    ),
    echo=settings.DEBUG,
)

# Enable foreign keys for SQLite
if "sqlite" in settings.DATABASE_URL:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        # WAL lets the dashboard keep reading (and queue its writes) while
        # the monitoring run writes. In the default rollback-journal mode a
        # single writer blocks everyone, which is what surfaced as
        # "database is locked" when saving a recipient during a run.
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
        except Exception as e:  # e.g. a DB on a network share
            print(f"[DB] WAL non attivabile ({e}), uso il journal di default")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db():
    """Dependency for FastAPI to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _add_missing_columns():
    """Additively add columns introduced after tables already existed.

    create_all() only creates missing tables, not missing columns on
    existing tables, so a manual model change needs an explicit ALTER TABLE
    here. Never drops or renames anything, so existing data is untouched.
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        existing_columns = {col["name"] for col in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in existing_columns:
                continue
            col_type = column.type.compile(engine.dialect)
            with engine.begin() as conn:
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'))
            print(f"Migrated: added column {table.name}.{column.name}")


def init_db():
    """Initialize database tables."""
    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
    print("Database initialized successfully")
