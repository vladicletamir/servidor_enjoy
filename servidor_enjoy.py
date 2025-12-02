from flask import Flask, request, jsonify, render_template_string
import threading
import sys
import os
import uuid
import time
import logging

# Configurar logging para filtrar mensajes no deseados
logging.getLogger('werkzeug').setLevel(logging.WARNING)

# Añade la ruta de tu script original
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from deep_kivy import run_bot, run_monitor, send_telegram_message
    IMPORT_SUCCESS = True
except ImportError as e:
    print(f"⚠️ Error importando deep_kivy: {e}")
    IMPORT_SUCCESS = False

app = Flask(__name__)

# Diccionario para rastrear monitorizaciones activas
monitor_active = {}

# Ruta de prueba básica
@app.route('/')
def home():
    return jsonify({
        'mensaje': '🎯 Servidor Enjoy activo', 
        'estado': 'funcionando',
        'rutas': ['/estado', '/buscar', '/monitor_activas', '/test_telegram']
    })

@app.route('/estado')
def estado_servidor():
    print("✅ Ruta /estado fue accedida")
    return jsonify({
        'estado': 'activo', 
        'mensaje': 'Servidor funcionando correctamente',
        'import': 'success' if IMPORT_SUCCESS else 'failed'
    })

@app.route('/buscar', methods=['POST'])
def buscar_actividad():
    try:
        data = request.json
        
        # PASO DE DEPURACIÓN CRÍTICO: Imprimir los datos recibidos en los logs de Docker
        print(f"Datos recibidos para la búsqueda: {data}", flush=True) 

        # Devuelve el JSON recibido para confirmarlo en tu móvil
        return jsonify({
            "estado": "error",
            "mensaje": f"DEBUG: Recibido. Actividad: {data.get('actividad')}, Dia: {data.get('dia')}, Mes: {data.get('mes')}, Hora: {data.get('hora')}"
        })
        
        # ... El resto de tu lógica de Playwright debe ir aquí después de la depuración ...

    except Exception as e:
        return jsonify({"estado": "error", "mensaje": f"Error al procesar la solicitud: {str(e)}"})
@app.route('/test')
def test_page():
    """Página HTML simple para probar desde el móvil"""
    html = """
    <!DOCTYPE html>
    <html>
    <head><title>Enjoy Test</title></head>
    <body>
        <h1>🎯 Servidor Enjoy ACTIVO</h1>
        <p>Si ves esta página, el servidor funciona.</p>
        <p><a href="/estado">Ver estado JSON</a></p>
    </body>
    </html>
    """
    return render_template_string(html)

@app.route('/debug')
def debug_routes():
    """Muestra todas las rutas disponibles"""
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': list(rule.methods),
            'path': str(rule)
        })
    return jsonify({'rutas_registradas': routes})

@app.route('/test_telegram', methods=['POST'])
def test_telegram():
    """Endpoint para probar Telegram directamente"""
    try:
        send_telegram_message("🔔 PRUEBA: Servidor funcionando correctamente!")
        
        return jsonify({
            'estado': 'éxito', 
            'mensaje': 'Mensaje de prueba enviado a Telegram'
        })
    except Exception as e:
        print(f"💥 Error en test_telegram: {e}")
        return jsonify({'estado': 'error', 'mensaje': str(e)})

@app.route('/debug_telegram', methods=['GET'])
def debug_telegram():
    """Verificar configuración de Telegram"""
    try:
        import deep_kivy
        config = {
            'TELEGRAM_BOT_TOKEN': getattr(deep_kivy, 'TELEGRAM_BOT_TOKEN', 'No definido'),
            'TELEGRAM_CHAT_ID': getattr(deep_kivy, 'TELEGRAM_CHAT_ID', 'No definido'),
            'Tiene send_telegram_message': hasattr(deep_kivy, 'send_telegram_message')
        }
        return jsonify(config)
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/monitor_activas', methods=['GET'])
def listar_monitor_activas():
    """Ver monitorizaciones activas"""
    return jsonify({
        'monitorizaciones_activas': monitor_active,
        'total': len(monitor_active)
    })

@app.route('/verificar_campos', methods=['POST'])
def verificar_campos():
    """Verificar exactamente qué campos llegan desde App Inventor"""
    data = request.get_json()
    print("🔍 CAMPOS RECIBIDOS EXACTAMENTE:")
    for key, value in data.items():
        print(f"  '{key}': '{value}'")
    
    return jsonify({
        'campos_recibidos': list(data.keys()),
        'valores': data
    })

