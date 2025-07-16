# database.py
import pandas as pd
from sqlalchemy import create_engine, inspect, text
from pathlib import Path

# ── DATABASE SETUP ───────────────────────────────────────────────
Path("/mnt/data").mkdir(exist_ok=True)        # local safety; no‑op on Cloud
DB_FILE = Path("/mnt/data") / "projects.db"   # lives on the persistent volume
engine = create_engine(f"sqlite:///{DB_FILE}")

# ── INITIALISATION ───────────────────────────────────────────────
def initialize_database() -> None:
    """Create / patch tables as needed."""
    with engine.connect() as conn:
        if not inspect(engine).has_table("projects"):
            conn.execute(text("""
                CREATE TABLE projects (
                    id   INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT    NOT NULL UNIQUE
                );
            """))
            conn.execute(text(
                "INSERT INTO projects (name) VALUES ('Default Project')"
            ))
            conn.commit()
            print("Created 'projects' table.")

        if not inspect(engine).has_table("tasks"):
            conn.execute(text("""
                CREATE TABLE tasks (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    task_id_str TEXT NOT NULL,
                    description TEXT NOT NULL,
                    predecessors TEXT,
                    duration INTEGER NOT NULL,
                    status TEXT DEFAULT 'Not Started',
                    FOREIGN KEY (project_id) REFERENCES projects (id)
                );
            """))
            print("Created 'tasks' table.")
        else:
            cols = [c["name"] for c in inspect(engine).get_columns("tasks")]
            if "status" not in cols:
                conn.execute(text(
                    "ALTER TABLE tasks ADD COLUMN status TEXT "
                    "DEFAULT 'Not Started'"
                ))
                conn.commit()
                print("Added 'status' column.")

# ── SIMPLE HELPERS ───────────────────────────────────────────────
def get_all_projects() -> dict[str, int]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT id, name FROM projects ORDER BY name")
        )
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

# ── IMPORT / SAVE OPERATIONS ─────────────────────────────────────
def import_df_to_db(df: pd.DataFrame, project_name: str) -> int:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT id FROM projects WHERE name = :n"), {"n": project_name}
        ).first()
        project_id = row[0] if row else conn.execute(
            text("INSERT INTO projects (name) VALUES (:n)"), {"n": project_name}
        ).lastrowid

        df_to_save = df.copy()
        if "Status" not in df_to_save.columns:
            df_to_save["Status"] = "Not Started"

        df_to_save["project_id"] = project_id
        df_to_save = df_to_save.rename(columns={
            "Task ID":        "task_id_str",
            "Task Description":"description",
            "Predecessors":   "predecessors",
            "Duration":       "duration",
            "Status":         "status"
        })[
            ["project_id", "task_id_str", "description",
             "predecessors", "duration", "status"]
        ]

        conn.execute(
            text("DELETE FROM tasks WHERE project_id = :pid"),
            {"pid": project_id},
        )
        df_to_save.to_sql("tasks", conn, if_exists="append", index=False)
        conn.commit()
    return project_id

def save_tasks_to_db(df: pd.DataFrame, project_id: int) -> None:
    df_to_save = df.copy()
    df_to_save["project_id"] = project_id
    df_to_save = df_to_save.rename(columns={
        "Task ID":        "task_id_str",
        "Task Description":"description",
        "Predecessors":   "predecessors",
        "Duration":       "duration",
        "Status":         "status"
    })[
        ["project_id", "task_id_str", "description",
         "predecessors", "duration", "status"]
    ]

    with engine.connect() as conn:
        conn.execute(
            text("DELETE FROM tasks WHERE project_id = :pid"),
            {"pid": project_id},
        )
        df_to_save.to_sql("tasks", conn, if_exists="append", index=False)
        conn.commit()
