from flask import Flask, jsonify
import os
from servidor_enjoy import run_monitor

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({"status": "ok", "message": "Enjoy bot Flask server running"})

@app.route("/monitor")
def monitor():
    activity = os.getenv("ENJOY_ACTIVITY", "AQUAGYM")
    hour = os.getenv("ENJOY_HOUR", "09:30")
    day = os.getenv("ENJOY_DAY", "22")
    month = os.getenv("ENJOY_MONTH", "DICIEMBRE")

    run_monitor(activity, hour, day, month)
    return jsonify({"status": "monitor started"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)

@app.route("/check") 
def check():
    print("📡 Endpoint /check recibido", flush=True) 
    try: 
        from servidor_enjoy import run_bot 
        plazas = run_bot(headless=True) 
        return jsonify({"plazas": plazas}) except 
    Exception as e: 
        print(f"❌ Error en /check: {e}", flush=True) 
        return jsonify({"error": str(e), "plazas": None})
