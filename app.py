import streamlit as st
from database import initialize_database
from views.project_view import show_project_view

# --- 1. Set Page Configuration ---
# This should be the first Streamlit command in your app.
st.set_page_config(
    page_title="Collaborative CPM Tool",
    page_icon="🏗️",
    layout="wide"
)

# --- 2. Initialize the Database ---
# This function from database.py will run when the app starts.
# It will create the 'projects.db' file and the necessary tables if they don't exist.
initialize_database()

# --- 3. Display App Title and Welcome Message ---
st.title("🏗️ Collaborative Renovation Project Hub I")
st.markdown("""
Welcome! This is your central hub for managing the renovation project.
All data is **saved to a persistent database** when you press the calculate button.
""")

# --- 4. Show the Main Project Interface ---
# We call the function from our new view file to render the page content.
# This keeps our main app file clean and organized.
show_project_view()
