# 🏗️ Collaborative CPM & Gantt Tool

![Streamlit](https://img.shields.io/badge/Built%20with-Streamlit-ff4b4b?logo=streamlit\&logoColor=white)
![Postgres](https://img.shields.io/badge/Database-PostgreSQL-4169E1?logo=postgresql\&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

A lightweight, web‑based Critical Path Method (CPM) and Gantt‑chart planner for
construction (or any dependency‑heavy) projects.  Upload a CSV/Excel schedule,
get instant CPM analytics, an interactive Gantt, and a network diagram—then
edit tasks in‑browser and persist everything to PostgreSQL.

---

## ✨ Key features

| Feature                   | Details                                                                                                             |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| **Drag‑and‑drop import**  | Accepts `.csv` or `.xlsx` with Task ID / Description / Predecessors / Duration (+ optional Status).                 |
| **CPM engine**            | Early Start, Early Finish, Late Start, Late Finish, Float, and automatic critical‑path flagging.                    |
| **Interactive Gantt**     | Plotly timeline with colour‑coded criticality & status; filter by phase, date range, or task list.                  |
| **Network diagram**       | Activity‑on‑node diagram (NetworkX + Plotly) with missing‑ID guarding and clear red/blue colouring.                 |
| **Data persistence**      | All tasks & projects stored in a Postgres database (works locally or on Railway) so nothing is lost on app restart. |
| **Rich CSV export**       | One‑click download of the current project—including computed CPM columns—for offline analysis.                      |
| **Validation guardrails** | Detects duplicate IDs, empty IDs, and dangling predecessor references before saving.                                |

---

## 🖼️ Quick demo

![demo GIF](docs/demo.gif) <!-- optional → replace with screen‑capture -->

---

## 🏛️ Folder structure

```
basic_cpm_gantt/
│ app.py                 ← Streamlit entry‑point (sets the page config)
│ requirements.txt       ← Python deps (pin versions in prod!)
│
├─ views/
│   └─ project_view.py    ← Main Streamlit view (UI, validation, plots)
│
├─ cpm_logic.py          ← Forward/backward pass algorithm
├─ database.py           ← SQLAlchemy engine + create / save / load helpers
├─ utils.py              ← Sample‑data generator
└─ gantt.py              ← (Optional) stand‑alone Gantt‑chart helper
```

---

## 🚀 Local setup

```bash
# 1 Clone
$ git clone https://github.com/<your‑org>/basic_cpm_gantt.git
$ cd basic_cpm_gantt

# 2 Create venv & install deps
$ python -m venv .venv && source .venv/bin/activate
$ pip install -r requirements.txt

# 3 Provision Postgres (Docker example)
$ docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=pass postgres:15

# 4 Set secrets (creates .streamlit/secrets.toml)
$ cp .streamlit/secrets.example.toml .streamlit/secrets.toml
# edit the DB URL: postgresql+psycopg2://postgres:pass@localhost:5432/postgres

# 5 Run
$ streamlit run app.py
```

> **Note**: the first launch creates the `projects` and `tasks` tables
> automatically.

---

## ☁️ Deploy to Streamlit Cloud + Railway

1. **Fork** the repo → Deploy to Streamlit Cloud.
2. Create a **PostgreSQL plugin** in Railway.  Copy the public connection URL.
3. Add the following secret in the Cloud UI (`Settings → Secrets`).

```toml
[database]
url = "postgresql+psycopg2://<user>:<password>@<proxy>.railway.app:<port>/<db>?sslmode=require"
```

4. Restart the app—tables are created on first run; data persists across
   redeploys.

---

## 📄 CSV / Excel format

| Column               | Required | Example            | Notes                                         |
| -------------------- | -------- | ------------------ | --------------------------------------------- |
| **Task ID**          | ✔︎       | `SITE-100`         | Must be unique (case‑insensitive after trim). |
| **Task Description** | ✔︎       | `Site Survey`      | Free text.                                    |
| **Predecessors**     | ✔︎       | `SITE-100,EXC-200` | Comma, space, semicolon, or period separated. |
| **Duration**         | ✔︎       | `3`                | Integer days.                                 |
| **Status**           | –        | `In Progress`      | Defaults to `Not Started` if omitted.         |

See `sample_data.csv` for a template.

---

## 🧮 How CPM is calculated (high‑level)

1. **Forward pass** → compute Early Start (ES) & Early Finish (EF).
2. **Backward pass** → compute Late Finish (LF) & Late Start (LS).
3. **Float** = `LS – ES`; activities with Float 0 are on the **critical path**.

Implementation is in `cpm_logic.py`; unit tests suggested in `tests/` (todo).

---

## ⚙️ Configuration reference

| Secret / ENV             | Purpose                                                      |
| ------------------------ | ------------------------------------------------------------ |
| `database.url`           | Full SQLAlchemy URL. Supports `sqlite:///…` for quick demos. |
| `PORT` (Streamlit Cloud) | Usually set automatically; keep default.                     |

---

## 🤝 Contributing

Pull requests are welcome!  Please:

1. Run `black` and `ruff --fix .` before committing.
2. Add or update unit tests in `tests/`.
3. Describe the change in the PR template.

---

## 📜 License

This project is licensed under the MIT License—see `LICENSE` for details.
