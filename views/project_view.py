# views/project_view.py
import streamlit as st
import pandas as pd
from datetime import date, timedelta
import plotly.express as px
import plotly.graph_objects as go
import networkx as nx
import re

# Updated database function imports
# THIS LINE IS FIXED
from database import get_all_projects, get_project_data_from_db, save_tasks_to_db, import_df_to_db
from cpm_logic import calculate_cpm
from utils import get_sample_data

# --- Main View Function ---
def show_project_view():

    # --- Callbacks for State Management ---
    def process_uploaded_file():
        uploaded_file = st.session_state.get("file_uploader")
        if uploaded_file:
            try:
                project_name = uploaded_file.name.rsplit('.', 1)[0] # Use filename as project name
                df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
                new_project_id = import_df_to_db(df, project_name)
                
                # Automatically switch to the new project
                st.session_state.current_project_id = new_project_id
                st.session_state.project_df = get_project_data_from_db(new_project_id)
                st.session_state.cpm_results = None
                st.success(f"Successfully imported and switched to project: {project_name}")
            except Exception as e:
                st.error(f"Error processing file: {e}")
    
    def switch_project():
        project_name = st.session_state.project_selector
        st.session_state.current_project_id = st.session_state.all_projects[project_name]
        st.session_state.project_df = get_project_data_from_db(st.session_state.current_project_id)
        st.session_state.cpm_results = None # Clear results when switching

    # --- Initialize Session State ---
    if 'all_projects' not in st.session_state:
        st.session_state.all_projects = get_all_projects()
    if 'current_project_id' not in st.session_state:
        st.session_state.current_project_id = next(iter(st.session_state.all_projects.values()), None)
    if 'project_df' not in st.session_state:
        st.session_state.project_df = get_project_data_from_db(st.session_state.current_project_id)
    if 'cpm_results' not in st.session_state:
        st.session_state.cpm_results = None

    # --- UI ---
    st.header("1. Project Selection & Setup")
    
    project_names = list(st.session_state.all_projects.keys())
    try:
        current_project_name = [name for name, id in st.session_state.all_projects.items() if id == st.session_state.current_project_id][0]
        current_index = project_names.index(current_project_name)
    except (IndexError, ValueError):
        current_index = 0
    
    st.selectbox("Select Project", options=project_names, index=current_index, key="project_selector", on_change=switch_project)
    
    with st.expander("Import New Project or Load Sample"):
        st.file_uploader("Upload Project File (CSV or Excel)", type=['csv', 'xlsx'], key="file_uploader", on_change=process_uploaded_file)
        if st.button("Load Sample Project Data (Overwrites 'Default Project')"):
            import_df_to_db(get_sample_data(), "Default Project")
            st.session_state.all_projects = get_all_projects()
            st.success("Sample data loaded into 'Default Project'.")

    start_date = st.date_input("Select Project Start Date", value=date.today())
    st.divider()

    # --- Data Editor and Controls ---
    st.header("2. Task Planning")
    st.markdown("Edit tasks below, then calculate. You can export your edits at any time.")
    
    if st.session_state.project_df.empty:
        st.warning("No data in this project. Upload a file or load sample data.")
        return

    edited_df = st.data_editor(st.session_state.project_df, num_rows="dynamic", use_container_width=True)
    
    col1, col2, col3 = st.columns([1.5, 1, 3])
    with col1:
        if st.button("Calculate & Save Project Plan", type="primary"):
            if edited_df['Task ID'].isnull().any() or "" in edited_df['Task ID'].values:
                st.error("Validation Failed: One or more tasks has an empty 'Task ID'.")
            elif edited_df['Task ID'].duplicated().any():
                st.error("Validation Failed: Found duplicate 'Task ID's. Please ensure every ID is unique.")
            else:
                try:
                    # THIS LINE IS FIXED
                    save_tasks_to_db(edited_df, st.session_state.current_project_id)
                    st.session_state.project_df = edited_df.copy()
                    st.session_state.cpm_results = calculate_cpm(st.session_state.project_df.copy())
                except ValueError:
                    st.error("Calculation Failed: Please ensure the 'Duration' column contains only valid numbers.")
                except Exception as e:
                    st.error(f"An unexpected error occurred: {e}")
    
    with col2:
        st.download_button(
            label="Export as CSV",
            data=edited_df.to_csv(index=False).encode('utf-8'),
            file_name=f"{current_project_name}_backup.csv",
            mime='text/csv',
        )

    # --- Results Display Block ---
    if st.session_state.cpm_results is not None:
        cpm_df = st.session_state.cpm_results
        st.header("3. Results")
        st.subheader("Critical Path Analysis")
        st.dataframe(cpm_df)
        st.subheader("Gantt Chart")
        gantt_df = cpm_df.copy()
        gantt_df['Start'] = gantt_df['ES'].apply(lambda x: pd.to_datetime(start_date) + timedelta(days=int(x - 1)))
        gantt_df['Finish'] = gantt_df['EF'].apply(lambda x: pd.to_datetime(start_date) + timedelta(days=int(x - 1)))
        
        with st.container(border=True):
            st.write("Filter Controls")
            f_col1, f_col2 = st.columns(2)
            with f_col1:
                show_critical_only = st.checkbox("Show only critical path tasks")
                search_term = st.text_input("Search by Task Description")
            with f_col2:
                phases = sorted(list(set(gantt_df['Task ID'].str.split('-').str[0].dropna())))
                selected_phases = st.multiselect("Filter by Project Phase", options=phases)
                min_date, max_date = gantt_df['Start'].min().date(), gantt_df['Finish'].max().date()
                date_range = st.date_input("Filter by Date Range", value=(min_date, max_date), min_value=min_date, max_value=max_date)

        filtered_df = gantt_df
        if show_critical_only: filtered_df = filtered_df[filtered_df['On Critical Path?'] == 'Yes']
        if selected_phases: filtered_df = filtered_df[filtered_df['Task ID'].str.startswith(tuple(selected_phases))]
        if search_term: filtered_df = filtered_df[filtered_df['Task Description'].str.contains(search_term, case=False, na=False)]
        if len(date_range) == 2:
            start_filter, end_filter = pd.to_datetime(date_range[0]), pd.to_datetime(date_range[1])
            filtered_df = filtered_df[(filtered_df['Start'] <= end_filter) & (filtered_df['Finish'] >= start_filter)]

        fig = create_gantt_chart(filtered_df)
        st.plotly_chart(fig, use_container_width=True)

        st.subheader("CPM Network Diagram")
        network_fig = create_network_diagram(cpm_df)
        st.plotly_chart(network_fig, use_container_width=True)

