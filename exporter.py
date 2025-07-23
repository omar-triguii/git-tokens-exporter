import os
import requests
from datetime import datetime
from flask import Flask, Response
from prometheus_client import Gauge, generate_latest
import threading
import time

# ─── Configuration ───
GITLAB_URL = "https://gitlab.com" ## change it if needed github, bitbucket, ..
GITLAB_API_TOKEN = os.getenv("GITLAB_API_TOKEN")

HEADERS = {
    "PRIVATE-TOKEN": GITLAB_API_TOKEN
}

# ─── Prometheus Metric ───
TOKEN_EXPIRY_GAUGE = Gauge(
    "gitlab_token_days_left",
    "Days left before GitLab token expires",
    ["token_name", "owner", "scope", "alert_level"]
)

# ─── GitLab API Calls ───
def calculate_days_left(expiry_date):
    try:
        expiry_date = expiry_date.strip()
        exp = datetime.strptime(expiry_date, "%Y-%m-%d")
        return (exp - datetime.utcnow()).days
    except Exception as e:
        print(f"⚠️ Date parsing failed: {expiry_date} → {e}")
        return None

def get_groups():
    url = f"{GITLAB_URL}/api/v4/groups?per_page=100"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        return res.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching groups: {e}")
        return []

def get_projects_for_group(group_id):
    url = f"{GITLAB_URL}/api/v4/groups/{group_id}/projects?per_page=100"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.raise_for_status()
        return res.json()
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching projects for group {group_id}: {e}")
        return []

def get_project_tokens(project_id):
    url = f"{GITLAB_URL}/api/v4/projects/{project_id}/access_tokens"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            return res.json()
        return []
    except requests.exceptions.RequestException:
        return []
def get_alert_level(days_left):
    if days_left is None:
        return "UNKNOWN"
    if days_left <= 5:
        return "CRITICAL"
    elif days_left <= 30:
        return "WARNING"
    elif days_left <= 60:
        return "ALERT"
    else:
        return "INFO"

# ✅ CHANGE START: New function to fetch group access tokens
def get_group_tokens(group_id):
    url = f"{GITLAB_URL}/api/v4/groups/{group_id}/access_tokens"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            return res.json()
        return []
    except requests.exceptions.RequestException as e:
        print(f"❌ Error fetching group tokens for group {group_id}: {e}")
        return []
# ✅ CHANGE END
# ─── Background Data Fetcher ───
metrics_ready = False
lock = threading.Lock()

def fetch_gitlab_metrics():
    global metrics_ready
    while True:
        with lock:
            print("🔄 Fetching GitLab token metrics...")
            TOKEN_EXPIRY_GAUGE.clear()
            groups = get_groups()
            if not groups:
                print("⚠️ No groups found.")
            else:
                for group in groups:
                    group_id = group["id"]
                    group_name = group["full_path"]
                    # ✅ CHANGE START: Fetch group access tokens
                    group_tokens = get_group_tokens(group_id)
                    for token in group_tokens:
                        days_left = calculate_days_left(token["expires_at"])
                        if days_left is not None:
                            TOKEN_EXPIRY_GAUGE.labels(
                                token_name=token["name"],
                                owner=group_name,
                                scope="group",
                                alert_level=get_alert_level(days_left)
                            ).set(days_left)
                    # ✅ CHANGE END
                    projects = get_projects_for_group(group_id)
                    for proj in projects:
                        project_id = proj["id"]
                        project_name = proj["name_with_namespace"]
                        tokens = get_project_tokens(project_id)
                        for token in tokens:
                            days_left = calculate_days_left(token["expires_at"])
                            if days_left is not None:
                                TOKEN_EXPIRY_GAUGE.labels(
                                    token_name=token["name"],
                                    owner=project_name,
                                    scope="project",
                                    alert_level=get_alert_level(days_left)
                                ).set(days_left)
            metrics_ready = True
            print("✅ Metrics updated successfully.")
        time.sleep(300)  # Wait 5 minutes before next fetch

# ─── Flask App for Exporter ───
app = Flask(__name__)

@app.route("/metrics")
def metrics():
    with lock:
        if not metrics_ready:
            return "Metrics not ready yet", 503
        return Response(generate_latest(), mimetype="text/plain")
def start_background_worker():
    threading.Thread(target=fetch_gitlab_metrics, daemon=True).start()

start_background_worker()  # ✅ Runs background worker in both dev & prod
if __name__ == "__main__":
    threading.Thread(target=fetch_gitlab_metrics, daemon=True).start()
    app.run(host="0.0.0.0", port=8000)
