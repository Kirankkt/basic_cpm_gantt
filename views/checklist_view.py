# views/checklist_view.py
import streamlit as st
import pandas as pd
from datetime import date
from sqlalchemy import text

from database import engine, _normalise_id   # _normalise_id exists in project_view

def show_checklist_view() -> None:
    st.set_page_config(page_title="Daily Checklist", layout="centered")
    st.title("✔️ Daily Task Checklist")

    # list projects loaded at app start
    proj_names = list(st.session_state.all_projects.keys())
    if not proj_names:
        st.warning("No projects found. Import one first.")
        return

    project_name = st.selectbox("Project", proj_names)
    pid = st.session_state.all_projects[project_name]

    today = date.today().toordinal()

    df = pd.read_sql(
        text(
            """
            SELECT task_id_str, description
            FROM tasks
            WHERE project_id=:pid
              AND status!='Complete'
              AND es<=:today AND ef>=:today
            ORDER BY id
            """
        ),
        engine,
        params={"pid": pid, "today": today},
    )

    if df.empty:
        st.success("All scheduled tasks are already complete 🎉")
        return

    # checklist UI
    options = df["task_id_str"] + " — " + df["description"]
    checked = st.multiselect("Mark tasks finished this shift:", options.tolist())

    if st.button("Save progress", type="primary"):
        if not checked:
            st.info("Nothing selected.")
            return
        tids = [opt.split(" — ")[0] for opt in checked]
        tids = [_normalise_id(t) for t in tids]

        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    UPDATE tasks
                       SET status='Complete'
                     WHERE project_id=:pid
                       AND task_id_str = ANY(:tids)
                    """
                ),
                {"pid": pid, "tids": tids},
            )
        st.success("Progress recorded!")
        st.experimental_rerun()
