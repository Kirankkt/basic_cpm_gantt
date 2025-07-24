"""
Planner dashboard: upload → edit → calculate CPM / Gantt / network diagram.
"""

from datetime import date, timedelta
from typing import List

import networkx as nx
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import re
import streamlit as st
from sqlalchemy import text

from cpm_logic import calculate_cpm
from database import (
    engine,
    get_all_projects,
    get_project_data_from_db,
    import_df_to_db,
    save_tasks_to_db,
)
from utils import get_sample_data

# ──────────────────────────────────────────────────────────────────────────────
def show_project_view() -> None:
    # ── callbacks ────────────────────────────────────────────────────────────
    def _process_uploaded_file() -> None:
        up = st.session_state.get("file_uploader")
        if not up:
            return
        try:
            project_name = up.name.rsplit(".", 1)[0]
            df = pd.read_csv(up) if up.name.endswith(".csv") else pd.read_excel(up)
            new_id = import_df_to_db(df, project_name)
            st.session_state.update(
                {
                    "all_projects": get_all_projects(),
                    "current_project_id": new_id,
                    "project_df": get_project_data_from_db(new_id),
                    "cpm_results": None,
                }
            )
            st.success(f"Imported **{project_name}**")
        except Exception as exc:  # pylint: disable=broad-except
            st.error(f"Upload failed: {exc}")

    def _switch_project() -> None:
        name = st.session_state.project_selector
        if name:
            pid = st.session_state.all_projects[name]
            st.session_state.current_project_id = pid
            st.session_state.project_df = get_project_data_from_db(pid)
            st.session_state.cpm_results = None

    # ── initial session state ────────────────────────────────────────────────
    st.session_state.setdefault("all_projects", get_all_projects())
    st.session_state.setdefault(
        "current_project_id",
        next(iter(st.session_state.all_projects.values()), None),
    )
    st.session_state.setdefault(
        "project_df", get_project_data_from_db(st.session_state.current_project_id)
    )
    st.session_state.setdefault("cpm_results", None)

    # ── sidebar nav handled in app.py ────────────────────────────────────────
    st.header("📂 Project Selection & Setup")

    names: List[str] = list(st.session_state.all_projects.keys())
    cur_name = next(
        (n for n, pid in st.session_state.all_projects.items()
         if pid == st.session_state.current_project_id),
        "",
    )
    st.selectbox(
        "Select Project",
        names,
        index=names.index(cur_name) if cur_name in names else 0,
        key="project_selector",
        on_change=_switch_project,
    )

    with st.expander("Import New Project / Load Sample"):
        st.file_uploader(
            "Upload CSV / Excel",
            type=["csv", "xlsx"],
            key="file_uploader",
            on_change=_process_uploaded_file,
        )
        if st.button("Load Sample Data"):
            pid = import_df_to_db(get_sample_data(), "Demo Project")
            st.session_state.update(
                {
                    "all_projects": get_all_projects(),
                    "current_project_id": pid,
                    "project_df": get_project_data_from_db(pid),
                    "cpm_results": None,
                }
            )
            st.rerun()

    # ── project calendar start date ──────────────────────────────────────────
    with engine.begin() as conn:
        cur_start = conn.execute(
            text("SELECT start_date FROM projects WHERE id=:pid"),
            {"pid": st.session_state.current_project_id},
        ).scalar()
    picked_date = st.date_input(
        "Project calendar **start date**",
        value=cur_start or date.today(),
        key="start_date_picker",
    )

    # persist when changed
    if picked_date != cur_start:
        with engine.begin() as conn:
            conn.execute(
                text("UPDATE projects SET start_date=:d WHERE id=:pid"),
                {"d": picked_date, "pid": st.session_state.current_project_id},
            )

    st.divider()

    # ── task editor ──────────────────────────────────────────────────────────
    st.header("📝 Task Planning & Status")

    if st.session_state.project_df.empty:
        st.info("No tasks yet – upload a schedule above.")
        return

    column_cfg = {
        "Status": st.column_config.SelectboxColumn(
            "Status",
            options=["Not Started", "In Progress", "Complete"],
            required=True,
        )
    }
    edited_df = st.data_editor(
        st.session_state.project_df,
        column_config=column_cfg,
        num_rows="dynamic",
        use_container_width=True,
    )

    col_calc, col_export = st.columns([1.5, 1])
    with col_calc:
        if st.button("Calculate & Save", type="primary"):
            # validation
            if edited_df["Task ID"].isna().any() or (edited_df["Task ID"] == "").any():
                st.error("Task ID cannot be empty.")
                st.stop()
            dupes = edited_df["Task ID"].str.strip().str.upper().duplicated()
            if dupes.any():
                st.error(f"Duplicate Task ID: {edited_df['Task ID'][dupes].iloc[0]}")
                st.stop()

            try:
                cpm_df = calculate_cpm(edited_df.copy())
            except ValueError as exc:
                st.error(str(exc))
                st.stop()

            # merge computed cols back
            merged = edited_df.merge(
                cpm_df[["Task ID", "ES", "EF"]],
                on="Task ID",
                how="left",
            )
            save_tasks_to_db(merged, st.session_state.current_project_id)
            st.session_state.project_df = merged
            st.session_state.cpm_results = cpm_df
            st.success("Saved 🚀")

    with col_export:
        st.download_button(
            "Export CSV",
            edited_df.to_csv(index=False).encode(),
            "schedule_backup.csv",
            "text/csv",
        )

    # ── results area ─────────────────────────────────────────────────────────
    if st.session_state.cpm_results is None:
        return

    cpm_df = st.session_state.cpm_results
    st.header("📊 Results")

    st.subheader("Critical Path Table")
    st.dataframe(cpm_df, use_container_width=True)

    # overall progress
    with st.container(border=True):
        tot = cpm_df["Duration"].sum()
        done = cpm_df.loc[cpm_df["Status"] == "Complete", "Duration"].sum()
        pct = done / tot if tot else 0
        st.markdown("#### Overall progress")
        st.progress(pct, text=f"{pct:.0%}")
        a, b = st.columns(2)
        a.metric("Days done", done, f"of {tot}")
        b.metric(
            "Tasks done",
            f"{(cpm_df['Status'] == 'Complete').sum()}",
            f"of {len(cpm_df)}",
        )

    # build Gantt DF with real dates
    gdf = cpm_df.copy()
    gdf["Start"] = pd.to_datetime(picked_date) + pd.to_timedelta(gdf["ES"] - 1, unit="D")
    gdf["Finish"] = gdf["Start"] + pd.to_timedelta(gdf["Duration"], unit="D")

    def _gcolor(row):
        crit = row["On Critical Path?"] == "Yes"
        return (
            "Critical" if crit else "Non-critical"
        ) + f" ({row['Status']})"

    gdf["GanttColor"] = gdf.apply(_gcolor, axis=1)

    st.plotly_chart(
        px.timeline(
            gdf, x_start="Start", x_end="Finish", y="Task Description",
            color="GanttColor",
            hover_data=["Task ID", "Duration", "Status", "On Critical Path?"],
        ).update_yaxes(autorange="reversed"),
        use_container_width=True,
    )

    st.subheader("CPM Network Diagram")
    st.plotly_chart(_create_network_diagram(cpm_df), use_container_width=True)