@app.route('/debug_appinventor', methods=['POST'])
def debug_appinventor():
    """Endpoint especial para debuggear App Inventor"""
    print("🔍 DEBUG App Inventor:")
    print("Headers:", dict(request.headers))
    print("Content-Type:", request.content_type)
    print("Data raw:", request.data)
    
    # Intentar procesar como JSON
    try:
        data = request.get_json()
        print("JSON data:", data)
        return jsonify({
            'estado': 'debug',
            'recibido': data,
            'mensaje': '✅ Datos recibidos correctamente como JSON'
        })
    except Exception as e:
        print("Error JSON:", e)
        return jsonify({
            'estado': 'error',
            'mensaje': f'No se pudo leer JSON: {str(e)}',
            'data_raw': request.data.decode('utf-8') if request.data else None
        }), 400

@app.route('/debug_deep_kivy', methods=['POST'])
def debug_deep_kivy():
    """Para diagnosticar cómo llamar correctamente a run_bot"""
    try:
        from deep_kivy import run_bot
        import inspect
        
        # Obtener información sobre la función run_bot
        signature = inspect.signature(run_bot)
        print(f"🔍 run_bot signature: {signature}")
        
        return jsonify({
            'estado': 'debug',
            'run_bot_parameters': str(signature),
            'mensaje': 'Revisa los logs del servidor para ver los parámetros'
        })
    except Exception as e:
        return jsonify({'estado': 'error', 'mensaje': str(e)})

@app.route('/test_monitor', methods=['POST'])
def test_monitor():
    """Endpoint de prueba con intervalo más corto"""
    try:
        import deep_kivy
        
        # Configurar para prueba rápida (30 segundos)
        deep_kivy.MONITOR_INTERVAL = 30  # 30 segundos para prueba
        deep_kivy.MAX_MONITOR_CYCLES = 3  # Solo 3 ciclos para prueba
        
        deep_kivy.ACTIVITY_NAME = "TEST"
        deep_kivy.ACTIVITY_HOUR = "12:00"
        deep_kivy.TARGET_DAY = "28"
        deep_kivy.TARGET_MONTH = "noviembre"
        
        # Iniciar monitorización en hilo
        threading.Thread(target=deep_kivy.run_monitor, daemon=True).start()
        
        return jsonify({
            'estado': 'test_monitor',
            'mensaje': 'Monitorización de prueba iniciada (30 segundos entre chequeos)'
        })
    except Exception as e:
        return jsonify({'estado': 'error', 'mensaje': str(e)})

@app.route('/config_deep_kivy', methods=['GET'])
def config_deep_kivy():
    """Verificar la configuración actual de deep_kivy"""
    try:
        import deep_kivy
        return jsonify({
            'ACTIVITY_NAME': getattr(deep_kivy, 'ACTIVITY_NAME', 'No definido'),
            'ACTIVITY_HOUR': getattr(deep_kivy, 'ACTIVITY_HOUR', 'No definido'),
            'TARGET_DAY': getattr(deep_kivy, 'TARGET_DAY', 'No definido'),
            'TARGET_MONTH': getattr(deep_kivy, 'TARGET_MONTH', 'No definido')
        })
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/buscar_simple', methods=['GET'])
def buscar_simple():
    """Versión simple que acepta GET"""
    try:
        actividad = request.args.get('actividad', 'BODY PUMP')
        dia = request.args.get('dia', '15')
        mes = request.args.get('mes', 'enero')
        hora = request.args.get('hora', '08:00')
        
        return jsonify({
            'estado': 'éxito',
            'mensaje': f'Recibido: {actividad} {dia}/{mes} a las {hora}',
            'nota': 'Método GET funcionando'
        })
    except Exception as e:
        return jsonify({'estado': 'error', 'mensaje': str(e)})


if __name__ == '__main__':
    # Obtener puerto de variable de entorno (para producción)
    port = int(os.environ.get('PORT', 5001))
    
    print("=" * 50)
    print("🚀 INICIANDO SERVIDOR ENJOY...")
    print("📍 URL local: http://localhost:5001")
    print("📍 Modo: PRODUCCIÓN")
    print("=" * 50)
    
    # Verificar import
    if not IMPORT_SUCCESS:
        print("❌ ADVERTENCIA: deep_kivy no se pudo importar")
        print("   Usando modo de prueba...")
    else:
        print("✅ deep_kivy importado correctamente")
    
    app.run(host='0.0.0.0', port=port, debug=False)
