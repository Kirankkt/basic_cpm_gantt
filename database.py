"""
Database helpers (PostgreSQL or SQLite fallback).

Tables
------
projects : id, name, start_date
tasks    : id, project_id, task_id_str, description, predecessors,
           duration, status, es, ef
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List   # ← ADD THIS
import os
import streamlit as st
from sqlalchemy import create_engine, inspect, text

# 1) Streamlit-secrets  2) env var  3) fallback SQLite
DB_URL = (
    st.secrets.get("database", {}).get("url")
    or os.getenv("DB_URL")
    or f"sqlite:///{Path(__file__).parent / 'projects.db'}"
)

engine = create_engine(DB_URL, future=True, echo=False)


# ── schema bootstrap / patch ─────────────────────────────────────────────────
def initialize_database() -> None:
    """Create or patch tables so the rest of the app can assume columns exist."""
    with engine.begin() as conn:  # handles COMMIT/ROLLBACK automatically
        # --- projects --------------------------------------------------------
        conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS projects (
                id          SERIAL PRIMARY KEY,
                name        TEXT NOT NULL UNIQUE,
                start_date  DATE            -- may be NULL until user picks one
            );
            """
            )
        )

        # --- tasks -----------------------------------------------------------
        conn.execute(
            text(
                """
            CREATE TABLE IF NOT EXISTS tasks (
                id            SERIAL PRIMARY KEY,
                project_id    INTEGER NOT NULL REFERENCES projects(id),
                task_id_str   TEXT    NOT NULL,
                description   TEXT    NOT NULL,
                predecessors  TEXT,
                duration      INTEGER NOT NULL,
                status        TEXT    DEFAULT 'Not Started',
                es            INTEGER,          -- Early Start  (1-based)
                ef            INTEGER           -- Early Finish
            );
            """
            )
        )

        # patch columns if legacy installs miss them
        inspector = inspect(conn)
        task_cols = {c["name"] for c in inspector.get_columns("tasks")}
        for missing, ddl in [
            ("status", "ALTER TABLE tasks ADD COLUMN status TEXT DEFAULT 'Not Started'"),
            ("es", "ALTER TABLE tasks ADD COLUMN es INTEGER"),
            ("ef", "ALTER TABLE tasks ADD COLUMN ef INTEGER"),
        ]:
            if missing not in task_cols:
                conn.execute(text(ddl))


# ── convenience helpers ------------------------------------------------------
def get_all_projects() -> Dict[str, int]:
    """Return {project_name: id} sorted by name."""
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, name FROM projects ORDER BY name"))
        return {name: pid for pid, name in rows}


def get_project_data_from_db(project_id: int | None) -> pd.DataFrame:
    if not project_id:
        return pd.DataFrame()
    query = text(
        """
        SELECT task_id_str  AS "Task ID",
               description  AS "Task Description",
               predecessors AS "Predecessors",
               duration     AS "Duration",
               status       AS "Status",
               es           AS "ES",
               ef           AS "EF"
        FROM tasks
        WHERE project_id = :pid
        ORDER BY id
        """
    )
    return pd.read_sql(query, engine, params={"pid": project_id})


def import_df_to_db(df: pd.DataFrame, project_name: str) -> int:
    """Create project (or replace its tasks) from uploaded CSV/XLSX."""
    with engine.begin() as conn:
        res = conn.execute(
            text("SELECT id FROM projects WHERE name = :n"), {"n": project_name}
        ).first()
        project_id = res[0] if res else conn.execute(
            text("INSERT INTO projects (name) VALUES (:n) RETURNING id"),
            {"n": project_name},
        ).scalar_one()

        # normalise columns
        upload = df.copy()
        if "Status" not in upload:
            upload["Status"] = "Not Started"
        upload = upload.rename(
            columns={
                "Task ID": "task_id_str",
                "Task Description": "description",
                "Predecessors": "predecessors",
                "Duration": "duration",
                "Status": "status",
                "ES": "es",
                "EF": "ef",
            }
        )
        upload["project_id"] = project_id
        upload[
            ["project_id", "task_id_str", "description", "predecessors",
             "duration", "status", "es", "ef"]
        ].to_sql("tasks", conn, if_exists="replace", index=False)
    return project_id


def save_tasks_to_db(df: pd.DataFrame, project_id: int) -> None:
    """Write the (edited + CPM-augmented) DataFrame back to DB."""
    upload = df.rename(
        columns={
            "Task ID": "task_id_str",
            "Task Description": "description",
            "Predecessors": "predecessors",
            "Duration": "duration",
            "Status": "status",
            "ES": "es",
            "EF": "ef",
        }
    )
    upload["project_id"] = project_id
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM tasks WHERE project_id = :pid"), {"pid": project_id})
        upload[
            ["project_id", "task_id_str", "description", "predecessors",
             "duration", "status", "es", "ef"]
        ].to_sql("tasks", conn, if_exists="append", index=False)
