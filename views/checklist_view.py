# views/checklist_view.py
import streamlit as st
import pandas as pd
from datetime import date
from views.project_view import _normalise_id   # reuse helper
from database import get_project_data_from_db
from cpm_logic import calculate_cpm            # NEW

def show_checklist_view() -> None:
    st.set_page_config(page_title="Daily Checklist", layout="centered")
    st.title("✔️ Daily Task Checklist")

    projects = list(st.session_state.all_projects.keys())
    if not projects:
        st.warning("No projects found. Import one first."); return

    proj_name = st.selectbox("Project", projects)
    pid = st.session_state.all_projects[proj_name]

    # --- load tasks then compute ES/EF on-the-fly ---
    raw_df = get_project_data_from_db(pid)
    if raw_df.empty:
        st.info("Project has no tasks yet."); return

    cpm_df = calculate_cpm(raw_df.copy())
    today_ord = date.today().toordinal()

    today_df = cpm_df[
        (cpm_df["Status"] != "Complete") &
        (cpm_df["ES"] <= today_ord) &
        (cpm_df["EF"] >= today_ord)
    ]

    if today_df.empty:
        st.success("All scheduled tasks are already complete for today 🎉")
        return

    options = today_df["Task ID"] + " — " + today_df["Task Description"]
    picked = st.multiselect("Mark tasks finished this shift:", options.tolist())

    if st.button("Save progress", type="primary"):
        if not picked:
            st.info("Nothing selected."); return
        to_complete = [_normalise_id(x.split(" — ")[0]) for x in picked]

        # update in database
        today_df.loc[today_df["Task ID"].isin(to_complete), "Status"] = "Complete"
        from database import save_tasks_to_db
        save_tasks_to_db(today_df[["Task ID","Task Description","Predecessors",
                                   "Duration","Status"]], pid)

        st.success("Progress recorded!")
        st.experimental_rerun()