# (No changes to the functions below this line)
def create_gantt_chart(df):
    fig = px.timeline(
        df, x_start="Start", x_end="Finish", y="Task Description", color="On Critical Path?",
        title="Project Gantt Chart", color_discrete_map={"Yes": "#FF0000", "No": "#0000FF"},
        hover_data=["Task ID", "Duration", "ES", "EF", "LS", "LF", "Float"]
    )
    fig.update_yaxes(autorange="reversed")
    return fig

def create_network_diagram(df):
    G = nx.DiGraph()
    for _, row in df.iterrows():
        G.add_node(row['Task ID'])
        if pd.notna(row['Predecessors']) and row['Predecessors']:
            predecessors = [p.strip() for p in re.split(r'[,.\s;]+', str(row['Predecessors'])) if p]
            for p_task in predecessors:
                if p_task in G:
                    G.add_edge(p_task, row['Task ID'])
    try:
        generations = list(nx.topological_generations(G))
        pos = {}
        for i, generation in enumerate(generations):
            y_start = (len(generation) - 1) / 2.0
            for j, node in enumerate(generation):
                pos[node] = (i, y_start - j)
    except nx.NetworkXUnfeasible:
        st.warning("Project has a cyclic dependency! Using a spring layout as a fallback.")
        pos = nx.spring_layout(G, seed=42)
        
    is_large_graph = len(df) > 25
    node_size = 20 if is_large_graph else 35
    standoff_dist = 12 if is_large_graph else 20
    text_inside_node = "" if is_large_graph else [f"<b>{node}</b>" for node in G.nodes()]
    node_trace = go.Scatter(
        x=[pos[n][0] for n in G.nodes() if n in pos], y=[pos[n][1] for n in G.nodes() if n in pos],
        mode='markers' if is_large_graph else 'markers+text',
        text=text_inside_node, textposition="middle center", hoverinfo='text',
        marker=dict(size=node_size, line=dict(width=1, color='Black'))
    )
    node_colors, node_hover_text = [], []
    for node in G.nodes():
        if node in pos:
            task_info = df[df['Task ID'] == node]
            if not task_info.empty:
                is_critical = task_info['On Critical Path?'].iloc[0]
                node_colors.append('red' if is_critical == 'Yes' else 'skyblue')
                node_hover_text.append(f"Task: {d}{task_info['Task Description'].iloc[0]}<br>Duration: {task_info['Duration'].iloc[0]}")
            else:
                node_colors.append('grey'); node_hover_text.append(f"Task: {node} (Missing)")
    node_trace.marker.color = node_colors; node_trace.hovertext = node_hover_text
    node_trace.textfont = dict(color='white', size=10)
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
    layout = go.Layout(
        title=dict(text='CPM Network Diagram', font=dict(size=16)), showlegend=False,
        hovermode='closest', margin=dict(b=20, l=5, r=5, t=40),
        xaxis=dict(title='Project Sequence Level', showgrid=False, zeroline=False, showticklabels=True),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        annotations=arrow_annotations
    )
    fig = go.Figure(data=[node_trace], layout=layout)
    return fig