# ── network helper ───────────────────────────────────────────────────────────
def _create_network_diagram(df: pd.DataFrame) -> go.Figure:
    G = nx.DiGraph()
    for _, row in df.iterrows():
        G.add_node(row["Task ID"])
        if pd.notna(row["Predecessors"]) and row["Predecessors"]:
            preds = [
                p.strip() for p in re.split(r"[,\s;]+", str(row["Predecessors"])) if p
            ]
            G.add_edges_from([(p, row["Task ID"]) for p in preds])

    try:
        layers = list(nx.topological_generations(G))
        pos = {n: (i, -(layers[i].index(n))) for i in range(len(layers)) for n in layers[i]}
    except nx.NetworkXUnfeasible:
        pos = nx.spring_layout(G, seed=42)

    node_trace = go.Scatter(
        x=[pos[n][0] for n in G],
        y=[pos[n][1] for n in G],
        mode="markers+text",
        text=[n for n in G],
        textposition="middle center",
        hoverinfo="text",
        marker=dict(size=24, line=dict(width=1, color="black")),
    )

    colours, htxt = [], []
    for n in G:
        row = df.loc[df["Task ID"] == n]
        if row.empty:
            colours.append("grey")
            htxt.append(f"{n} (missing)")
        else:
            crit = row["On Critical Path?"].iloc[0] == "Yes"
            colours.append("red" if crit else "skyblue")
            htxt.append(
                f"{n}<br>{row['Task Description'].iloc[0]}<br>Dur {row['Duration'].iloc[0]}"
            )
    node_trace.marker.color = colours
    node_trace.hovertext = htxt
    node_trace.textfont = dict(color="white", size=10)

    arrows = [
        go.layout.Annotation(
            ax=pos[a][0], ay=pos[a][1], x=pos[b][0], y=pos[b][1],
            xref="x", yref="y", axref="x", ayref="y",
            showarrow=True, arrowhead=2, arrowwidth=1, arrowsize=1.5, arrowcolor="#888",
            standoff=12,
        )
        for a, b in G.edges()
    ]

    return go.Figure(
        data=[node_trace],
        layout=go.Layout(
            title="CPM Network Diagram",
            showlegend=False,
            hovermode="closest",
            margin=dict(t=40, b=20, l=5, r=5),
            xaxis=dict(title="Sequence", showgrid=False, zeroline=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            annotations=arrows,
        ),
    )
