from flask import Flask, request, jsonify
import threading

# Importamos SOLO lo que ya existe
from deep_kivy import run_bot

# Variables globales que tu bot YA usa
from deep_kivy import (
    ACTIVITY_NAME,
    ACTIVITY_HOUR,
    TARGET_DAY,
    TARGET_MONTH
)

app = Flask(__name__)

@app.route("/check", methods=["GET"])
def check_activity():
    """
    URL ejemplo:
    /check?activity=BODY PUMP&hour=18:00&day=15&month=octubre
    """

    try:
        # Leer parámetros
        activity = request.args.get("activity")
        hour = request.args.get("hour")
        day = request.args.get("day")
        month = request.args.get("month")

        if not all([activity, hour, day, month]):
            return jsonify({
                "ok": False,
                "error": "Faltan parámetros"
            }), 400

        # Asignar a las variables globales EXISTENTES
        import deep_kivy
        deep_kivy.ACTIVITY_NAME = activity
        deep_kivy.ACTIVITY_HOUR = hour
        deep_kivy.TARGET_DAY = day
        deep_kivy.TARGET_MONTH = month

        # Ejecutar bot (headless SIEMPRE)
        plazas = run_bot(headless=True)

        return jsonify({
            "ok": True,
            "activity": activity,
            "hour": hour,
            "day": day,
            "month": month,
            "plazas": plazas
        })

    except Exception as e:
        return jsonify({
            "ok": False,
            "error": str(e)
        }), 500


@app.route("/")
def health():
    return "Enjoy bot activo 🏋️‍♀️"


if __name__ == "__main__":
    # Render usa el puerto de la variable PORT
    import os
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
