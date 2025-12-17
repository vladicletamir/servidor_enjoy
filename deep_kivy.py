from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from datetime import datetime
from pathlib import Path
import json
from concurrent.futures import ThreadPoolExecutor
import re
import requests 
import time
import os
from flask import Flask, request, jsonify
import sys

# ==========================================================
# CONDICIONAL PARA ENTORNO HEADLESS (RENDER)
# ==========================================================
# En Render, NO hay GUI disponible
GUI_AVAILABLE = False

# Módulos dummy para evitar errores
class DummyModule:
    def __init__(self, *args, **kwargs): pass
    def __getattr__(self, name): return lambda *args, **kwargs: self
    def Tk(self): return self
    def mainloop(self): pass
    def protocol(self, *args): pass
    def quit(self): pass
    def destroy(self): pass

class DummyStringVar:
    def __init__(self, *args, **kwargs): self.value = kwargs.get('value', '')
    def get(self): return self.value
    def set(self, val): self.value = val

class DummyMessagebox:
    def showerror(*args, **kwargs): 
        print("Mock: messagebox.showerror llamado (Ignorado en servidor)")

# Crear módulos dummy para evitar import errors
sys.modules['tkinter'] = DummyModule()
sys.modules['tkinter.ttk'] = DummyModule()
tk = DummyModule()
ttk = DummyModule()
messagebox = DummyMessagebox()
tk.StringVar = DummyStringVar

# ===============================
# CONFIGURACIÓN (Variables de Entorno)
# ===============================
# En Render, usa variables de entorno:
# ENJOY_USERNAME, ENJOY_PASSWORD, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

LOGIN_URL = "https://member.resamania.com/enjoy"
PLANNING_URL = "https://member.resamania.com/enjoy/planning"
STATE_FILE = Path("enjoy_state.json")

# --- CREDENCIALES desde variables de entorno ---
USERNAME =  "anaurma@hotmail.com"
PASSWORD = "Kerkrade1126"
TELEGRAM_BOT_TOKEN = "7576773682:AAE8_4OC9lLAFNlOWBbFmYGj5MFDfkQxAsU"
TELEGRAM_CHAT_ID = "1326867840"
# ----------------------------------------------

# Configuración de timeouts (ms)
TIMEOUT_CONFIG = {
    'navigation': 45000,  # Aumentado para Render
    'element': 15000,
    'short_wait': 3000,
    'long_wait': 8000
}

# Variables globales
ACTIVITY_NAME = ""
ACTIVITY_HOUR = ""
TARGET_DAY = ""
TARGET_MONTH = ""

# ===============================
# LISTAS DE ACTIVIDADES
# ===============================
HORAS_DISPONIBLES = []
for h in range(7, 21): 
    for m in [0, 15, 30, 45]:
        if h == 20 and m > 30: break 
        HORAS_DISPONIBLES.append(f"{h:02d}:{m:02d}")

ACTIVIDADES_DISPONIBLES = ["BODY PUMP", "ZUMBA", "PILATES", "GAP", "AQUAGYM", "BODY BALANCE", 
                          "CICLO INDOOR", "FUNCIONAL 360", "BODY BALANCE VIRTUAL", 
                          "CICLO INDOOR VIRTUAL", "BODY COMBAT", "BODY COMBAT VIRTUAL"]

MESES_DISPONIBLES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
]

# ===============================
# UTILIDADES
# ===============================
def log(msg):
    """Log con timestamp"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def send_telegram_message(text):
    """Envía un mensaje usando la API de Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log("❌ ERROR: TELEGRAM_BOT_TOKEN o CHAT_ID no configurados.")
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': text,
        'parse_mode': 'Markdown'
    }
    try:
        response = requests.post(url, data=payload, timeout=10)
        if response.status_code == 200:
            log("✅ Notificación de Telegram enviada.")
            return True
        else:
            log(f"❌ Error Telegram: {response.status_code}")
            return False
    except Exception as e:
        log(f"💥 Error conexión Telegram: {e}")
        return False

