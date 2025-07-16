# database.py
import pandas as pd
from sqlalchemy import create_engine, inspect, text

# --- DATABASE SETUP ---
DB_FILE = "projects.db"
engine = create_engine(f"sqlite:///{DB_FILE}")

def initialize_database():
    """Initializes the database. Creates/updates tables as needed."""
    with engine.connect() as connection:
        if not inspect(engine).has_table("projects"):
            connection.execute(text("""
                CREATE TABLE projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE
                );
            """))
            connection.execute(text("INSERT INTO projects (name) VALUES ('Default Project')"))
            connection.commit()
            print("Database initialized and 'projects' table created.")

        if not inspect(engine).has_table("tasks"):
            connection.execute(text("""
                CREATE TABLE tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    task_id_str TEXT NOT NULL,
                    description TEXT NOT NULL,
                    predecessors TEXT,
                    duration INTEGER NOT NULL,
                    status TEXT DEFAULT 'Not Started',
                    FOREIGN KEY (project_id) REFERENCES projects (id)
                );
            """))
            print("'tasks' table created.")
        else:
            # --- MINIMAL CHANGE: Add status column if it doesn't exist ---
            inspector = inspect(engine)
            columns = [col['name'] for col in inspector.get_columns('tasks')]
            if 'status' not in columns:
                connection.execute(text("ALTER TABLE tasks ADD COLUMN status TEXT DEFAULT 'Not Started'"))
                connection.commit()
                print("Added 'status' column to tasks table.")

def get_all_projects():
    with engine.connect() as connection:
        result = connection.execute(text("SELECT id, name FROM projects ORDER BY name"))
        return {name: id for id, name in result}

def get_project_data_from_db(project_id):
    if project_id is None:
        return pd.DataFrame()
    # Add status to the SELECT query
    query = text("""
        SELECT task_id_str as "Task ID", description as "Task Description", 
               predecessors as "Predecessors", duration as "Duration",
               status as "Status"
        FROM tasks 
        WHERE project_id = :proj_id
    """)
    with engine.connect() as connection:
        df = pd.read_sql(query, connection, params={"proj_id": project_id})
    return df

def import_df_to_db(df, project_name):
    with engine.connect() as connection:
        res = connection.execute(text("SELECT id FROM projects WHERE name = :name"), {"name": project_name}).first()
        if res:
            project_id = res[0]
        else:
            insert_res = connection.execute(text("INSERT INTO projects (name) VALUES (:name)"), {"name": project_name})
            project_id = insert_res.lastrowid

        df_to_save = df.copy()
        # Ensure status column exists in the uploaded file, if not, add it
        if "Status" not in df_to_save.columns:
            df_to_save['Status'] = 'Not Started'
        
        required_cols = ["Task ID", "Task Description", "Predecessors", "Duration", "Status"]
        df_to_save['project_id'] = project_id
        df_to_save = df_to_save.rename(columns={
            "Task ID": "task_id_str", "Task Description": "description",
            "Predecessors": "predecessors", "Duration": "duration", "Status": "status"
        })
        db_cols = ["project_id", "task_id_str", "description", "predecessors", "duration", "status"]
        df_to_save = df_to_save[db_cols]

        connection.execute(text("DELETE FROM tasks WHERE project_id = :proj_id"), {"proj_id": project_id})
        df_to_save.to_sql("tasks", con=connection, if_exists="append", index=False)
        connection.commit()
    return project_id

def save_tasks_to_db(df, project_id):
    df_to_save = df.copy()
    df_to_save['project_id'] = project_id
    df_to_save = df_to_save.rename(columns={
        "Task ID": "task_id_str", "Task Description": "description",
        "Predecessors": "predecessors", "Duration": "duration", "Status": "status"
    })
    db_cols = ["project_id", "task_id_str", "description", "predecessors", "duration", "status"]
    
    with engine.connect() as connection:
        connection.execute(text("DELETE FROM tasks WHERE project_id = :proj_id"), {"proj_id": project_id})
        df_to_save[db_cols].to_sql("tasks", con=connection, if_exists="append", index=False)
        connection.commit()
