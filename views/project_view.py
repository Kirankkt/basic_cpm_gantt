# views/project_view.py
import streamlit as st
import pandas as pd
from datetime import date, timedelta
import plotly.express as px
import plotly.graph_objects as go
import networkx as nx
import re, unicodedata                     # NEW
from database import (
    get_all_projects,
    get_project_data_from_db,
    save_tasks_to_db,
    import_df_to_db,
)
from cpm_logic import calculate_cpm
from utils import get_sample_data

# ────────────────────────────────────────────────────────────────
#  Helper functions (NEW)
# ────────────────────────────────────────────────────────────────
def _normalise_id(s: str) -> str:
    """
    Trim, fold unicode, replace fancy dashes with ASCII hyphen,
    upper‑case the string. Empty/NaN → "".
    """
    if pd.isna(s):
        return ""
    s = unicodedata.normalize("NFKC", str(s)).strip().upper()
    return s.replace("–", "-").replace("—", "-")


def _check_for_dangling_preds(df: pd.DataFrame) -> set[str]:
    """Return {predecessorID,…} tokens that are not in the Task ID column."""
    task_ids = set(df["Task ID"])
    dangling = {
        _normalise_id(tok)
        for preds in df["Predecessors"].dropna()
        for tok in re.split(r"[,\s;]+", preds)
        if _normalise_id(tok) and _normalise_id(tok) not in task_ids
    }
    return dangling