# ===============================
# GESTIÓN DE SESIÓN
# ===============================
class SessionManager:
    
    @staticmethod
    def is_logged_in(page):
        """Detecta si hay sesión activa"""
        try:
            indicators_of_success = [
                page.locator("text=Planificación"),
                page.locator("a:has-text('Cerrar sesión')"),
            ]
            is_success_indicated = any(ind.count() > 0 for ind in indicators_of_success) or "planning" in page.url.lower()
            is_on_login_page = "login" in page.url.lower()
            return is_success_indicated and not is_on_login_page
        except Exception:
            return False
    
    @staticmethod
    def restore_session(page):
        """Intenta restaurar sesión guardada"""
        if not STATE_FILE.exists():
            return False
        
        log("🔄 Restaurando sesión guardada...")
        try:
            page.goto(PLANNING_URL, wait_until="networkidle", timeout=TIMEOUT_CONFIG['navigation'])
            page.wait_for_timeout(TIMEOUT_CONFIG['long_wait'])
            
            if SessionManager.is_logged_in(page):
                log("✅ Sesión restaurada")
                return True
        except Exception as e:
            log(f"⚠️ Error restaurando sesión: {e}")
        
        return False
    
    @staticmethod
    def perform_login(page, context):
        """Realiza el login"""
        log("🚪 Iniciando login...")
        
        try:
            page.goto(LOGIN_URL, wait_until="networkidle", timeout=TIMEOUT_CONFIG['navigation'])
            
            if SessionManager.is_logged_in(page):
                log("✅ Ya estaba logueado")
                return True
            
            # Buscar botón de login
            selectors = [
                "button:has-text('Iniciar sesión')",
                "a:has-text('Iniciar sesión')",
                "button:has-text('Acceder')",
                "button:has-text('Entrar')",
                "[role='button']:has-text('sesión')"
            ]
            
            for selector in selectors:
                try:
                    if page.locator(selector).count() > 0:
                        page.click(selector)
                        log(f"✅ Click en: {selector}")
                        time.sleep(2)
                        break
                except:
                    continue
            
            # Email
            email_selectors = ["input[type='email']", "input[placeholder*='email']", "input[name='email']"]
            for selector in email_selectors:
                try:
                    page.fill(selector, USERNAME)
                    log("📧 Email introducido")
                    time.sleep(1)
                    break
                except:
                    continue
            
            # Botón continuar
            continue_selectors = ["button:has-text('Continuar')", "button:has-text('Siguiente')"]
            for selector in continue_selectors:
                try:
                    page.click(selector)
                    time.sleep(2)
                    break
                except:
                    continue
            
            # Contraseña
            pass_selectors = ["input[type='password']", "input[placeholder*='contraseña']"]
            for selector in pass_selectors:
                try:
                    page.fill(selector, PASSWORD)
                    log("🔑 Contraseña introducida")
                    time.sleep(1)
                    break
                except:
                    continue
            
            # Conectar
            connect_selectors = ["button:has-text('Conectarme')", "button:has-text('Entrar')", "button:has-text('Log in')"]
            for selector in connect_selectors:
                try:
                    page.click(selector)
                    break
                except:
                    continue
            
            # Esperar login
            time.sleep(5)
            
            if SessionManager.is_logged_in(page):
                context.storage_state(path=str(STATE_FILE))
                log("✅ Login exitoso")
                return True
            
            raise Exception("Login fallido - no se detectó sesión activa")
            
        except Exception as e:
            log(f"❌ Error en login: {e}")
            return False

# ===============================
# GESTIÓN DE FECHAS
# ===============================
class DateNavigator:
    @staticmethod
    def ensure_date_selected(page, target_day, target_month):
        """Garantiza que la fecha objetivo esté seleccionada"""
        log(f"🎯 Seleccionando fecha: {target_day} de {target_month}")
        
        # Primero intentar hacer clic en HOY para resetear
        try:
            hoy_selectors = ["button:has-text('HOY')", "button:has-text('Hoy')"]
            for selector in hoy_selectors:
                if page.locator(selector).count() > 0:
                    page.click(selector)
                    log("✅ Click en HOY")
                    time.sleep(3)
                    break
        except:
            pass
        
        # Si el día objetivo no es hoy, intentar seleccionarlo
        from datetime import datetime
        today = datetime.now().day
        today_str = str(today)
        
        if target_day != today_str:
            log(f"🔁 Buscamos día {target_day} (no es hoy)")
            
            # Intentar clic directo en el día
            try:
                day_elements = page.locator(f"text='{target_day}'").all()
                for element in day_elements:
                    if element.is_visible():
                        element.click()
                        log(f"✅ Click en día {target_day}")
                        time.sleep(3)
                        return True
            except Exception as e:
                log(f"⚠️ No se pudo hacer clic en día {target_day}: {e}")
        
        return True

