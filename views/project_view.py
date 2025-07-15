# views/project_view.py
import streamlit as st
import pandas as pd
from datetime import date, timedelta
import plotly.express as px
import plotly.graph_objects as go
import networkx as nx

# Import functions from other project files
from database import get_project_data_from_db, save_project_data_to_db, import_df_to_db
from cpm_logic import calculate_cpm
from utils import get_sample_data

# --- Gantt Chart Logic ---
def create_gantt_chart(df, start_date):
    """
    Creates a Gantt chart using Plotly based on a selected start date.
    """
    gantt_df = df.copy()
    project_start_date = pd.to_datetime(start_date)

    # Calculate the 'Start' and 'Finish' dates for the Gantt chart
    gantt_df['Start'] = gantt_df['ES'].apply(lambda x: project_start_date + timedelta(days=int(x - 1)))
    gantt_df['Finish'] = gantt_df['EF'].apply(lambda x: project_start_date + timedelta(days=int(x - 1)))

    fig = px.timeline(
        gantt_df,
        x_start="Start",
        x_end="Finish",
        y="Task Description",
        color="On Critical Path?",
        title="Project Gantt Chart",
        color_discrete_map={"Yes": "#FF0000", "No": "#0000FF"}, # Red for critical, Blue for non-critical
        hover_data=["Task ID", "Duration", "ES", "EF", "LS", "LF", "Float"]
    )
    fig.update_yaxes(autorange="reversed")
    return fig

# --- NEW: Network Diagram Logic ---
def create_network_diagram(df):
    """
    Creates a CPM network diagram using NetworkX and Plotly.
    """
    G = nx.DiGraph()
    for index, row in df.iterrows():
        G.add_node(row['Task ID'])

    for index, row in df.iterrows():
        if row['Predecessors']:
            predecessors = [p.strip() for p in row['Predecessors'].split(',')]
            for p_task in predecessors:
                if p_task:
                    G.add_edge(p_task, row['Task ID'])

    pos = nx.spring_layout(G, k=0.9, iterations=50)

    edge_x = []
    edge_y = []
    for edge in G.edges():
        x0, y0 = pos[edge[0]]
        x1, y1 = pos[edge[1]]
        edge_x.extend([x0, x1, None])
        edge_y.extend([y0, y1, None])

    edge_trace = go.Scatter(
        x=edge_x, y=edge_y,
        line=dict(width=0.5, color='#888'),
        hoverinfo='none',
        mode='lines')

    node_x = []
    node_y = []
    node_text = []
    node_color = []
    for node in G.nodes():
        x, y = pos[node]
        node_x.append(x)
        node_y.append(y)
        node_text.append(node)
        is_critical = df[df['Task ID'] == node]['On Critical Path?'].iloc[0]
        node_color.append('red' if is_critical == 'Yes' else 'skyblue')

    node_trace = go.Scatter(
        x=node_x, y=node_y,
        mode='markers+text',
        text=node_text,
        textposition="top center",
        hoverinfo='text',
        marker=dict(
            showscale=False,
            color=node_color,
            size=20,
            line_width=2))

    fig = go.Figure(data=[edge_trace, node_trace],
                 layout=go.Layout(
                    title='<br>CPM Network Diagram',
                    titlefont_size=16,
                    showlegend=False,
                    hovermode='closest',
                    margin=dict(b=20,l=5,r=5,t=40),
                    xaxis=dict(showgrid=False, zeroline=False, showticklabels=False),
                    yaxis=dict(showgrid=False, zeroline=False, showticklabels=False))
                    )
    return fig


# --- Main View Function ---
def show_project_view():
    st.header("1. Project Setup")

    # --- Feature 1: Adjustable Start Date ---
    start_date = st.date_input("Select Project Start Date", value=date.today())

    # --- Feature 2: File Uploader ---
    st.subheader("Import Project Plan")
    st.info("Upload an Excel or CSV file with columns: 'Task ID', 'Task Description', 'Predecessors', 'Duration'.")
    uploaded_file = st.file_uploader("Choose a file", type=['csv', 'xlsx'])

    if uploaded_file:
        try:
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
                df = pd.read_excel(uploaded_file)

            import_df_to_db(df, project_id=1)
            st.success("File uploaded and project data imported successfully!")
            st.rerun() # Rerun to reflect the changes from the database
        except Exception as e:
            st.error(f"Error processing file: {e}")

    # --- Load Sample Data ---
    if st.button("Load Sample Project Data"):
        import_df_to_db(get_sample_data(), project_id=1)
        st.success("Sample data loaded!")
        st.rerun()

    st.divider()

    # --- Data Editor and Calculation ---
    st.header("2. Task Planning")
    st.markdown("Edit tasks below. Press 'Calculate & Save' to update the project plan.")

    project_df = get_project_data_from_db(project_id=1)
    if project_df.empty:
        st.warning("No project data found. Load sample data or upload a file to begin.")
        return

    edited_df = st.data_editor(project_df, num_rows="dynamic", use_container_width=True)

    if st.button("Calculate & Save Project Plan", type="primary"):
        if edited_df is not None:
            save_project_data_to_db(edited_df, project_id=1)
            cpm_df = calculate_cpm(edited_df.copy())

            st.header("3. Results")
            st.subheader("Critical Path Analysis")
            st.dataframe(cpm_df)

            st.subheader("Gantt Chart")
            fig = create_gantt_chart(cpm_df, start_date)
            st.plotly_chart(fig, use_container_width=True)
            
            # --- ADDED THIS SECTION FOR THE NETWORK DIAGRAM ---
            st.subheader("CPM Network Diagram")
            network_fig = create_network_diagram(cpm_df)
            st.plotly_chart(network_fig, use_container_width=True)
