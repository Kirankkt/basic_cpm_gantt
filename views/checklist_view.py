"""
Daily checklist view – shows tasks whose ES..EF window includes today.

Ticking a task marks its status 'Complete' instantly.
"""

from datetime import date

import pandas as pd
import streamlit as st
from sqlalchemy import text

from database import engine, get_all_projects, save_tasks_to_db, get_project_data_from_db
from cpm_logic import calculate_cpm


def show_checklist_view() -> None:
    st.header("✅ Daily Task Checklist")

    # pick project
    projects = get_all_projects()
    if not projects:
        st.info("No projects yet. Upload one in the Planner.")
        return

    pname = st.selectbox("Project", list(projects.keys()))
    pid = projects[pname]

    # need start_date
    with engine.connect() as conn:
        start_date = conn.execute(
            text("SELECT start_date FROM projects WHERE id=:pid"),
            {"pid": pid},
        ).scalar()
    if not start_date:
        st.warning("Set a project start date in the Planner first.")
        return

    # day number today (1-based)
    rel_day = (date.today() - start_date).days + 1

    # pull tasks for the window
    today_df = pd.read_sql(
        text(
            """
        SELECT id, task_id_str AS "Task ID", description AS "Task Description",
               status
        FROM tasks
        WHERE project_id = :pid
          AND status != 'Complete'
          AND es <= :d AND ef >= :d
        ORDER BY id
        """
        ),
        engine,
        params={"pid": pid, "d": rel_day},
    )

    if today_df.empty:
        st.success("All scheduled tasks are complete for today 🎉")
        return

    st.write(f"Date: **{date.today():%d %b %Y}** — schedule day {rel_day}")

    # checkbox list
    completed = st.multiselect(
        "Mark completed", today_df["Task ID"] + " — " + today_df["Task Description"]
    )
    if completed:
        done_ids = [row.split(" — ")[0] for row in completed]
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE tasks SET status='Complete' "
                    "WHERE project_id=:pid AND task_id_str=ANY(:ids)"
                ),
                {"pid": pid, "ids": done_ids},
            )
        st.success("Saved progress!")
        st.rerun()
