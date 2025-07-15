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

# --- Main View Function ---
def show_project_view():
    
    # --- Callback Function to handle file uploads robustly ---
    def process_uploaded_file():
        uploader_key = "file_uploader"
        uploaded_file = st.session_state[uploader_key]
        if uploaded_file is not None:
            try:
                if uploaded_file.name.endswith('.csv'):
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file)
                
                import_df_to_db(df, project_id=1)
                # CRITICAL: Update the session state immediately after import
                st.session_state.project_df = get_project_data_from_db(project_id=1)
                st.success("File uploaded and project data refreshed!")

            except Exception as e:
                st.error(f"Error processing file: {e}")

    # --- Initialize Session State ---
    if 'project_df' not in st.session_state:
        st.session_state.project_df = get_project_data_from_db(project_id=1)

    # --- UI and State Management ---
    st.header("1. Project Setup")
    start_date = st.date_input("Select Project Start Date", value=date.today())
    
    st.subheader("Import Project Plan")
    st.info("Upload an Excel or CSV file with columns: 'Task ID', 'Task Description', 'Predecessors', 'Duration'.")
    
    # THE FIX: Attach the callback to the file uploader
    st.file_uploader(
        "Choose a file",
        type=['csv', 'xlsx'],
        key="file_uploader",
        on_change=process_uploaded_file # This runs the function upon upload
    )

    if st.button("Load Sample Project Data"):
        import_df_to_db(get_sample_data(), project_id=1)
        st.session_state.project_df = get_project_data_from_db(project_id=1)
        st.success("Sample data loaded!")
        st.rerun()

    st.divider()

    # --- Data Editor and Calculation ---
    st.header("2. Task Planning")
    st.markdown("Edit tasks below. Press 'Calculate & Save' to update the project plan.")

    if st.session_state.project_df.empty:
        st.warning("No project data found. Load sample data or upload a file to begin.")
        return

    # The data editor now ALWAYS reflects the true state from session_state
    edited_df = st.data_editor(st.session_state.project_df, num_rows="dynamic", use_container_width=True)

    if st.button("Calculate & Save Project Plan", type="primary"):
        if edited_df is not None:
            save_project_data_to_db(edited_df, project_id=1)
            st.session_state.project_df = edited_df.copy() # Keep state in sync with edits
            
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


# --- (No changes to Gantt Chart or Network Diagram functions below this line) ---
def create_gantt_chart(df, start_date):
    gantt_df = df.copy()
    project_start_date = pd.to_datetime(start_date)
    gantt_df['Start'] = gantt_df['ES'].apply(lambda x: project_start_date + timedelta(days=int(x - 1)))
    gantt_df['Finish'] = gantt_df['EF'].apply(lambda x: project_start_date + timedelta(days=int(x - 1)))
    fig = px.timeline(
        gantt_df,
        x_start="Start",
        x_end="Finish",
        y="Task Description",
        color="On Critical Path?",
        title="Project Gantt Chart",
        color_discrete_map={"Yes": "#FF0000", "No": "#0000FF"},
        hover_data=["Task ID", "Duration", "ES", "EF", "LS", "LF", "Float"]
    )
    fig.update_yaxes(autorange="reversed")
    return fig

def create_network_diagram(df):
    G = nx.DiGraph()
    df['Predecessors'] = df['Predecessors'].astype(str).fillna('')
    for task_id in df['Task ID']:
        G.add_node(task_id)
    for index, row in df.iterrows():
        if row['Predecessors']:
            predecessors = [p.strip() for p in re.split(r'[,.\s;]+', row['Predecessors']) if p]
            for p_task in predecessors:
                if p_task:
                    G.add_edge(p_task, row['Task ID'])
    pos = {}
    y_positions = {}
    for index, row in df.iterrows():
        es = row['ES']
        task_id = row['Task ID']
        y_level = y_positions.get(es, 0)
        pos[task_id] = (es, y_level)
        y_positions[es] = y_level - 1.5
    if pos:
        max_y = max(p[1] for p in pos.values())
        min_y = min(p[1] for p in pos.values())
        y_center = (max_y + min_y) / 2
        for node, (x, y) in pos.items():
            pos[node] = (x, y - y_center)
    arrow_annotations = []
    for edge in G.edges():
        if edge[0] in pos and edge[1] in pos:
            x0, y0 = pos[edge[0]]
            x1, y1 = pos[edge[1]]
            arrow_annotations.append(
                go.layout.Annotation(dict(
                    ax=x0, ay=y0, x=x1, y=y1,
                    xref='x', yref='y', axref='x', ayref='y',
                    showarrow=True, arrowhead=3, arrowsize=2, arrowwidth=1.5, arrowcolor='#888',
                    standoff=25
                ))
            )
    node_x, node_y, node_text, node_color = [], [], [], []
    for node in G.nodes():
        if node in pos:
            x, y = pos[node]
            node_x.append(x)
            node_y.append(y)
            task_info = df[df['Task ID'] == node]
            if not task_info.empty:
                is_critical = task_info['On Critical Path?'].iloc[0]
                node_color.append('red' if is_critical == 'Yes' else 'skyblue')
                node_text.append(f"Task: {node}<br>Desc: {task_info['Task Description'].iloc[0]}<br>Duration: {task_info['Duration'].iloc[0]}")
            else:
                node_color.append('grey')
                node_text.append(f"Task: {node} (Missing)")
    node_trace = go.Scatter(
        x=node_x, y=node_y, mode='markers+text', text=[f"<b>{node}</b>" for node in G.nodes() if node in pos],
        textposition="middle center", hovertext=node_text, hoverinfo='text',
        textfont=dict(color='white', size=12),
        marker=dict(color=node_color, size=45, line=dict(color='Black', width=2))
    )
    layout = go.Layout(
        title=dict(text='<br>CPM Network Diagram', font=dict(size=16)),
        showlegend=False, hovermode='closest', margin=dict(b=20, l=5, r=5, t=40),
        xaxis=dict(title='Project Timeline (Days)', showgrid=True, zeroline=False, showticklabels=True),
        yaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
        annotations=arrow_annotations
    )
    fig = go.Figure(data=[node_trace], layout=layout)
    return fig
