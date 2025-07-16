# gantt.py
import pandas as pd
import plotly.express as px


def create_gantt_chart(df: pd.DataFrame):
    """
    Return an interactive Plotly Gantt chart.

    The dataframe must already include CPM columns ES / EF and
    a 'Duration' column (days).
    """
    project_start = pd.to_datetime("2025-01-01")

    df_g = df.copy()
    df_g["Start"] = project_start + pd.to_timedelta(df_g["ES"] - 1, unit="D")
    # NEW: +Duration (not -1) ensures one‑day activities are visible
    df_g["Finish"] = df_g["Start"] + pd.to_timedelta(df_g["Duration"], unit="D")

    fig = px.timeline(
        df_g,
        x_start="Start",
        x_end="Finish",
        y="Task Description",
        color="On Critical Path?",
        hover_data=["Task ID", "Duration", "ES", "EF", "LS", "LF", "Float"],
        color_discrete_map={"Yes": "red", "No": "blue"},
        title="Project Timeline (Gantt Chart)",
    )
    fig.update_yaxes(autorange="reversed")
    fig.update_layout(xaxis_title="Timeline", yaxis_title="Tasks")
    return fig
