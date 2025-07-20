# app.py
import os
os.environ["ST_DISABLE_WATCHDOG"] = "true"   # avoid inotify limit in containers

import streamlit as st

from database import initialize_database
from views.project_view import show_project_view
from views.checklist_view import show_checklist_view   # ← NEW

# ── 1. Page configuration (must be first Streamlit call) ─────────────
st.set_page_config(
    page_title="Collaborative CPM Tool",
    page_icon="🏗️",
    layout="wide",
)

# ── 2. Initialise the database ───────────────────────────────────────
initialize_database()

# ── 3. Sidebar navigation ────────────────────────────────────────────
PAGES = {
    "Planner Dashboard": show_project_view,
    "Daily Checklist":   show_checklist_view,   # ← NEW entry
}

selection = st.sidebar.radio("Go to page:", list(PAGES))
st.sidebar.divider()

# ── 4. Header shown on every page ────────────────────────────────────
st.title("🏗️ Collaborative Renovation Project Hub")
st.markdown(
    "Welcome! All data is **saved to the persistent database** when you press "
    "the *Calculate & Save* button (or tick items in the daily checklist)."
)
st.divider()

# ── 5. Render the selected view ──────────────────────────────────────
PAGES[selection]()
