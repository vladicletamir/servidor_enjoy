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
def buscar_plazas():
    try:
        data = request.get_json()
        print(f"📱 Petición recibida: {data}")
        
        if not IMPORT_SUCCESS:
            return jsonify({
                'estado': 'error', 
                'mensaje': 'Error: No se pudo importar deep_kivy'
            })
        
        # Extraer datos (manejar diferentes nombres)
        actividad = data.get('actividad', data.get('activity_name', 'BODY PUMP'))
        dia = data.get('dia', data.get('DIA', '15'))
        hora = data.get('hora', data.get('HORA', '08:00'))
        mes = data.get('mes', data.get('MES', 'enero'))
        
        print(f"🔍 Procesado - Actividad: {actividad}, Día: {dia}, Hora: {hora}, Mes: {mes}")
        
        # ✅ CONEXIÓN CON DEEP_KIVY
        try:
            import deep_kivy
            
            # CONFIGURAR VARIABLES GLOBALES (como espera deep_kivy)
            deep_kivy.ACTIVITY_NAME = actividad
            deep_kivy.ACTIVITY_HOUR = hora
            deep_kivy.TARGET_DAY = dia
            deep_kivy.TARGET_MONTH = mes
            
            print(f"🎯 Configuración deep_kivy - ACTIVITY_NAME: {deep_kivy.ACTIVITY_NAME}")
            print(f"🎯 Configuración deep_kivy - TARGET_DAY: {deep_kivy.TARGET_DAY}")
            print(f"🎯 Configuración deep_kivy - TARGET_MONTH: {deep_kivy.TARGET_MONTH}")
            print(f"🎯 Configuración deep_kivy - ACTIVITY_HOUR: {deep_kivy.ACTIVITY_HOUR}")
            
            # Ejecutar búsqueda
            plazas = run_bot(headless=True)
            
            print(f"🎯 Resultado de búsqueda: {plazas} plazas")
            
            if plazas > 0:
                mensaje = f'🎉 {plazas} PLAZAS DISPONIBLES!\n{actividad} - {hora}'
                
                # ✅ ENVIAR A TELEGRAM
                try:
                    telegram_msg = f"🚨 PLAZAS ENCONTRADAS!\n{actividad} - {hora}\nDía: {dia} {mes}\nPlazas: {plazas}"
                    send_telegram_message(telegram_msg)
                    print("✅ Mensaje de Telegram enviado")
                except Exception as e:
                    print(f"⚠️ Error enviando Telegram: {e}")
                
                return jsonify({
                    'estado': 'plazas', 
                    'mensaje': mensaje,
                    'plazas': plazas
                })
                
            elif plazas == 0:
                mensaje = '🔍 No hay plazas, monitorizando...'
                
                # Enviar notificación a Telegram
                try:
                    telegram_msg = f"🔍 Monitorizando: {actividad} - {hora} (Día {dia} {mes})"
                    send_telegram_message(telegram_msg)
                except Exception as e:
                    print(f"⚠️ Error enviando Telegram: {e}")
                
                # Generar ID único para esta monitorización
                monitor_id = str(uuid.uuid4())[:8]
                
                # Iniciar monitorización en hilo separado
                def monitorizar_con_variables(mon_id, act, hr, d, m):
                    try:
                        import deep_kivy as dk_monitor
                        dk_monitor.ACTIVITY_NAME = act
                        dk_monitor.ACTIVITY_HOUR = hr
                        dk_monitor.TARGET_DAY = d
                        dk_monitor.TARGET_MONTH = m
                        
                        # Marcar como activa
                        monitor_active[mon_id] = {
                            'actividad': act,
                            'hora': hr,
                            'dia': d,
                            'mes': m,
                            'inicio': time.time()
                        }
                        
                        # Ejecutar monitorización
                        dk_monitor.run_monitor()
                        
                    except Exception as e:
                        print(f"💥 Error en hilo de monitorización: {e}")
                    finally:
                        # Eliminar de activas cuando termine
                        if mon_id in monitor_active:
                            del monitor_active[mon_id]
                
                thread = threading.Thread(
                    target=monitorizar_con_variables,
                    args=(monitor_id, actividad, hora, dia, mes),
                    daemon=True
                )
                thread.start()
                
                return jsonify({
                    'estado': 'monitorizando', 
                    'mensaje': f'🔍 Monitorizando cada 5 minutos... (ID: {monitor_id})',
                    'monitor_id': monitor_id
                })
            else:
                return jsonify({
                    'estado': 'error', 
                    'mensaje': '❌ No se encontró la actividad'
                })
                
        except Exception as e:
            print(f"💥 Error en deep_kivy: {e}")
            import traceback
            traceback.print_exc()
            
            return jsonify({
                'estado': 'error', 
                'mensaje': f'Error en búsqueda: {str(e)}'
            })
            
    except Exception as e:
        print(f"💥 Error en /buscar: {e}")
        return jsonify({
            'estado': 'error', 
            'mensaje': f'Error del servidor: {str(e)}'
        })

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
