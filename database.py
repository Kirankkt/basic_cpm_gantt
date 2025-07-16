# database.py
import os
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, inspect, text

# ── DATABASE SETUP ──────────────────────────────────────────────
DB_URL = (
    st.secrets["database"]["url"]          # Streamlit Cloud / secrets.toml
    if "database" in st.secrets
    else os.getenv("DATABASE_URL")         # fallback for local dev
)

if DB_URL is None:
    raise RuntimeError(
        "Database URL not found. "
        "Add it to .streamlit/secrets.toml or set the DATABASE_URL env‑var."
    )

engine = create_engine(DB_URL, pool_pre_ping=True, echo=False)

# ── INITIALISATION ──────────────────────────────────────────────
def initialize_database() -> None:
    """Create or patch tables inside Postgres."""
    with engine.begin() as conn:           # BEGIN … COMMIT automatically
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS projects (
                id   SERIAL PRIMARY KEY,
                name TEXT NOT NULL UNIQUE
            );
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS tasks (
                id           SERIAL PRIMARY KEY,
                project_id   INTEGER NOT NULL REFERENCES projects(id)
                               ON DELETE CASCADE,
                task_id_str  TEXT NOT NULL,
                description  TEXT NOT NULL,
                predecessors TEXT,
                duration     INTEGER NOT NULL,
                status       TEXT DEFAULT 'Not Started'
            );
        """))

        # add `status` column if the table predates it
        cols = [c["name"] for c in inspect(conn).get_columns("tasks")]
        if "status" not in cols:
            conn.execute(text(
                "ALTER TABLE tasks ADD COLUMN status TEXT "
                "DEFAULT 'Not Started';"
            ))

# ── QUERY HELPERS ───────────────────────────────────────────────
def get_all_projects() -> dict[str, int]:
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT id, name FROM projects ORDER BY name"
        ))
        return {name: pid for pid, name in rows}

def get_project_data_from_db(project_id: int) -> pd.DataFrame:
    if project_id is None:
        return pd.DataFrame()
    q = text("""
        SELECT task_id_str  AS "Task ID",
               description  AS "Task Description",
               predecessors AS "Predecessors",
               duration     AS "Duration",
               status       AS "Status"
        FROM tasks
        WHERE project_id = :pid
    """)
    with engine.connect() as conn:
        return pd.read_sql(q, conn, params={"pid": project_id})

# ── IMPORT / SAVE OPERATIONS ────────────────────────────────────
def import_df_to_db(df: pd.DataFrame, project_name: str) -> int:
    with engine.begin() as conn:
        pid = conn.execute(
            text("""
                INSERT INTO projects (name)
                VALUES (:n)
                ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
            """),
            {"n": project_name},
        ).scalar_one()

        df_copy = df.copy()
        if "Status" not in df_copy.columns:
            df_copy["Status"] = "Not Started"

        df_copy["project_id"] = pid
        df_copy = df_copy.rename(columns={
            "Task ID":         "task_id_str",
            "Task Description":"description",
            "Predecessors":    "predecessors",
            "Duration":        "duration",
            "Status":          "status"
        })[
            ["project_id", "task_id_str", "description",
             "predecessors", "duration", "status"]
        ]

        conn.execute(text("DELETE FROM tasks WHERE project_id = :pid"),
                     {"pid": pid})
        df_copy.to_sql("tasks", conn, if_exists="append", index=False)
    return pid

def save_tasks_to_db(df: pd.DataFrame, project_id: int) -> None:
    df_copy = df.copy()
    df_copy["project_id"] = project_id
    df_copy = df_copy.rename(columns={
        "Task ID":         "task_id_str",
        "Task Description":"description",
        "Predecessors":    "predecessors",
        "Duration":        "duration",
        "Status":          "status"
    })[
        ["project_id", "task_id_str", "description",
         "predecessors", "duration", "status"]
    ]

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM tasks WHERE project_id = :pid"),
                     {"pid": project_id})
        df_copy.to_sql("tasks", conn, if_exists="append", index=False)
