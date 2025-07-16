# views/project_view.py
import streamlit as st
import pandas as pd
from datetime import date, timedelta
import plotly.express as px
import plotly.graph_objects as go
import networkx as nx
import re

from database import get_all_projects, get_project_data_from_db, save_tasks_to_db, import_df_to_db
from cpm_logic import calculate_cpm
from utils import get_sample_data

# --- Main View Function ---
def show_project_view():
    def process_uploaded_file():
        uploaded_file = st.session_state.get("file_uploader")
        if uploaded_file:
            try:
                project_name = uploaded_file.name.rsplit('.', 1)[0]
                df = pd.read_csv(uploaded_file) if uploaded_file.name.endswith('.csv') else pd.read_excel(uploaded_file)
                new_project_id = import_df_to_db(df, project_name)
                
                st.session_state.all_projects = get_all_projects()
                st.session_state.current_project_id = new_project_id
                st.session_state.project_df = get_project_data_from_db(new_project_id)
                st.session_state.cpm_results = None
                st.success(f"Successfully imported and switched to project: {project_name}")
            except Exception as e:
                st.error(f"Error processing file: {e}")
    
    def switch_project():
        project_name = st.session_state.project_selector
        if project_name:
            st.session_state.current_project_id = st.session_state.all_projects[project_name]
            st.session_state.project_df = get_project_data_from_db(st.session_state.current_project_id)
            st.session_state.cpm_results = None

    if 'all_projects' not in st.session_state: st.session_state.all_projects = get_all_projects()
    if 'current_project_id' not in st.session_state: st.session_state.current_project_id = next(iter(st.session_state.all_projects.values()), None)
    if 'project_df' not in st.session_state: st.session_state.project_df = get_project_data_from_db(st.session_state.current_project_id)
    if 'cpm_results' not in st.session_state: st.session_state.cpm_results = None

    st.header("1. Project Selection & Setup")
    
    project_names = list(st.session_state.all_projects.keys())
    current_project_name = "No Project Selected"
    current_index = 0
    if st.session_state.current_project_id and project_names:
        try:
            current_project_name = [name for name, id_ in st.session_state.all_projects.items() if id_ == st.session_state.current_project_id][0]
            current_index = project_names.index(current_project_name)
        except (IndexError, ValueError):
            if project_names: current_project_name = project_names[0]; st.session_state.current_project_id = st.session_state.all_projects[current_project_name]

    st.selectbox("Select Project", options=project_names, index=current_index, key="project_selector", on_change=switch_project)
    
    with st.expander("Import New Project or Load Sample"):
        st.file_uploader("Upload Project File", type=['csv', 'xlsx'], key="file_uploader", on_change=process_uploaded_file)
        if st.button("Load Sample Data"):
            project_name = "Default Project"; project_id = import_df_to_db(get_sample_data(), project_name)
            st.session_state.all_projects = get_all_projects(); st.session_state.current_project_id = project_id
            st.session_state.project_df = get_project_data_from_db(project_id); st.session_state.cpm_results = None
            st.success(f"Sample data loaded into '{project_name}'."); st.rerun()

    start_date = st.date_input("Select Project Start Date", value=date.today())
    st.divider()

    st.header("2. Task Planning & Status")
    st.markdown("Edit tasks and update their status below. Changes are saved when you press 'Calculate & Save'.")
    
    if st.session_state.project_df.empty:
        st.warning("No data in this project."); return

    column_config = {
        "Status": st.column_config.SelectboxColumn("Task Status", options=["Not Started", "In Progress", "Complete"], required=True)
    }
    edited_df = st.data_editor(st.session_state.project_df, column_config=column_config, num_rows="dynamic", use_container_width=True)
    
    col1, col2, col3 = st.columns([1.5, 1, 3])
    with col1:
        if st.button("Calculate & Save Project Plan", type="primary"):
            if edited_df['Task ID'].isnull().any() or "" in edited_df['Task ID'].values: st.error("Validation Failed: Task ID cannot be empty.")
            elif edited_df['Task ID'].duplicated().any(): st.error("Validation Failed: Found duplicate Task IDs.")
            else:
                try:
                    save_tasks_to_db(edited_df, st.session_state.current_project_id)
                    st.session_state.project_df = edited_df.copy()
                    st.session_state.cpm_results = calculate_cpm(st.session_state.project_df.copy())
                except ValueError: st.error("Calculation Failed: 'Duration' must be a number.")
                except Exception as e: st.error(f"An unexpected error occurred: {e}")
    with col2:
        st.download_button("Export as CSV", edited_df.to_csv(index=False).encode('utf-8'), f"{current_project_name}_backup.csv", 'text/csv')

    if st.session_state.cpm_results is not None:
        cpm_df = st.session_state.cpm_results
        
        st.header("3. Results & Progress")
        
        with st.container(border=True):
            total_duration = cpm_df['Duration'].sum()
            completed_duration = cpm_df[cpm_df['Status'] == 'Complete']['Duration'].sum()
            progress = (completed_duration / total_duration) if total_duration > 0 else 0
            st.markdown("#### Overall Project Progress")
            st.progress(progress, text=f"{progress:.0%} Complete")
            p_col1, p_col2 = st.columns(2)
            p_col1.metric("Days Completed", f"{completed_duration}", f"of {total_duration} total days")
            p_col2.metric("Tasks Completed", f"{len(cpm_df[cpm_df['Status'] == 'Complete'])}", f"of {len(cpm_df)} total tasks")

        st.subheader("Gantt Chart")
        gantt_df = cpm_df.copy()
        gantt_df['Start'] = gantt_df['ES'].apply(lambda x: pd.to_datetime(start_date) + timedelta(days=int(x - 1)))
        gantt_df['Finish'] = gantt_df['EF'].apply(lambda x: pd.to_datetime(start_date) + timedelta(days=int(x - 1)))
        
        def get_gantt_color(row):
            if row['On Critical Path?'] == 'Yes':
                return 'Critical (Complete)' if row['Status'] == 'Complete' else 'Critical (Active)'
            else:
                return 'Non-Critical (Complete)' if row['Status'] == 'Complete' else 'Non-Critical (Active)'
        gantt_df['GanttColor'] = gantt_df.apply(get_gantt_color, axis=1)

        with st.container(border=True):
            st.write("Filter Controls")
            f_col1, f_col2 = st.columns(2);
            with f_col1:
                show_critical_only = st.checkbox("Show only critical path tasks")
                
                # --- THIS IS THE FIX: Changed back to multiselect ---
                task_list = sorted(gantt_df['Task Description'].tolist())
                selected_tasks = st.multiselect("Search for Specific Tasks", options=task_list)
                
            with f_col2:
                phases = sorted(list(set(gantt_df['Task ID'].str.split('-').str[0].dropna())))
                selected_phases = st.multiselect("Filter by Project Phase", options=phases)
                min_date, max_date = gantt_df['Start'].min().date(), gantt_df['Finish'].max().date()
                date_range = st.date_input("Filter by Date Range", value=(min_date, max_date), min_value=min_date, max_value=max_date)

        filtered_df = gantt_df
        if show_critical_only: filtered_df = filtered_df[filtered_df['On Critical Path?'] == 'Yes']
        if selected_phases: filtered_df = filtered_df[filtered_df['Task ID'].str.startswith(tuple(selected_phases))]
        
        # --- THIS IS THE FIX: Changed to handle a list from multiselect ---
        if selected_tasks:
            filtered_df = filtered_df[filtered_df['Task Description'].isin(selected_tasks)]
            
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
        df, x_start="Start", x_end="Finish", y="Task Description",
        color="GanttColor",
        color_discrete_map={
            'Critical (Active)': 'red',
            'Non-Critical (Active)': 'blue',
            'Critical (Complete)': '#F1948A',
            'Non-Critical (Complete)': '#AED6F1'
        },
        hover_data=["Task ID", "Duration", "Status", "On Critical Path?"]
    )
    fig.update_layout(legend_title_text='Task Status')
    fig.update_yaxes(autorange="reversed")
    return fig

