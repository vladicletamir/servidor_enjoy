from flask import Flask, jsonify
import os
from servidor_enjoy import run_monitor, run_bot
from servidor_enjoy import (
    MONITOR_ACTIVO,
    ULTIMA_VERIFICACION,
    PROXIMA_VERIFICACION,
    ACTIVITY_NAME,
    ACTIVITY_HOUR,
    TARGET_DAY,
    TARGET_MONTH
)

app = Flask(__name__)

@app.route("/")
def home():
    return jsonify({"status": "ok", "message": "Enjoy bot Flask server running"})

@app.route("/monitor")
def monitor():
    print("📡 Endpoint /monitor recibido", flush=True)

    activity = os.getenv("ENJOY_ACTIVITY", "BODY PUMP")
    hour = os.getenv("ENJOY_HOUR", "18:00")
    day = os.getenv("ENJOY_DAY", "21")
    month = os.getenv("ENJOY_MONTH", "DICIEMBRE")

    # Lanzamos monitor en hilo separado para no bloquear Flask
    import threading
    threading.Thread(target=run_monitor, args=(activity, hour, day, month), daemon=True).start()

    return jsonify({"status": "monitor started"})


@app.route("/check") 
def check(): 
    print("📡 Endpoint /check recibido", flush=True) 
    from servidor_enjoy import run_bot 
    plazas = run_bot(headless=True) 
    return jsonify({"plazas": plazas})

@app.route("/status") 
def status(): 
    return jsonify({"status": "ok"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(f"🚀 Flask arrancando en puerto {port}", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
