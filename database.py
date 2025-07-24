"""
Database helpers (PostgreSQL or SQLite).

Tables
------
projects : id, name, start_date
tasks    : id, project_id, task_id_str, description, predecessors,
           duration, status, es, ef
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict

import os
import pandas as pd
import streamlit as st
from sqlalchemy import create_engine, inspect, text

# 1) secrets.toml  2) $DB_URL env  3) local SQLite fallback
DB_URL = (
    st.secrets.get("database", {}).get("url")
    or os.getenv("DB_URL")
    or f"sqlite:///{Path(__file__).parent / 'projects.db'}"
)

engine = create_engine(DB_URL, echo=False, future=True)


# ─────────────────────────── schema bootstrap ────────────────────────────────
def initialize_database() -> None:
    with engine.begin() as conn:
        # projects
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id         SERIAL PRIMARY KEY,
                    name       TEXT  NOT NULL UNIQUE,
                    start_date DATE  DEFAULT CURRENT_DATE
                );
                """
            )
        )
        # patch older installs
        if "start_date" not in {c["name"] for c in inspect(conn).get_columns("projects")}:
            conn.execute(text("ALTER TABLE projects ADD COLUMN start_date DATE"))

        # tasks
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id            SERIAL PRIMARY KEY,
                    project_id    INTEGER REFERENCES projects(id) ON DELETE CASCADE,
                    task_id_str   TEXT    NOT NULL,
                    description   TEXT    NOT NULL,
                    predecessors  TEXT,
                    duration      INTEGER NOT NULL,
                    status        TEXT    DEFAULT 'Not Started',
                    es            INTEGER,
                    ef            INTEGER
                );
                """
            )
        )
        # ensure newer columns on legacy DB
        have_cols = {c["name"] for c in inspect(conn).get_columns("tasks")}
        for col, ddl in [
            ("status", "ALTER TABLE tasks ADD COLUMN status TEXT DEFAULT 'Not Started'"),
            ("es", "ALTER TABLE tasks ADD COLUMN es INTEGER"),
            ("ef", "ALTER TABLE tasks ADD COLUMN ef INTEGER"),
        ]:
            if col not in have_cols:
                conn.execute(text(ddl))


# ───────────────────────────── helpers ───────────────────────────────────────
def get_all_projects() -> Dict[str, int]:
    """Return {project_name: id}."""
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT id, name FROM projects ORDER BY name"))
        return {name: pid for pid, name in rows}


def get_project_data_from_db(project_id: int | None) -> pd.DataFrame:
    if not project_id:
        return pd.DataFrame()
    q = text(
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
    return pd.read_sql(q, engine, params={"pid": project_id})


def import_df_to_db(df: pd.DataFrame, project_name: str) -> int:
    """Create / replace a project from an uploaded file."""
    with engine.begin() as conn:
        pid = conn.execute(
            text("INSERT INTO projects (name) VALUES (:n) "
                 "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name "
                 "RETURNING id"),
            {"n": project_name},
        ).scalar_one()

        # normalise columns
        up = df.copy()
        if "Status" not in up:
            up["Status"] = "Not Started"

        up = up.rename(
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
        up["project_id"] = pid

        # replace tasks wholesale
        conn.execute(text("DELETE FROM tasks WHERE project_id=:pid"), {"pid": pid})
        up[
            ["project_id", "task_id_str", "description", "predecessors",
             "duration", "status", "es", "ef"]
        ].to_sql("tasks", conn, if_exists="append", index=False)

    return pid


def save_tasks_to_db(df: pd.DataFrame, project_id: int) -> None:
    """Persist the edited + CPM-augmented DataFrame (tolerant of missing es/ef)."""
    up = df.rename(
        columns={
            "Task ID": "task_id_str",
            "Task Description": "description",
            "Predecessors": "predecessors",
            "Duration": "duration",
            "Status": "status",
            "ES": "es",
            "EF": "ef",
        }
    ).copy()

    # graceful fallback: ensure es / ef columns exist (NULL → shows as blank)
    for col in ("es", "ef"):
        if col not in up:
            up[col] = pd.NA

    up["project_id"] = project_id

    with engine.begin() as conn:
        conn.execute(text("DELETE FROM tasks WHERE project_id = :pid"),
                     {"pid": project_id})
        up[
            ["project_id", "task_id_str", "description", "predecessors",
             "duration", "status", "es", "ef"]
        ].to_sql("tasks", conn, if_exists="append", index=False)