def create_network_diagram(df):
    G = nx.DiGraph()
    for _, row in df.iterrows():
        G.add_node(row['Task ID'])
        if pd.notna(row['Predecessors']) and row['Predecessors']:
            predecessors = [p.strip() for p in re.split(r'[,.\s;]+', str(row['Predecessors'])) if p]
            for p_task in predecessors:
                if p_task in G: G.add_edge(p_task, row['Task ID'])
    try:
        generations = list(nx.topological_generations(G))
        pos = {}
        for i, generation in enumerate(generations):
            y_start = (len(generation) - 1) / 2.0
            for j, node in enumerate(generation): pos[node] = (i, y_start - j)
    except nx.NetworkXUnfeasible:
        st.warning("Cyclic dependency detected!"); pos = nx.spring_layout(G, seed=42)
        
    is_large_graph = len(df) > 25
    node_size = 20 if is_large_graph else 35; standoff_dist = 12 if is_large_graph else 20
    text_inside_node = "" if is_large_graph else [f"<b>{node}</b>" for node in G.nodes()]
    node_trace = go.Scatter(
        x=[pos[n][0] for n in G.nodes() if n in pos], y=[pos[n][1] for n in G.nodes() if n in pos],
        mode='markers' if is_large_graph else 'markers+text', text=text_inside_node, textposition="middle center", 
        hoverinfo='text', marker=dict(size=node_size, line=dict(width=1, color='Black'))
    )
    node_colors, node_hover_text = [], []
    for node in G.nodes():
        if node in pos:
            task_info = df[df['Task ID'] == node]
            if not task_info.empty:
                is_critical = task_info['On Critical Path?'].iloc[0]
                node_colors.append('red' if is_critical == 'Yes' else 'skyblue')
                node_hover_text.append(f"Task: {node}<br>Desc: {task_info['Task Description'].iloc[0]}<br>Duration: {task_info['Duration'].iloc[0]}")
            else:
                node_colors.append('grey'); node_hover_text.append(f"Task: {node} (Missing)")
    node_trace.marker.color = node_colors; node_trace.hovertext = node_hover_text
    node_trace.textfont = dict(color='white', size=10)
    arrow_annotations = []
    for edge in G.edges():
        if edge[0] in pos and edge[1] in pos:
            pos_start, pos_end = pos[edge[0]], pos[edge[1]]
            arrow_annotations.append(go.layout.Annotation(dict(ax=pos_start[0], ay=pos_start[1], x=pos_end[0], y=pos_end[1], xref='x', yref='y', axref='x', ayref='y', showarrow=True, arrowhead=2, arrowsize=1.5, arrowwidth=1, arrowcolor='#888', standoff=standoff_dist)))
    layout = go.Layout(
        title=dict(text='CPM Network Diagram', font=dict(size=16)), showlegend=False, hovermode='closest', 
        margin=dict(b=20, l=5, r=5, t=40),
        xaxis=dict(title='Project Sequence Level', showgrid=False, zeroline=False, showticklabels=True),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        annotations=arrow_annotations
    )
    fig = go.Figure(data=[node_trace], layout=layout)
    return fig