# ===============================
# BÚSQUEDA DE ACTIVIDADES
# ===============================
class ActivityFinder:
    @staticmethod
    def find_activity_robust(page, activity_name, activity_hour):
        """Búsqueda robusta de actividad"""
        log(f"🔍 Buscando: '{activity_name}' a las '{activity_hour}'")
        
        # Obtener todo el texto de la página
        try:
            all_text = page.evaluate("() => document.body.textContent").upper()
        except:
            all_text = page.content().upper()
        
        # Verificar si la actividad y hora están en el texto
        if activity_name.upper() not in all_text:
            log(f"❌ '{activity_name}' no encontrado en la página")
            return -1
        
        # Buscar patrones de plazas
        import re
        
        # Dividir en líneas para análisis más preciso
        lines = all_text.split('\n')
        for line in lines:
            line_upper = line.upper().strip()
            
            # Filtrar líneas irrelevantes
            if len(line_upper) < 20:
                continue
            
            # Debe contener actividad Y hora
            contains_activity = activity_name.upper() in line_upper
            contains_hour = activity_hour in line_upper or activity_hour.replace(':', '.') in line_upper
            
            if contains_activity and contains_hour:
                log(f"✅ Línea encontrada: {line_upper[:80]}...")
                
                # Extraer plazas
                plazas = ActivityFinder._extract_spots_from_line(line_upper)
                if plazas >= 0:
                    return plazas
        
        return -1
    
    @staticmethod
    def _extract_spots_from_line(line):
        """Extrae plazas de una línea de texto"""
        import re
        
        # Buscar número antes de "PLAZA"
        match = re.search(r'(\d+)\s+PLAZAS?\s+VACANTES?', line)
        if match:
            return int(match.group(1))
        
        # Buscar cualquier número en la línea
        numbers = re.findall(r'\b(\d+)\b', line)
        if numbers:
            # Tomar el primer número (normalmente las plazas)
            return int(numbers[0])
        
        # Si dice "COMPLETO"
        if "COMPLETO" in line or "LLENO" in line:
            return 0
        
        return -1

# ===============================
# FUNCIÓN PRINCIPAL DEL BOT
# ===============================
def run_bot(activity_name, activity_hour, target_day, target_month, headless=True):
    """Ejecuta el bot y retorna número de plazas"""
    log(f"🚀 Iniciando bot para {activity_name} {activity_hour} ({target_day} {target_month})")
    
    with sync_playwright() as p:
        # Configuración para Render
        browser = p.chromium.launch(
            headless=headless,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--disable-features=IsolateOrigins,site-per-process"
            ]
        )
        
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        
        page = context.new_page()
        
        try:
            # 1. Login o restaurar sesión
            if SessionManager.restore_session(page):
                log("✅ Sesión restaurada")
            else:
                if not SessionManager.perform_login(page, context):
                    log("❌ Login fallido")
                    return {"status": "error", "message": "Login fallido"}
            
            # 2. Ir a planning
            page.goto(PLANNING_URL, wait_until="networkidle", timeout=TIMEOUT_CONFIG['navigation'])
            time.sleep(3)
            
            # 3. Seleccionar fecha
            DateNavigator.ensure_date_selected(page, target_day, target_month)
            time.sleep(3)
            
            # 4. Buscar actividad
            plazas = ActivityFinder.find_activity_robust(page, activity_name, activity_hour)
            
            if plazas > 0:
                log(f"🎉 ¡ÉXITO! {plazas} plazas disponibles")
                return {"status": "success", "plazas": plazas, "message": f"{plazas} plazas disponibles"}
            elif plazas == 0:
                log("⚠️ Actividad COMPLETA (0 plazas)")
                return {"status": "complete", "plazas": 0, "message": "Actividad completa"}
            elif plazas == -2:
                log("✅ Ya estás inscrito")
                return {"status": "inscrito", "message": "Ya estás inscrito"}
            else:
                log("❌ Actividad no encontrada")
                return {"status": "not_found", "message": "Actividad no encontrada"}
                
        except Exception as e:
            log(f"💥 Error crítico: {e}")
            return {"status": "error", "message": str(e)}
        
        finally:
            browser.close()
            log("👋 Bot finalizado")

# ===============================
# API FLASK PARA RENDER
# ===============================
app = Flask(__name__)
executor = ThreadPoolExecutor(max_workers=2)

@app.route('/')
def index():
    return jsonify({
        "status": "online",
        "service": "Enjoy Bot API",
        "version": "1.0",
        "endpoints": {
            "/buscar": "GET - Busca plazas disponibles",
            "/monitor": "POST - Inicia monitorización",
            "/health": "GET - Estado del servicio"
        },
        "usage": "GET /buscar?actividad=ZUMBA&hora=20:00&dia=17&mes=diciembre"
    })

