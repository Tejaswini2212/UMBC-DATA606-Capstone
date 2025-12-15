# db_helpers.py

import os
import hashlib
import pandas as pd
from sqlalchemy import create_engine, text

# ==============================================================
# DB CONFIG
# ==============================================================

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://neondb_owner:npg_WZCgK7qno1SO@ep-tiny-fire-ahu53e2e-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
)

engine = create_engine(DATABASE_URL)


# ==============================================================
# USERS TABLE / AUTH HELPERS
# ==============================================================

def hash_password(password: str) -> str:
    """Simple SHA256 hash. (Good enough for project demo.)"""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def get_user_by_email(email: str):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id, email, password_hash FROM users WHERE email = :e"),
            {"e": email.strip().lower()},
        ).fetchone()
    return row


def create_user(email: str, password: str):
    email_norm = email.strip().lower()
    pwd_hash = hash_password(password)
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO users (email, password_hash)
                VALUES (:email, :ph)
                RETURNING id, email, password_hash
                """
            ),
            {"email": email_norm, "ph": pwd_hash},
        ).fetchone()
        conn.commit()
    return row


def validate_credentials(email: str, password: str):
    row = get_user_by_email(email)
    if not row:
        return None
    if hash_password(password) != row.password_hash:
        return None
    return row  # has id, email, password_hash


# ==============================================================
# DB INIT (TABLES / CONSTRAINTS)
# ==============================================================

def init_db():
    with engine.connect() as conn:
        # 1) USERS TABLE
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT now()
            );
        """))

        # 2) STATEMENTS TABLE
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS statements (
                id SERIAL PRIMARY KEY,
                sha256 TEXT NOT NULL,
                original_filename TEXT,
                statement_type TEXT,
                uploaded_at TIMESTAMPTZ DEFAULT now(),
                user_id INTEGER REFERENCES users(id)
            );
        """))

        # ensure user_id column exists
        conn.execute(text("""
            ALTER TABLE statements
            ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id);
        """))

        # 3) STATEMENT_ROWS TABLE
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS statement_rows (
                id SERIAL PRIMARY KEY,
                "Date" TEXT,
                "Transaction Date" TEXT,
                "Posting Date" TEXT,
                "Description" TEXT,
                "Amount" TEXT,
                "Vendor" TEXT,
                "Category" TEXT,
                statement_name TEXT,
                statement_type TEXT,
                section_name TEXT,
                statement_id INTEGER REFERENCES statements(id),
                user_id INTEGER REFERENCES users(id)
            );
        """))

        # ensure user_id column exists
        conn.execute(text("""
            ALTER TABLE statement_rows
            ADD COLUMN IF NOT EXISTS user_id INTEGER REFERENCES users(id);
        """))

        # 4) Drop old unique constraint on sha256 if it exists
        conn.execute(text("""
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'statements_sha256_key'
                ) THEN
                    ALTER TABLE statements DROP CONSTRAINT statements_sha256_key;
                END IF;
            END$$;
        """))

        # 5) New unique index per user + sha256
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_statements_user_sha
            ON statements(user_id, sha256);
        """))

        conn.commit()


# ==============================================================
# STATEMENT HELPERS (PER USER)
# ==============================================================

def get_statement_by_hash(sha256_hex: str, user_id: int):
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT id, sha256, original_filename, statement_type, user_id "
                "FROM statements WHERE sha256 = :sha AND user_id = :uid"
            ),
            {"sha": sha256_hex, "uid": user_id},
        ).fetchone()
    return row


def create_statement_record(
    sha256_hex: str,
    filename: str,
    statement_type: str,
    user_id: int,
):
    with engine.connect() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO statements (sha256, original_filename, statement_type, user_id)
                VALUES (:sha, :filename, :stype, :uid)
                ON CONFLICT (user_id, sha256)
                DO UPDATE SET statement_type = EXCLUDED.statement_type,
                              original_filename = EXCLUDED.original_filename
                RETURNING id, sha256, original_filename, statement_type, user_id
                """
            ),
            {
                "sha": sha256_hex,
                "filename": filename,
                "stype": statement_type,
                "uid": user_id,
            },
        ).fetchone()
        conn.commit()
    return row


def write_section_to_db(
    section_name: str,
    df: pd.DataFrame,
    base_name: str,
    statement_type: str,
    statement_id: int,
    user_id: int,
):
    df2 = df.copy()

    # Ensure all standard columns exist
    for col in [
        "Date", "Transaction Date", "Posting Date",
        "Description", "Amount", "Vendor", "Category"
    ]:
        if col not in df2.columns:
            df2[col] = None

    df2["statement_name"] = base_name
    df2["statement_type"] = statement_type
    df2["section_name"] = section_name
    df2["statement_id"] = statement_id
    df2["user_id"] = user_id

    df2.to_sql("statement_rows", engine, if_exists="append", index=False)
