import os
import sys
import json
from datetime import datetime, timedelta

TRIAL_DAYS = 14

def check_trial():

    # get app name (works for exe also)
    app_name = os.path.basename(sys.argv[0])

    folder = os.path.join(os.getenv("APPDATA"), "SystemCache")
    os.makedirs(folder, exist_ok=True)

    file_name = f".{app_name}_timer.dat"
    path = os.path.join(folder, file_name)

    if not os.path.exists(path):
        start_time = datetime.now()

        with open(path, "w") as f:
            json.dump({"start": start_time.strftime("%Y-%m-%d %H:%M:%S")}, f)

        print("Trial started")
        return

    with open(path, "r") as f:
        data = json.load(f)

    start_time = datetime.strptime(data["start"], "%Y-%m-%d %H:%M:%S")
    expiry = start_time + timedelta(days=TRIAL_DAYS)

    if datetime.now() > expiry:
        print("❌ Trial expired")
        sys.exit()

    remaining = (expiry - datetime.now()).days
    print(f"Trial valid: {remaining} days remaining")