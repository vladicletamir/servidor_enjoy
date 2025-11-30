import kivy
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.uix.scrollview import ScrollView
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import StringProperty
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import time
import re
import requests
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright, expect, TimeoutError as PlaywrightTimeoutError

# Opcional: Especificar la versión mínima de Kivy
kivy.require('1.9.0')

# ===============================
# CONFIGURACIÓN (Mantener)
# ===============================
LOGIN_URL = "https://member.resamania.com/enjoy"
PLANNING_URL = "https://member.resamania.com/enjoy/planning?autologintoken=4a6425141ee392a2b1a1"
STATE_FILE = Path("enjoy_state.json")

# --- CREDENCIALES ---
USERNAME = "anaurma@hotmail.com" 
PASSWORD = "Kerkrade1126" 
# --------------------

# Configuración de timeouts (ms)
TIMEOUT_CONFIG = {
    'navigation': 30000,
    'element': 10000,
    'short_wait': 2000,
    'long_wait': 5000
}

# --- CONFIGURACIÓN DE TELEGRAM ---
TELEGRAM_BOT_TOKEN = "7576773682:AAE8_4OC9lLAFNlOWBbFmYGj5MFDfkQxAsU"
TELEGRAM_CHAT_ID = "1326867840"
# ------------------------------------

# Variables globales para el bot (se configuran en la UI)
ACTIVITY_NAME = ""
ACTIVITY_HOUR = ""
TARGET_DAY = ""
TARGET_MONTH = ""

# ===============================
# CONFIGURACIÓN DE LISTAS (Mantener)
# ===============================
HORAS_DISPONIBLES = [f"{h:02d}:{m:02d}" for h in range(7, 23) for m in [0, 15, 30, 45] if not (h == 23 and m > 30)]
ACTIVIDADES_DISPONIBLES = ["BODY PUMP", "ZUMBA", "PILATES","GAP","AQUAGYM","BODY BALANCE", "CICLO INDOOR","FUNCIONAL 360","BODY BALANCE VIRTUAL", "CICLO INDOOR VIRTUAL","BODY COMBAT","BODY COMBAT VIRTUAL", "X-TRAINING"]
DIAS_DISPONIBLES = [str(i) for i in range(1, 32)]
MESES_DISPONIBLES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
]

# ===============================
# UTILIDADES (MODIFICADO: log ahora se conecta a Kivy)
# ===============================
def log(msg):
    """Log con timestamp, lo muestra en consola Y lo envía a la UI de Kivy si existe."""
    # 1. Log a consola
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")
    
    # 2. Log a Kivy UI
    try:
        app = App.get_running_app()
        # Verificar si la aplicación y el widget raíz están en ejecución
        if app and hasattr(app, 'root') and hasattr(app.root, 'append_log'):
            # Usar el método de la UI para añadir el mensaje
            app.root.append_log(msg)
    except Exception:
        # Falla si la app Kivy no se ha inicializado
        pass 

def screenshot(page, name):
    """Captura screenshot con timestamp"""
    Path("screenshots").mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = Path("screenshots") / f"{name}_{ts}.png"
    try:
        page.screenshot(path=str(path), timeout=5000)
        log(f"📸 Screenshot: {path}")
    except Exception as e:
        log(f"⚠️ Error capturando screenshot: {e}")