# ────────────────────────────────────────────────────────────────
#  Main View
# ────────────────────────────────────────────────────────────────
def show_project_view() -> None:
    # ── Helper callbacks ────────────────────────────────────────
    def _process_uploaded_file() -> None:
        uploaded = st.session_state.get("file_uploader")
        if not uploaded:
            return
        try:
            project_name = uploaded.name.rsplit(".", 1)[0]
            df = (
                pd.read_csv(uploaded)
                if uploaded.name.endswith(".csv")
                else pd.read_excel(uploaded)
            )
            # NORMALISE IDs on import (NEW)
            df["Task ID"] = df["Task ID"].apply(_normalise_id)

            new_id = import_df_to_db(df, project_name)
            st.session_state.all_projects = get_all_projects()
            st.session_state.current_project_id = new_id
            st.session_state.project_df = get_project_data_from_db(new_id)
            st.session_state.cpm_results = None
            st.success(f"Imported and switched to **{project_name}**")
        except Exception as exc:  # pylint: disable=broad-except
            st.error(f"Error processing file: {exc}")

    def _switch_project() -> None:
        name = st.session_state.project_selector
        if name:
            st.session_state.current_project_id = st.session_state.all_projects[name]
            st.session_state.project_df = get_project_data_from_db(
                st.session_state.current_project_id
            )
            st.session_state.cpm_results = None

    # ── Session‑state bootstrap ─────────────────────────────────
    if "all_projects" not in st.session_state:
        st.session_state.all_projects = get_all_projects()
    if "current_project_id" not in st.session_state:
        st.session_state.current_project_id = next(
            iter(st.session_state.all_projects.values()), None
        )
    if "project_df" not in st.session_state:
        st.session_state.project_df = get_project_data_from_db(
            st.session_state.current_project_id
        )
    if "cpm_results" not in st.session_state:
        st.session_state.cpm_results = None

    # ── 1. Project selection & setup ────────────────────────────
    st.header("1  Project Selection & Setup")

    project_names = list(st.session_state.all_projects.keys())
    cur_name = (
        [
            n
            for n, pid in st.session_state.all_projects.items()
            if pid == st.session_state.current_project_id
        ][0]
        if st.session_state.current_project_id
        else "No Project Selected"
    )
    cur_idx = project_names.index(cur_name) if cur_name in project_names else 0

    st.selectbox(
        "Select Project",
        options=project_names,
        index=cur_idx,
        key="project_selector",
        on_change=_switch_project,
    )

    with st.expander("Import New Project or Load Sample"):
        st.file_uploader(
            "Upload Project File",
            type=["csv", "xlsx"],
            key="file_uploader",
            on_change=_process_uploaded_file,
        )
        if st.button("Load Sample Data"):
            pname = "Default Project"
            pid = import_df_to_db(get_sample_data(), pname)
            st.session_state.all_projects = get_all_projects()
            st.session_state.current_project_id = pid
            st.session_state.project_df = get_project_data_from_db(pid)
            st.session_state.cpm_results = None
            st.success(f"Sample data loaded into **{pname}**")
            st.rerun()

    start_date = st.date_input("Select Project Start Date", value=date.today())
    st.divider()

    # ── 2. Task planning & status ───────────────────────────────
    st.header("2  Task Planning & Status")
    st.markdown(
        "Edit tasks and update their status below. **Press “Calculate & Save”** "
        "to persist changes."
    )

    if st.session_state.project_df.empty:
        st.warning("No data in this project.")
        return

    column_config = {
        "Status": st.column_config.SelectboxColumn(
            "Task Status",
            options=["Not Started", "In Progress", "Complete"],
            required=True,
        )
    }
    edited_df = st.data_editor(
        st.session_state.project_df,
        column_config=column_config,
        num_rows="dynamic",
        use_container_width=True,
    )

    col_calc, col_export, _ = st.columns([1.5, 1, 3])

    with col_calc:
        if st.button("Calculate & Save Project Plan", type="primary"):
            # ── Validation (NEW) ────────────────────────────────
            edited_df["Task ID"] = edited_df["Task ID"].apply(_normalise_id)
            dangling = _check_for_dangling_preds(edited_df)

            if "" in edited_df["Task ID"].values:
                st.error("Task ID cannot be empty.")
            elif edited_df["Task ID"].duplicated().any():
                st.error("Duplicate Task IDs detected.")
            elif dangling:
                st.error(
                    "Predecessor ID(s) not found in the Task ID column: "
                    + ", ".join(sorted(dangling))
                )
            else:
                try:
                    save_tasks_to_db(edited_df, st.session_state.current_project_id)
                    st.session_state.project_df = edited_df.copy()
                    st.session_state.cpm_results = calculate_cpm(
                        st.session_state.project_df.copy()
                    )
                except ValueError:
                    st.error("`Duration` must be numeric.")
                except Exception as exc:  # pylint: disable=broad-except
                    st.error(f"Unexpected error: {exc}")

    with col_export:
        st.download_button(
            "Export as CSV",
            edited_df.to_csv(index=False).encode(),
            f"{cur_name}_backup.csv",
            "text/csv",
        )

    # ── 3. Results ──────────────────────────────────────────────
    if st.session_state.cpm_results is None:
        return

    cpm_df = st.session_state.cpm_results

    st.header("3  Results & Progress")

    st.subheader("Critical Path Analysis")
    st.dataframe(cpm_df, use_container_width=True)

    # ▸ Overall progress bar
    with st.container(border=True):
        total_dur = cpm_df["Duration"].sum()
        done_dur = cpm_df[cpm_df["Status"] == "Complete"]["Duration"].sum()
        prog = done_dur / total_dur if total_dur else 0
        st.markdown("#### Overall Project Progress")
        st.progress(prog, text=f"{prog:.0%} Complete")
        m1, m2 = st.columns(2)
        m1.metric("Days Completed", f"{done_dur}", f"of {total_dur}")
        m2.metric(
            "Tasks Completed",
            f"{(cpm_df['Status'] == 'Complete').sum()}",
            f"of {len(cpm_df)}",
        )

    # ▸ Build calendar dates for Gantt
    gantt_df = cpm_df.copy()
    gantt_df["Start"] = pd.to_datetime(start_date) + pd.to_timedelta(
        gantt_df["ES"] - 1, unit="D"
    )
    gantt_df["Finish"] = gantt_df["Start"] + pd.to_timedelta(
        gantt_df["Duration"], unit="D"
    )

    def _g_color(row):
        critical = row["On Critical Path?"] == "Yes"
        stt = row["Status"]
        if critical:
            return (
                "Critical (Complete)"
                if stt == "Complete"
                else "Critical (In Progress)"
                if stt == "In Progress"
                else "Critical (Not Started)"
            )
        return (
            "Non-Critical (Complete)"
            if stt == "Complete"
            else "Non-Critical (In Progress)"
            if stt == "In Progress"
            else "Non-Critical (Not Started)"
        )

    gantt_df["GanttColor"] = gantt_df.apply(_g_color, axis=1)

    # ▸ Filter controls
    st.write("Filter Controls")
    fc1, fc2 = st.columns(2)

    with fc1:
        show_crit_only = st.checkbox("Show only critical path tasks")
        sel_tasks = st.multiselect(
            "Search for Specific Tasks", options=sorted(gantt_df["Task Description"])
        )
    with fc2:
        sel_phases = st.multiselect(
            "Filter by Project Phase",
            options=sorted({t.split("-")[0] for t in gantt_df["Task ID"]}),
        )
        buffer = timedelta(days=14)
        min_date = (gantt_df["Start"].min() - buffer).date()
        max_date = (gantt_df["Finish"].max() + buffer).date()
        date_rng = st.date_input("Filter by Date Range", value=(min_date, max_date))

    # ▸ Apply filters
    if sel_tasks:
        filt_df = gantt_df[gantt_df["Task Description"].isin(sel_tasks)]
    else:
        filt_df = gantt_df.copy()
        if show_crit_only:
            filt_df = filt_df[filt_df["On Critical Path?"] == "Yes"]
        if sel_phases:
            filt_df = filt_df[filt_df["Task ID"].str.startswith(tuple(sel_phases))]
        if len(date_rng) == 2:
            d0, d1 = map(pd.to_datetime, date_rng)
            filt_df = filt_df[(filt_df["Start"] <= d1) & (filt_df["Finish"] >= d0)]

    st.plotly_chart(create_gantt_chart(filt_df), use_container_width=True)

    st.subheader("CPM Network Diagram")
    st.plotly_chart(create_network_diagram(cpm_df), use_container_width=True)


