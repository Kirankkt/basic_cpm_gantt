# views/project_view.py
import streamlit as st
import pandas as pd
from datetime import date, timedelta
import plotly.express as px
import plotly.graph_objects as go
import networkx as nx
import re

# Import functions from other project files
from database import get_project_data_from_db, save_project_data_to_db, import_df_to_db
from cpm_logic import calculate_cpm
from utils import get_sample_data

# --- Main View Function (No changes needed here) ---
def show_project_view():
    def process_uploaded_file():
        uploader_key = "file_uploader"
        uploaded_file = st.session_state[uploader_key]
        if uploaded_file is not None:
            try:
                df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
                import_df_to_db(df, project_id=1)
                st.session_state.project_df = get_project_data_from_db(project_id=1)
                st.success("File uploaded and project data refreshed!")
            except Exception as e:
                st.error(f"Error processing file: {e}")

    if 'project_df' not in st.session_state:
        st.session_state.project_df = get_project_data_from_db(project_id=1)

    st.header("1. Project Setup")
    start_date = st.date_input("Select Project Start Date", value=date.today())
    st.subheader("Import Project Plan")
    st.info("Upload an Excel or CSV file with columns: 'Task ID', 'Task Description', 'Predecessors', 'Duration'.")
    st.file_uploader(
        "Choose a file", type=['csv', 'xlsx'], key="file_uploader", on_change=process_uploaded_file
    )
    if st.button("Load Sample Project Data"):
        import_df_to_db(get_sample_data(), project_id=1)
        st.session_state.project_df = get_project_data_from_db(project_id=1)
        st.success("Sample data loaded!")
        st.rerun()

    st.divider()
    st.header("2. Task Planning")
    st.markdown("Edit tasks below. Press 'Calculate & Save' to update the project plan.")

    if st.session_state.project_df.empty:
        st.warning("No project data found. Load sample data or upload a file to begin.")
        return

    edited_df = st.data_editor(st.session_state.project_df, num_rows="dynamic", use_container_width=True)

    if st.button("Calculate & Save Project Plan", type="primary"):
        if edited_df is not None:
            save_project_data_to_db(edited_df, project_id=1)
            st.session_state.project_df = edited_df.copy()
            cpm_df = calculate_cpm(st.session_state.project_df.copy())
            st.header("3. Results")
            st.subheader("Critical Path Analysis")
            st.dataframe(cpm_df)
            st.subheader("Gantt Chart")
            fig = create_gantt_chart(cpm_df, start_date)
            st.plotly_chart(fig, use_container_width=True)
            st.subheader("CPM Network Diagram")
            network_fig = create_network_diagram(cpm_df)
            st.plotly_chart(network_fig, use_container_width=True)

# --- Gantt Chart Function (No changes needed here) ---
def create_gantt_chart(df, start_date):
    gantt_df = df.copy()
    project_start_date = pd.to_datetime(start_date)
    gantt_df['Start'] = gantt_df['ES'].apply(lambda x: project_start_date + timedelta(days=int(x - 1)))
    gantt_df['Finish'] = gantt_df['EF'].apply(lambda x: project_start_date + timedelta(days=int(x - 1)))
    fig = px.timeline(
        gantt_df, x_start="Start", x_end="Finish", y="Task Description", color="On Critical Path?",
        title="Project Gantt Chart", color_discrete_map={"Yes": "#FF0000", "No": "#0000FF"},
        hover_data=["Task ID", "Duration", "ES", "EF", "LS", "LF", "Float"]
    )
    fig.update_yaxes(autorange="reversed")
    return fig

# --- DEFINITIVE, PROFESSIONAL Network Diagram Logic ---
def create_network_diagram(df):
    G = nx.DiGraph()
    # Add nodes and edges from the dataframe
    for _, row in df.iterrows():
        G.add_node(row['Task ID'])
        if pd.notna(row['Predecessors']) and row['Predecessors']:
            predecessors = [p.strip() for p in re.split(r'[,.\s;]+', str(row['Predecessors'])) if p]
            for p_task in predecessors:
                if p_task in G:
                    G.add_edge(p_task, row['Task ID'])

    # --- TOPOLOGICAL LAYOUT LOGIC ---
    pos = {}
    try:
        # Arrange nodes in columns based on their sequence in the project flow
        generations = list(nx.topological_generations(G))
        for i, generation in enumerate(generations):
            # Center each column of nodes vertically
            y_start = (len(generation) - 1) / 2.0
            for j, node in enumerate(generation):
                pos[node] = (i, y_start - j)
    except nx.NetworkXUnfeasible:
        # Fallback for cyclic graphs (which shouldn't happen in CPM)
        st.warning("Project has a cyclic dependency! Using a spring layout as a fallback.")
        pos = nx.spring_layout(G, seed=42)

    # Adaptive visuals for clarity on large vs small graphs
    is_large_graph = len(df) > 25
    node_size = 20 if is_large_graph else 35
    standoff_dist = 12 if is_large_graph else 20
    text_inside_node = "" if is_large_graph else [f"<b>{node}</b>" for node in G.nodes()]

    # Create Plotly traces
    node_trace = go.Scatter(
        x=[pos[n][0] for n in G.nodes() if n in pos],
        y=[pos[n][1] for n in G.nodes() if n in pos],
        mode='markers' if is_large_graph else 'markers+text',
        text=text_inside_node, textposition="middle center",
        hoverinfo='text',
        marker=dict(size=node_size, line=dict(width=1, color='Black'))
    )

    # Color nodes and set hover text
    node_colors = []
    node_hover_text = []
    for node in G.nodes():
        if node in pos:
            task_info = df[df['Task ID'] == node]
            if not task_info.empty:
                is_critical = task_info['On Critical Path?'].iloc[0]
                node_colors.append('red' if is_critical == 'Yes' else 'skyblue')
                node_hover_text.append(f"Task: {node}<br>Desc: {task_info['Task Description'].iloc[0]}<br>Duration: {task_info['Duration'].iloc[0]}")
            else:
                node_colors.append('grey')
                node_hover_text.append(f"Task: {node} (Missing)")
    node_trace.marker.color = node_colors
    node_trace.hovertext = node_hover_text
    node_trace.textfont = dict(color='white', size=10)


    # Create annotations for arrows
    arrow_annotations = []
    for edge in G.edges():
        if edge[0] in pos and edge[1] in pos:
            pos_start, pos_end = pos[edge[0]], pos[edge[1]]
            arrow_annotations.append(
                go.layout.Annotation(dict(
                    ax=pos_start[0], ay=pos_start[1], x=pos_end[0], y=pos_end[1],
                    xref='x', yref='y', axref='x', ayref='y', showarrow=True,
                    arrowhead=2, arrowsize=1.5, arrowwidth=1, arrowcolor='#888',
                    standoff=standoff_dist
                ))
            )

    # Define layout and create figure
    layout = go.Layout(
        title=dict(text='CPM Network Diagram', font=dict(size=16)), showlegend=False,
        hovermode='closest', margin=dict(b=20, l=5, r=5, t=40),
        xaxis=dict(title='Project Sequence Level', showgrid=False, zeroline=False, showticklabels=True),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        annotations=arrow_annotations
    )

    fig = go.Figure(data=[node_trace], layout=layout)
    return fig