def send_telegram_message(text):
    """Envía un mensaje usando la API de Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        log("❌ ERROR: TELEGRAM_BOT_TOKEN o CHAT_ID no configurados correctamente.")
        return False
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': text,
        'parse_mode': 'Markdown' 
    }
    try:
        response = requests.post(url, data=payload, timeout=5)
        if response.status_code == 200:
            log("✅ Notificación de Telegram enviada con éxito.")
            return True
        else:
            log(f"❌ Error al enviar Telegram. Código: {response.status_code}")
            return False
    except Exception as e:
        log(f"💥 Error de conexión al enviar Telegram: {e}")
        return False

# ... (El resto de clases SessionManager, DateNavigator y ActivityFinder se mantienen iguales) ...
# Por brevedad en la respuesta, el código se omite aquí, pero se asume que está en el script completo.
# --------------------------------------------------------------------------------------------------

# ===============================
# GESTIÓN DE SESIÓN (SessionManager) - Mantenida
# ===============================
class SessionManager:
    @staticmethod
    def is_logged_in(page):
        try:
            indicators_of_success = [
                page.locator("text=Planificación"),
                page.locator("a:has-text('Cerrar sesión')"),
            ]
            is_success_indicated = any(ind.count() > 0 for ind in indicators_of_success) or "planning" in page.url.lower()
            is_on_login_page = "login" in page.url.lower()
            return is_success_indicated and not is_on_login_page
        except Exception: return False
    
    @staticmethod
    def restore_session(page):
        if not STATE_FILE.exists(): return False
        log("🔄 Restaurando sesión guardada...")
        try:
            page.goto(PLANNING_URL, wait_until="domcontentloaded", timeout=TIMEOUT_CONFIG['navigation'])
            page.wait_for_load_state("networkidle", timeout=TIMEOUT_CONFIG['long_wait'])
            if SessionManager.is_logged_in(page):
                log("✅ Sesión restaurada")
                return True
        except Exception as e: log(f"⚠️ Error restaurando sesión: {e}")
        return False
    
    @staticmethod
    def perform_login(page, context):
        log("🚪 Iniciando login...")
        try:
            page.goto(LOGIN_URL, wait_until="networkidle", timeout=TIMEOUT_CONFIG['navigation'])
            if SessionManager.is_logged_in(page):
                log("✅ Ya estaba logueado")
                return True
            screenshot(page, "antes_login")
            if not SessionManager._click_login_button(page): raise Exception("No se encontró botón de login")
            if not SessionManager._fill_email(page): raise Exception("No se pudo llenar el email")
            if not SessionManager._click_continue(page): raise Exception("No se encontró botón continuar")
            if not SessionManager._fill_password(page): raise Exception("No se pudo llenar la contraseña")
            if not SessionManager._click_connect(page): raise Exception("No se encontró botón conectar")
            page.wait_for_load_state("networkidle", timeout=TIMEOUT_CONFIG['navigation'])
            if SessionManager.is_logged_in(page):
                context.storage_state(path=str(STATE_FILE))
                log("✅ Login exitoso")
                return True
            raise Exception("Login fallido")
        except Exception as e:
            log(f"❌ Error en login: {e}")
            screenshot(page, "error_login")
            return False
    
    @staticmethod
    def _click_login_button(page):
        selectors = ["button:has-text('Iniciar sesión')", "a:has-text('Iniciar sesión')", "button:has-text('Acceder')", "button:has-text('Entrar')","[role='button']:has-text('sesión' i), [role='button']:has-text('Acceder' i)", "button[type='submit']", "a[href*='login']",]
        log("🖱️ Buscando botón de inicio de sesión...")
        for selector in selectors:
            try:
                elements = page.locator(selector).all()
                for elem in elements:
                    if elem.is_visible() and elem.is_enabled():
                        log(f"   ✅ Click en selector robusto: '{selector}'")
                        elem.click(timeout=TIMEOUT_CONFIG['element'])
                        page.wait_for_timeout(TIMEOUT_CONFIG['short_wait'])
                        return True
            except: continue
        log("   ❌ No se encontró un botón de inicio de sesión válido.")
        return False
    
    @staticmethod
    def _fill_email(page):
        selectors = ["input[placeholder*='email' i]", "input[type='email']", "input[name='email']"]
        for frame in [page] + page.frames:
            for selector in selectors:
                try:
                    if frame.locator(selector).count() > 0:
                        frame.fill(selector, USERNAME, timeout=TIMEOUT_CONFIG['element'])
                        log("📧 Email introducido")
                        page.wait_for_timeout(TIMEOUT_CONFIG['short_wait'])
                        return True
                except: continue
        return False
    
    @staticmethod
    def _click_continue(page):
        selectors = ["button:has-text('Introducir mi contraseña')", "button:has-text('Continuar')", "button:has-text('Siguiente')"]
        for frame in [page] + page.frames:
            for selector in selectors:
                try:
                    if frame.locator(selector).count() > 0:
                        frame.locator(selector).first.click(timeout=TIMEOUT_CONFIG['element'])
                        page.wait_for_timeout(TIMEOUT_CONFIG['short_wait'])
                        return True
                except: continue
        return False
    
    @staticmethod
    def _fill_password(page):
        selectors = ["input[placeholder*='contraseña' i]", "input[type='password']", "input[name='password']"]
        for frame in [page] + page.frames:
            for selector in selectors:
                try:
                    if frame.locator(selector).count() > 0:
                        frame.fill(selector, PASSWORD, timeout=TIMEOUT_CONFIG['element'])
                        log("🔑 Contraseña introducida")
                        page.wait_for_timeout(TIMEOUT_CONFIG['short_wait'])
                        return True
                except: continue
        return False
    
    @staticmethod
    def _click_connect(page):
        selectors = ["button:has-text('Conectarme a mi club')", "button:has-text('Conectarme')", "button:has-text('Entrar')"]
        for frame in [page] + page.frames:
            for selector in selectors:
                try:
                    if frame.locator(selector).count() > 0:
                        frame.locator(selector).first.click(timeout=TIMEOUT_CONFIG['element'])
                        return True
                except: continue
        return False

# ===============================
# GESTIÓN DE FECHAS (DateNavigator) - Mantenida
# ===============================
class DateNavigator:
    @staticmethod
    def ensure_date_selected(page, max_retries=3):
        log(f"🎯 Seleccionando fecha: {TARGET_DAY} de {TARGET_MONTH}")
        screenshot(page, "antes_seleccion_fecha")
        for attempt in range(max_retries):
            try:
                log(f"🔄 Intento {attempt + 1}/{max_retries}")
                if DateNavigator._is_date_selected(page):
                    log("✅ Fecha ya seleccionada")
                    return True
                if DateNavigator._click_day_directly(page):
                    log("✅ Click directo en día exitoso")
                    page.wait_for_timeout(TIMEOUT_CONFIG['long_wait'])
                    if DateNavigator._verify_activities_loaded(page):
                        log("🎉 Fecha seleccionada y actividades cargadas")
                        return True
                log("🔄 Intentando navegación por mes...")
                if DateNavigator._navigate_to_month(page):
                    if DateNavigator._select_day(page):
                        page.wait_for_timeout(TIMEOUT_CONFIG['long_wait'])
                        return True
            except Exception as e:
                log(f"💥 Error en intento {attempt + 1}: {e}")
                screenshot(page, f"error_fecha_intento_{attempt+1}")
                page.wait_for_timeout(TIMEOUT_CONFIG['short_wait'])
        log("⚠️ Continuando sin confirmar fecha (puede que ya esté seleccionada)")
        return True
    
    @staticmethod
    def _verify_activities_loaded(page):
        try:
            page.wait_for_function(
                """() => {
                    const html = document.body.innerHTML.toLowerCase();
                    return html.includes('actividad') || html.includes('plaza');
                }""",
                timeout=5000
            )
            return True
        except: return False

    @staticmethod
    def _is_date_selected(page):
        try:
            selectors = [
                f"[class*='selected']:has-text('{TARGET_DAY}')",
                f"[class*='active']:has-text('{TARGET_DAY}')",
                f"[aria-selected='true']:has-text('{TARGET_DAY}')"
            ]
            return any(page.locator(sel).count() > 0 for sel in selectors)
        except: return False

    @staticmethod
    def _click_day_directly(page):
        log(f"🖱️ Buscando día {TARGET_DAY} para click directo...")
        strategies = [
            (f"button:has-text('{TARGET_DAY}')", "botón"),
            (f"td:has-text('{TARGET_DAY}')", "celda tabla"),
            (f"div[role='button']:has-text('{TARGET_DAY}')", "div clickeable"),
            (f"[data-date*='-{TARGET_DAY.zfill(2)}']", "data-date"),
            (f"a:has-text('{TARGET_DAY}')", "link"),
        ]
        for selector, tipo in strategies:
            try:
                elements = page.locator(selector).all()
                for elem in elements:
                    try:
                        if elem.is_visible() and elem.is_enabled():
                            log(f"   📌 Elemento encontrado: '{elem.text_content().strip()}'")
                            try:
                                with page.expect_navigation(timeout=3000, wait_until="domcontentloaded"):
                                    elem.click()
                                log(f"   ✅ Click exitoso con navegación ({tipo})")
                            except:
                                elem.click()
                                log(f"   ✅ Click exitoso sin navegación ({tipo})")
                            page.wait_for_timeout(3000)
                            return True
                    except Exception: continue
            except Exception as e:
                log(f"   ⚠️ Error en estrategia '{tipo}': {e}")
                continue
        return False
    
    @staticmethod
    def _navigate_to_month(page):
        if DateNavigator._is_correct_month(page): return True
        log("➡️ Navegando al mes objetivo...")
        next_selectors = ["button:has-text('>')", "button:has-text('›')", "[aria-label*='next' i]", ".fc-next-button", "[class*='next']"]
        for i in range(12):  
            if DateNavigator._is_correct_month(page): return True
            clicked = False
            for selector in next_selectors:
                try:
                    if page.locator(selector).count() > 0:
                        btn = page.locator(selector).first
                        if btn.is_visible() and btn.is_enabled():
                            btn.click(timeout=TIMEOUT_CONFIG['element'])
                            page.wait_for_timeout(TIMEOUT_CONFIG['short_wait'])
                            clicked = True
                            break
                except Exception: continue
            if not clicked:
                log("❌ No se encontraron botones de navegación")
                return False
        return False
    
    @staticmethod
    def _is_correct_month(page):
        try:
            month_lower = TARGET_MONTH.lower()
            month_short = month_lower[:3]
            content = page.content().lower()
            if month_lower in content or month_short in content: return True
            selectors = [f"text=/{month_lower}/i", f"text=/{month_short}/i", f"h1:has-text('{TARGET_MONTH}')"]
            for sel in selectors:
                if page.locator(sel).count() > 0: return True
            return False
        except Exception: return False
    
    @staticmethod
    def _select_day(page):
        return DateNavigator._click_day_directly(page)

# ===============================
# BÚSQUEDA DE ACTIVIDADES (ActivityFinder) - Mantenida
# ===============================
class ActivityFinder:
    @staticmethod
    def get_planning_frame(page):
        log("🧩 Buscando frame de planificación...")
        for frame in page.frames:
            if "planning" in frame.url or "resamania" in frame.url:
                return frame
        return page
    
    @staticmethod
    def wait_for_activities(frame):
        log("⏳ Esperando actividades...")
        try:
            frame.wait_for_selector("div, article, li", state="attached", timeout=TIMEOUT_CONFIG['navigation'])
            frame.wait_for_timeout(2000)
            return True
        except PlaywrightTimeoutError:
            log("⚠️ Timeout esperando carga inicial")
            return False
    
    @staticmethod
    def scroll_page(page):
        try:
            for _ in range(3):
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(500)
            page.mouse.wheel(0, -3000)
            return True
        except: return False

    @staticmethod
    def find_activity(frame):
        global ACTIVITY_NAME, ACTIVITY_HOUR
        activity_regex = f"/{re.escape(ACTIVITY_NAME)}/i"
        log(f"🎯 Buscando tarjeta con: '{ACTIVITY_NAME}' (Regex: {activity_regex}) Y '{ACTIVITY_HOUR}'")
        try:
            candidates = frame.locator(f"text={activity_regex}")
            count = candidates.count()
            log(f"   🔎 Elementos con el nombre encontrados: {count}")
            if count == 0: return -1

            for i in range(count):
                element = candidates.nth(i)
                parent = element
                for level in range(7): 
                    try:
                        text = parent.text_content()
                        clean_text = " ".join(text.split()).upper()
                        hour_check = ACTIVITY_HOUR.replace(':00', '') 
                        
                        if ACTIVITY_HOUR in clean_text or hour_check in clean_text:
                            log(f"   ✅ ¡Coincidencia de HORA encontrada en contenedor (Nivel {level})!")
                            log(f"   📄 Texto contenedor analizado: {clean_text[:100]}...")
                            plazas = ActivityFinder._extract_spots(parent)
                            if plazas != -1: 
                                return plazas
                            else:
                                log("   ⚠️ Hora y Actividad coinciden, pero no se extrajeron plazas válidas.")
                        parent = parent.locator("..")
                    except Exception: break
        except Exception as e:
            log(f"⚠️ Error en búsqueda: {e}")
        log("❌ No se encontró la combinación Actividad + Hora + Plazas en un contenedor válido")
        return -1
    
    @staticmethod
    def _extract_spots(element):
        text = element.text_content()
        clean_text = " ".join(text.split()) 
        log(f"   🔢 Analizando plazas en: '{clean_text[:60]}...'")

        try:
            if element.locator("button:has-text('Anular')").count() > 0 or \
               element.locator("button:has-text('Cancelar')").count() > 0:
                log("   ✅ DETECTADO BOTÓN 'Anular/Cancelar'. Usuario INSCRITO.")
                return -2 
        except Exception: pass
        
        if "completo" in clean_text.lower() or "lista de espera" in clean_text.lower() or "no quedan plazas" in clean_text.lower():
            log("   🔴 DETECTADO TEXTO 'COMPLETO' o 'Lista de Espera'.")
            return 0

        if "inscrito" in clean_text.lower() or "reservado" in clean_text.lower():
            log("   ⚠️ DETECTADO TEXTO 'INSCRITO' (Sin botón Anular). Asumiendo INSCRITO.")
            return -2 

        match_exact = re.search(r'(\d+)\s*plazas?\s*vacantes?', clean_text, re.IGNORECASE)
        if match_exact:
            spots = int(match_exact.group(1))
            log(f"   🎉 ¡Plazas encontradas (Específica 'vacantes'): {spots}!")
            return spots
            
        match_quedan = re.search(r'(?:quedan|disponibles|libres):\s*(\d+)', clean_text, re.IGNORECASE)
        if match_quedan:
            spots = int(match_quedan.group(1))
            log(f"   🎉 ¡Plazas encontradas (Quedan/Disponibles): {spots}!")
            return spots

        match_fallback = re.search(r'(\d+)\s*plazas', clean_text, re.IGNORECASE)
        if match_fallback:
             spots = int(match_fallback.group(1))
             if spots < 100: 
                 log(f"   ⚠️ ¡Plazas encontradas (Fallback/Baja confianza): {spots}! (Límite: 100)")
                 return spots
             log("   ⚠️ Fallback ignorado (Número de plazas demasiado alto > 100).")

        log("   ⚠️ No se detectó un número de plazas válido en este contenedor.")
        return -1


# ===============================
# FUNCIÓN PRINCIPAL DEL BOT (Mantenida)
# ===============================
def run_bot(headless=False):
    """Ejecuta el bot y retorna número de plazas. Acepta headless para monitorización."""
    log("🚀 Iniciando bot...")
    log(f"🎯 Objetivo: {ACTIVITY_NAME} {ACTIVITY_HOUR} ({TARGET_DAY} {TARGET_MONTH})")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless) 
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        
        try:
            if SessionManager.restore_session(page):
                page.goto(PLANNING_URL, wait_until="networkidle", timeout=TIMEOUT_CONFIG['navigation'])
                page.wait_for_timeout(TIMEOUT_CONFIG['long_wait'])

                if not SessionManager.is_logged_in(page):
                    log("⚠️ Sesión restaurada inválida. Forzando login completo.")
                    if not SessionManager.perform_login(page, context):
                        log("❌ Fallo de autenticación tras restauración")
                        return -1
            
            else:
                if not SessionManager.perform_login(page, context):
                    log("❌ Fallo de autenticación")
                    return -1
            
            page.goto(PLANNING_URL, wait_until="networkidle", timeout=TIMEOUT_CONFIG['navigation'])
            page.wait_for_timeout(TIMEOUT_CONFIG['long_wait'])
            
            if not DateNavigator.ensure_date_selected(page):
                log("❌ No se pudo seleccionar la fecha")
                return -1
            
            frame = ActivityFinder.get_planning_frame(page)
            ActivityFinder.wait_for_activities(frame)
            ActivityFinder.scroll_page(page)
            
            plazas = ActivityFinder.find_activity(frame)
            log(f"🎯 Resultado final: {plazas} plazas")
            
            return plazas
            
        except Exception as e:
            log(f"💥 Error crítico: {e}")
            screenshot(page, "error_critico")
            return -1
        
        finally:
            browser.close()
            log("👋 Bot finalizado")

# ===============================
# FUNCIÓN DE MONITORIZACIÓN (MODIFICADO: Pasa callback de UI)
# ===============================
def run_monitor(activity, hour, day, month):
    """
    Ejecuta el bot en un bucle hasta encontrar plazas.
    """
    global ACTIVITY_NAME, ACTIVITY_HOUR, TARGET_DAY, TARGET_MONTH
    
    ACTIVITY_NAME = activity
    ACTIVITY_HOUR = hour
    TARGET_DAY = day
    TARGET_MONTH = month
    
    log(f"🕵️‍♂️ INICIANDO MONITORIZACIÓN: {activity} a las {hour} - DÍA {day}/{month}")
    
    SLEEP_SECONDS = 600 # 10 minutos
    
    while True:
        log("🔄 Ejecutando verificación en modo monitor...")
        
        # Le enviamos un mensaje a la UI para que sepa que el monitor está vivo
        Clock.schedule_once(lambda dt: App.get_running_app().root.update_result_text(f"🔴 Monitor ACTIVO...\nPróximo chequeo en 10 min."), 0)
        
        plazas = run_bot(headless=True) 
        
        if plazas > 0:
            msg_telegram = f"🚨 *¡PLAZA LIBRE ENCONTRADA!* 🚨\n\n" \
                           f"Clase: *{ACTIVITY_NAME}*\n" \
                           f"Hora: {ACTIVITY_HOUR}\n" \
                           f"Día: {TARGET_DAY} de {TARGET_MONTH}\n" \
                           f"Plazas: **{plazas}**\n\n" \
                           f"¡Reserva inmediatamente!"
            send_telegram_message(msg_telegram)
            log("🎉 Monitorización finalizada con éxito (Plazas encontradas).")
            # Notificar éxito final a la UI
            Clock.schedule_once(lambda dt: App.get_running_app().root.update_result_text(f"✅ ¡PLAZA ENCONTRADA! {plazas} disponibles.\nMONITORIZACIÓN DETENIDA."), 0)
            break 
        
        elif plazas == 0:
            log(f"😴 Actividad sigue COMPLETA. Esperando {SLEEP_SECONDS // 60} minutos.")
            
            # Enviar notificación de estado
            msg_status = f"🔄 *Monitorización en curso* 🔄\n\n" \
                         f"Clase: *{ACTIVITY_NAME}*\n" \
                         f"Día: {TARGET_DAY} de {TARGET_MONTH}\n" \
                         f"Estado: **COMPLETO** (0 plazas)\n" \
                         f"Próximo chequeo: en 10 min."
            send_telegram_message(msg_status)
            
            # Notificar estado a la UI
            Clock.schedule_once(lambda dt: App.get_running_app().root.update_result_text(f"⚠️ Actividad COMPLETA (0 plazas).\nChequeo en 10 minutos.\nMonitor ACTIVO..."), 0)

            time.sleep(SLEEP_SECONDS)
            
        elif plazas == -2:
             log("🥳 El usuario se ha inscrito durante la monitorización. Deteniendo.")
             # Notificar inscripción a la UI
             Clock.schedule_once(lambda dt: App.get_running_app().root.update_result_text(f"🥳 ¡YA ESTÁS INSCRITO!\nMONITORIZACIÓN DETENIDA."), 0)
             break 
            
        else: # plazas == -1 (Error)
            log("❌ Error en la verificación. Intentando de nuevo en 5 minutos.")
            # Notificar error a la UI
            Clock.schedule_once(lambda dt: App.get_running_app().root.update_result_text(f"❌ Error en la verificación.\nIntentando de nuevo en 10 minutos."), 0)
            time.sleep(SLEEP_SECONDS)

# ===============================
# INTERFAZ GRÁFICA (KIVY)
# ===============================

class EnjoyKivyForm(BoxLayout):
    """
    Interfaz principal de Kivy.
    """
    
    result_text = StringProperty("Selecciona y busca la actividad.")
    # NUEVO: Propiedad para acumular y mostrar el log detallado del bot
    log_buffer = StringProperty("") 

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.padding = dp(25)
        self.spacing = dp(20)
        self.executor = ThreadPoolExecutor(max_workers=3)
        self.init_ui()

    # NUEVO: Métodos de log para conectar la función global log() con la UI
    def append_log(self, msg):
        """Añade un mensaje al buffer de log de forma segura."""
        Clock.schedule_once(lambda dt: self._append_ui_log(msg), 0)

    def _append_ui_log(self, msg):
        """Actualiza la propiedad vinculada a la UI con el log."""
        timestamp = f"[{datetime.now().strftime('%H:%M:%S')}] "
        self.log_buffer += timestamp + msg + "\n"
        
    def update_result_text(self, text):
        """Método seguro para actualizar el resultado principal desde cualquier hilo."""
        Clock.schedule_once(lambda dt: self._update_ui_text(text), 0)

    def _update_ui_text(self, text):
        """Actualiza la propiedad result_text."""
        self.result_text = text
        
    def _update_combined_text(self, *args):
        """Combina el mensaje de estado principal y el log detallado para mostrarlo."""
        if self.log_buffer:
            self.result_label.text = (
                f"--- ESTADO PRINCIPAL ---\n"
                f"{self.result_text}\n\n"
                f"--- REGISTRO DETALLADO ---\n"
                f"{self.log_buffer}"
            )
        else:
            self.result_label.text = self.result_text

    def init_ui(self):
        # Título
        self.add_widget(Label(text="Reserva tu Actividad - Enjoy", 
                              font_size='20sp', 
                              bold=True, 
                              size_hint_y=None, 
                              height=dp(40)))

        # Frame de Controles (Spinner)
        input_layout = BoxLayout(orientation='vertical', spacing=dp(10), size_hint_y=None, height=dp(250))
        
        # 1. Actividad
        self.activity_spinner = self._add_spinner(input_layout, "Actividad:", ACTIVIDADES_DISPONIBLES[0], ACTIVIDADES_DISPONIBLES)
        
        # 2. Hora
        self.hour_spinner = self._add_spinner(input_layout, "Hora:", HORAS_DISPONIBLES[0], HORAS_DISPONIBLES)
        
        # 3. Día
        dia_actual = str(datetime.now().day)
        self.day_spinner = self._add_spinner(input_layout, "Día:", dia_actual, DIAS_DISPONIBLES)
        
        # 4. Mes
        mes_actual = MESES_DISPONIBLES[datetime.now().month - 1]
        self.month_spinner = self._add_spinner(input_layout, "Mes:", mes_actual, MESES_DISPONIBLES)

        self.add_widget(input_layout)
        
        # Botones
        button_layout = BoxLayout(spacing=dp(20), size_hint_y=None, height=dp(50))
        self.search_btn = Button(text="🔍 BUSCAR PLAZAS", 
                                 on_press=self.iniciar_busqueda, 
                                 background_color=(0, 0.6, 0.8, 1))
        button_layout.add_widget(self.search_btn)
        
        self.exit_btn = Button(text="❌ Salir", on_press=App.get_running_app().stop, 
                                background_color=(0.8, 0.2, 0.2, 1))
        button_layout.add_widget(self.exit_btn)
        self.add_widget(button_layout)
        
        # Área de Resultados - Título
        self.add_widget(Label(text="Estado de la búsqueda:", 
                              font_size='12sp', bold=True, 
                              halign='left', valign='top', 
                              size_hint_y=None, height=dp(20),
                              text_size=(self.width, None)))

        # Usamos un ScrollView y Label para el área de texto.
        scroll_view = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self.result_label = Label(text=self.result_text, # Empezamos con result_text
                                  size_hint_y=None,
                                  text_size=(self.width - dp(40), None), 
                                  padding=(dp(10), dp(10)),
                                  halign='left',
                                  valign='top')
        
        # 🐛 CORRECCIÓN DEL ERROR: Soluciona el ValueError
        # Asigna explícitamente solo la altura (índice 1) del texture.size
        self.result_label.bind(texture_size=lambda instance, size: setattr(instance, 'height', size[1])) 
        
        # 🎯 VINCULACIÓN DEL LOG: Vinculamos los cambios de result_text y log_buffer 
        # a una función que combina ambos para mostrar el log en la UI
        self.bind(result_text=self._update_combined_text, log_buffer=self._update_combined_text)
        
        # Enlace dinámico para reajustar el ancho del texto al redimensionar la ventana
        self.bind(width=lambda *x: self.result_label.setter('text_size')(self.result_label, (self.width - dp(40), None)))
        
        scroll_view.add_widget(self.result_label)
        self.add_widget(scroll_view)
        
        # Inicializa el texto
        self._update_combined_text()


    def _add_spinner(self, parent, label_text, default_val, values_list):
        row_layout = BoxLayout(orientation='horizontal', spacing=dp(10), size_hint_y=None, height=dp(30))
        row_layout.add_widget(Label(text=label_text, size_hint_x=0.35, halign='left', text_size=(dp(150), None)))
        
        spinner = Spinner(text=default_val, 
                          values=values_list, 
                          size_hint_x=0.65,
                          background_color=(0.2, 0.4, 0.6, 1))
        
        row_layout.add_widget(spinner)
        parent.add_widget(row_layout)
        return spinner
        
    # --- Lógica de Búsqueda ---
    def iniciar_busqueda(self, instance):
        if not all([self.activity_spinner.text, self.hour_spinner.text, self.day_spinner.text, self.month_spinner.text]):
            self.update_result_text("Error: Por favor, selecciona todos los campos.")
            return
        
        # 🎯 Limpiar el log y el estado al iniciar
        self.log_buffer = "" 
        self.result_text = "🔄 Iniciando navegador...\nPor favor espera..."
        self.search_btn.disabled = True
        
        # Envía la ejecución de la función principal a un hilo
        future = self.executor.submit(self.ejecutar_busqueda)
        Clock.schedule_interval(lambda dt: self.check_search_result(future), 0.1)
    
    def check_search_result(self, future):
        if future.done():
            Clock.unschedule(self.check_search_result)
            try:
                plazas = future.result(timeout=1)
                self.mostrar_resultado(plazas)
            except TimeoutError:
                self.mostrar_error("El proceso tardó demasiado tiempo.")
            except Exception as e:
                self.mostrar_error(str(e))
            return False 
        return True 
    
    def ejecutar_busqueda(self):
        """Prepara las variables globales y ejecuta el bot."""
        global ACTIVITY_NAME, ACTIVITY_HOUR, TARGET_DAY, TARGET_MONTH
        ACTIVITY_NAME = self.activity_spinner.text
        ACTIVITY_HOUR = self.hour_spinner.text
        TARGET_DAY = self.day_spinner.text
        TARGET_MONTH = self.month_spinner.text
        return run_bot(headless=False) 
    
    def mostrar_error(self, error):
        self.search_btn.disabled = False
        self.update_result_text(f"💥 ERROR TÉCNICO: Revisa el log detallado.\n{error}")
        
    # --- Lógica de Resultados y Monitorización ---
    def mostrar_resultado(self, plazas):
        """Muestra el resultado y lanza monitorización si es necesario."""
        self.search_btn.disabled = False
        
        info = f"📋 {ACTIVITY_NAME} | 🕒 {ACTIVITY_HOUR}\n📅 {TARGET_DAY} de {TARGET_MONTH}"
        
        if plazas > 0:
            msg_app = f"✅ ¡ÉXITO! {plazas} PLAZAS DISPONIBLES\n\n{info}"
            msg_telegram = f"🟢 *¡PLAZAS DISPONIBLES!* 🟢\n\nClase: *{ACTIVITY_NAME}*\n...Plazas: **{plazas}**"
            self.executor.submit(send_telegram_message, msg_telegram)
            self.update_result_text(msg_app)
            
        elif plazas == 0:
            msg_app = f"⚠️ COMPLETO (0 PLAZAS)\n\n{info}\n\n🔴 INICIANDO MONITORIZACIÓN..."
            
            msg_telegram_full = f"⚠️ *ACTIVIDAD COMPLETA* ⚠️\n\nClase: *{ACTIVITY_NAME}*\n...**Activando monitorización (chequeo cada 10 min).**"
            self.executor.submit(send_telegram_message, msg_telegram_full)
            
            # LANZAR EL MONITOR EN UN NUEVO HILO
            self.executor.submit(run_monitor, ACTIVITY_NAME, ACTIVITY_HOUR, TARGET_DAY, TARGET_MONTH)
            self.update_result_text(msg_app)
            
        elif plazas == -2: # Caso INSCRITO
            msg_app = f"🥳 ¡YA ESTÁS INSCRITO!\n\n{info}\n\nMonitorización no requerida."
            
            msg_telegram_full = f"🥳 *¡INSCRITO CORRECTAMENTE!* 🥳\n\nClase: *{ACTIVITY_NAME}*\n...No se requiere monitorización."
            self.executor.submit(send_telegram_message, msg_telegram_full)
            self.update_result_text(msg_app)

        else: # plazas == -1 (Error/No encontrada)
            msg = f"❌ NO ENCONTRADA\n\n{info}\nRevisa el log detallado si hay un error de scraping."
            self.update_result_text(msg)

class EnjoyApp(App):
    def build(self):
        self.title = "Enjoy - Buscador de Actividades (Kivy)"
        return EnjoyKivyForm()
    
    def on_stop(self):
        log("👋 Deteniendo ThreadPoolExecutor.")
        root = self.root
        if isinstance(root, EnjoyKivyForm) and root.executor:
            root.executor.shutdown(wait=False)
        return True

if __name__ == "__main__":
    EnjoyApp().run()