# ────────────────────────────────────────────────────────────────
#  Plot helpers (Gantt & Network)
# ────────────────────────────────────────────────────────────────
def create_gantt_chart(df: pd.DataFrame) -> go.Figure:
    fig = px.timeline(
        df,
        x_start="Start",
        x_end="Finish",
        y="Task Description",
        color="GanttColor",
        hover_data=["Task ID", "Duration", "Status", "On Critical Path?"],
        color_discrete_map={
            "Critical (In Progress)": "#E74C3C",
            "Critical (Not Started)": "#CD5C5C",
            "Critical (Complete)": "#F5B7B1",
            "Non-Critical (In Progress)": "#3498DB",
            "Non-Critical (Not Started)": "#4169E1",
            "Non-Critical (Complete)": "#AED6F1",
        },
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(legend_title_text="Task Status")
    return fig


def create_network_diagram(df: pd.DataFrame) -> go.Figure:
    G = nx.DiGraph()
    for _, row in df.iterrows():
        G.add_node(row["Task ID"])
        if pd.notna(row["Predecessors"]) and row["Predecessors"]:
            preds = [
                _normalise_id(p)
                for p in re.split(r"[,\s;]+", str(row["Predecessors"]))
                if _normalise_id(p)
            ]
            for p_task in preds:
                G.add_edge(p_task, row["Task ID"])

    # Layout
    try:
        generations = list(nx.topological_generations(G))
        pos = {
            node: (i, (len(gen) - 1) / 2.0 - j)
            for i, gen in enumerate(generations)
            for j, node in enumerate(gen)
        }
    except nx.NetworkXUnfeasible:
        st.warning("Cyclic dependency detected!")
        pos = nx.spring_layout(G, seed=42)

    is_large = len(G) > 25
    node_size = 20 if is_large else 35
    text_inside = "" if is_large else [f"<b>{n}</b>" for n in G.nodes()]

    node_trace = go.Scatter(
        x=[pos[n][0] for n in G.nodes()],
        y=[pos[n][1] for n in G.nodes()],
        mode="markers" if is_large else "markers+text",
        text=text_inside,
        textposition="middle center",
        hoverinfo="text",
        marker=dict(size=node_size, line=dict(width=1, color="Black")),
    )

    colors, hovers = [], []
    for node in G.nodes():
        task = df[df["Task ID"] == node]
        if not task.empty:
            crit = task["On Critical Path?"].iloc[0] == "Yes"
            colors.append("red" if crit else "skyblue")
            hovers.append(
                f"Task: {node}<br>"
                f"Desc: {task['Task Description'].iloc[0]}<br>"
                f"Duration: {task['Duration'].iloc[0]}"
            )
        else:
            colors.append("grey")
            hovers.append(f"Task: {node} (Missing)")

    node_trace.marker.color = colors
    node_trace.hovertext = hovers
    node_trace.textfont = dict(color="white", size=10)

    arrows = []
    standoff = 12 if is_large else 20
    for a, b in G.edges():
        arrows.append(
            go.layout.Annotation(
                ax=pos[a][0],
                ay=pos[a][1],
                x=pos[b][0],
                y=pos[b][1],
                xref="x",
                yref="y",
                axref="x",
                ayref="y",
                showarrow=True,
                arrowhead=2,
                arrowsize=1.5,
                arrowwidth=1,
                arrowcolor="#888",
                standoff=standoff,
            )
        )

    fig = go.Figure(
        data=[node_trace],
        layout=go.Layout(
            title=dict(text="CPM Network Diagram", font=dict(size=16)),
            showlegend=False,
            hovermode="closest",
            margin=dict(t=40, b=20, l=5, r=5),
            xaxis=dict(title="Project Sequence Level", showgrid=False, zeroline=False),
            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
            annotations=arrows,
        ),
    )
    return fig