@app.route('/buscar', methods=['GET'])
def buscar():
    """Endpoint principal para buscar plazas"""
    try:
        # Obtener parámetros
        actividad = request.args.get('actividad', '').upper()
        hora = request.args.get('hora', '')
        dia = request.args.get('dia', '')
        mes = request.args.get('mes', '').lower()
        
        # Validar parámetros
        if not all([actividad, hora, dia, mes]):
            return jsonify({
                "status": "error",
                "message": "Faltan parámetros. Usa: actividad, hora, dia, mes"
            }), 400
        
        if mes not in MESES_DISPONIBLES:
            return jsonify({
                "status": "error", 
                "message": f"Mes inválido. Debe ser uno de: {', '.join(MESES_DISPONIBLES)}"
            }), 400
        
        # Validar hora (formato HH:MM)
        import re
        if not re.match(r'^\d{2}:\d{2}$', hora):
            return jsonify({
                "status": "error",
                "message": "Formato de hora inválido. Usa HH:MM (ej: 20:00)"
            }), 400
        
        log(f"📥 Petición recibida: {actividad} {hora} {dia}/{mes}")
        
        # Ejecutar búsqueda
        result = run_bot(
            activity_name=actividad,
            activity_hour=hora,
            target_day=dia,
            target_month=mes,
            headless=True
        )
        
        # Enviar notificación Telegram si hay plazas
        if result.get("status") == "success":
            telegram_msg = f"✅ *PLAZAS DISPONIBLES!*\n\n" \
                          f"Clase: *{actividad}*\n" \
                          f"Hora: {hora}\n" \
                          f"Día: {dia} de {mes}\n" \
                          f"Plazas: **{result['plazas']}**"
            executor.submit(send_telegram_message, telegram_msg)
        
        return jsonify(result)
        
    except Exception as e:
        log(f"💥 Error en endpoint /buscar: {e}")
        return jsonify({
            "status": "error",
            "message": f"Error interno: {str(e)}"
        }), 500

@app.route('/monitor', methods=['POST'])
def monitor():
    """Inicia monitorización continua"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "No JSON data"}), 400
        
        actividad = data.get('actividad', '').upper()
        hora = data.get('hora', '')
        dia = data.get('dia', '')
        mes = data.get('mes', '').lower()
        
        if not all([actividad, hora, dia, mes]):
            return jsonify({"status": "error", "message": "Faltan parámetros"}), 400
        
        # Función de monitorización (simplificada para Render)
        def monitor_task():
            SLEEP_SECONDS = 300  # 5 minutos
            
            while True:
                log(f"🔄 Monitorización: {actividad} {hora}")
                result = run_bot(actividad, hora, dia, mes, headless=True)
                
                if result.get("status") == "success":
                    telegram_msg = f"🚨 *MONITOR: PLAZAS ENCONTRADAS!*\n\n" \
                                  f"Clase: *{actividad}*\n" \
                                  f"Hora: {hora}\n" \
                                  f"Día: {dia} de {mes}\n" \
                                  f"Plazas: **{result['plazas']}**"
                    send_telegram_message(telegram_msg)
                    break
                
                elif result.get("status") == "complete":
                    log(f"😴 Actividad completa. Esperando {SLEEP_SECONDS//60} min...")
                    time.sleep(SLEEP_SECONDS)
                
                else:
                    log("❌ Error en monitorización. Reintentando...")
                    time.sleep(SLEEP_SECONDS)
        
        # Iniciar monitorización en segundo plano
        executor.submit(monitor_task)
        
        return jsonify({
            "status": "monitoring",
            "message": f"Monitorización iniciada para {actividad} {hora}"
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Endpoint de salud"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "service": "Enjoy Bot API"
    })

@app.route('/debug', methods=['GET'])
def debug():
    """Endpoint de debug"""
    return jsonify({
        "credentials_configured": bool(USERNAME and PASSWORD),
        "telegram_configured": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
        "gui_available": GUI_AVAILABLE,
        "state_file_exists": STATE_FILE.exists(),
        "python_version": sys.version
    })

# ===============================
# EJECUCIÓN PRINCIPAL PARA RENDER
# ===============================
if __name__ == "__main__":
    # En Render, ejecutamos Flask
    port = int(os.environ.get("PORT", 5000))
    
    print("=" * 50)
    print("🚀 Enjoy Bot API - Iniciando en modo servidor")
    print(f"🌐 Puerto: {port}")
    print(f"🔧 GUI disponible: {GUI_AVAILABLE}")
    print(f"📱 Endpoints:")
    print(f"   • http://localhost:{port}/buscar?actividad=ZUMBA&hora=20:00&dia=17&mes=diciembre")
    print(f"   • http://localhost:{port}/health")
    print(f"   • http://localhost:{port}/debug")
    print("=" * 50)
    
    # Verificar credenciales
    if not USERNAME or USERNAME == "anaurma@hotmail.com":
        print("⚠️ ADVERTENCIA: Usa variables de entorno para credenciales:")
        print("   ENJOY_USERNAME, ENJOY_PASSWORD, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID")
    
    app.run(host="0.0.0.0", port=port, debug=False)
