# views/project_view.py
import streamlit as st
import pandas as pd
from datetime import date, timedelta

# Import functions from other project files
from database import get_project_data_from_db, save_project_data_to_db, import_df_to_db
from cpm_logic import calculate_cpm
from utils import get_sample_data
import plotly.express as px

# --- Gantt Chart Logic (Moved here for simplicity) ---
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
