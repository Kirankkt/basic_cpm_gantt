# database.py
import pandas as pd
from sqlalchemy import create_engine, inspect, text

# --- DATABASE SETUP ---
DB_FILE = "projects.db"
engine = create_engine(f"sqlite:///{DB_FILE}")

def initialize_database():
    """
    Initializes the database. Creates 'projects' and 'tasks' tables if they don't exist.
    """
    with engine.connect() as connection:
        if not inspect(engine).has_table("projects"):
            connection.execute(text("""
                CREATE TABLE projects (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE
                );
            """))
            # Add a default project if none exist
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
                    FOREIGN KEY (project_id) REFERENCES projects (id)
                );
            """))
            print("'tasks' table created.")

def get_all_projects():
    """Returns a dictionary of all projects {project_name: project_id}."""
    with engine.connect() as connection:
        result = connection.execute(text("SELECT id, name FROM projects ORDER BY name"))
        # Return as a dictionary for easy lookup in the UI
        return {name: id for id, name in result}

def get_project_data_from_db(project_id):
    """Reads task data for a specific project_id from the database."""
    if project_id is None:
        return pd.DataFrame()
    query = text("""
        SELECT task_id_str as "Task ID", description as "Task Description", 
               predecessors as "Predecessors", duration as "Duration" 
        FROM tasks 
        WHERE project_id = :proj_id
    """)
    with engine.connect() as connection:
        df = pd.read_sql(query, connection, params={"proj_id": project_id})
    return df

def import_df_to_db(df, project_name):
    """
    Imports a DataFrame as a new project. If the project name already exists,
    it overwrites the tasks for that project.
    """
    with engine.connect() as connection:
        # Check if project exists, if not, create it
        res = connection.execute(text("SELECT id FROM projects WHERE name = :name"), {"name": project_name}).first()
        if res:
            project_id = res[0]
        else:
            insert_res = connection.execute(text("INSERT INTO projects (name) VALUES (:name)"), {"name": project_name})
            project_id = insert_res.lastrowid

        # Prepare DataFrame for database insertion
        df_to_save = df.copy()
        required_cols = ["Task ID", "Task Description", "Predecessors", "Duration"]
        for col in required_cols:
            if col not in df_to_save.columns:
                raise ValueError(f"Uploaded file is missing required column: {col}")
        
        df_to_save['project_id'] = project_id
        df_to_save = df_to_save.rename(columns={
            "Task ID": "task_id_str", "Task Description": "description",
            "Predecessors": "predecessors", "Duration": "duration"
        })
        db_cols = ["project_id", "task_id_str", "description", "predecessors", "duration"]
        df_to_save = df_to_save[db_cols]

        # Overwrite strategy: Delete old tasks for this project before inserting new ones
        connection.execute(text("DELETE FROM tasks WHERE project_id = :proj_id"), {"proj_id": project_id})
        df_to_save.to_sql("tasks", con=connection, if_exists="append", index=False)
        connection.commit()
    print(f"Successfully imported {len(df_to_save)} tasks into project '{project_name}'.")
    return project_id

# We rename the old save function to be more specific
def save_tasks_to_db(df, project_id):
    """Saves an edited DataFrame back to the database for a specific project."""
    df_to_save = df.copy()
    df_to_save['project_id'] = project_id
    df_to_save = df_to_save.rename(columns={
        "Task ID": "task_id_str", "Task Description": "description",
        "Predecessors": "predecessors", "Duration": "duration"
    })
    db_cols = ["project_id", "task_id_str", "description", "predecessors", "duration"]
    
    with engine.connect() as connection:
        connection.execute(text("DELETE FROM tasks WHERE project_id = :proj_id"), {"proj_id": project_id})
        df_to_save[db_cols].to_sql("tasks", con=connection, if_exists="append", index=False)
        connection.commit()
    print(f"Project data for project_id {project_id} saved to database.")
