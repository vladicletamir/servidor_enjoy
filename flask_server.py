from flask import Flask, jsonify
import os
from servidor_enjoy import run_monitor

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({"status": "ok", "message": "Enjoy bot Flask server running"})

@app.route("/monitor")
def monitor():
    activity = os.getenv("ENJOY_ACTIVITY", "BODY PUMP")
    hour = os.getenv("ENJOY_HOUR", "19:00")
    day = os.getenv("ENJOY_DAY", "21")
    month = os.getenv("ENJOY_MONTH", "enero")

    run_monitor(activity, hour, day, month)
    return jsonify({"status": "monitor started"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
