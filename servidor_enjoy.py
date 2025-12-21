from playwright.sync_api import sync_playwright, expect, TimeoutError as PlaywrightTimeoutError
from datetime import datetime
from pathlib import Path
import json
#import tkinter as tk
#from tkinter import ttk, messagebox
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import re
import requests 
import time # Importado para la función time.sleep()
import os
import logging
import sys

# Configuración de logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

log = logging.getLogger("EnjoyBot")

# Importar Tkinter solo si NO estamos en Render
if os.getenv("RENDER", "").lower() != "true":
    import tkinter as tk
    from tkinter import ttk, messagebox
else:
    tk = None
    ttk = None
    messagebox = None

# ===============================
# CONFIGURACIÓN
# ===============================
LOGIN_URL = "https://member.resamania.com/enjoy"
PLANNING_URL = "https://member.resamania.com/enjoy/planning?autologintoken=4a6425141ee392a2b1a1"
STATE_FILE = Path("enjoy_state.json")


# --- CREDENCIALES ---

USERNAME = os.getenv("ENJOY_USERNAME", "")
PASSWORD = os.getenv("ENJOY_PASSWORD", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# --- VARIABLE ÚNICA PARA DETECTAR SERVIDOR ---
IS_SERVER = os.getenv("RENDER", "").lower() == "true"
# --------------------

# Configuración de timeouts (ms)
TIMEOUT_CONFIG = {
    'navigation': 30000,
    'element': 10000,
    'short_wait': 2000,
    'long_wait': 5000
}

# --- CONFIGURACIÓN DE TELEGRAM ---

# ------------------------------------

# Variables globales (se establecen al iniciar la búsqueda)
ACTIVITY_NAME = ""
ACTIVITY_HOUR = ""
TARGET_DAY = ""
TARGET_MONTH = ""

# ===============================
# CONFIGURACIÓN DE LISTAS
# ===============================
# Generamos las horas de 17:00 a 20:30 en tramos de 15 min
HORAS_DISPONIBLES = []
for h in range(7, 21): 
    for m in [0, 15, 30, 45]:
        if h == 20 and m > 30: break 
        HORAS_DISPONIBLES.append(f"{h:02d}:{m:02d}")

ACTIVIDADES_DISPONIBLES = ["BODY PUMP", "ZUMBA", "PILATES","GAP","AQUAGYM","BODY BALANCE", "CICLO INDOOR","FUNCIONAL 360","BODY BALANCE VIRTUAL", "CICLO INDOOR VIRTUAL","BODY COMBAT","BODY COMBAT VIRTUAL"]
DIAS_DISPONIBLES = [str(i) for i in range(1, 32)]
MESES_DISPONIBLES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"
]


# ===============================
# UTILIDADES
# ===============================
def log(msg):
    """Log con timestamp"""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

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
            log(f"   Respuesta: {response.text}")
            return False
    except Exception as e:
        log(f"💥 Error de conexión al enviar Telegram: {e}")
        return False

# --- FUNCIÓN DE MONITORIZACIÓN ---
def run_monitor(activity, hour, day, month):
    """
    Ejecuta el bot en un bucle cada 5 minutos hasta encontrar plazas.
    """
    global ACTIVITY_NAME, ACTIVITY_HOUR, TARGET_DAY, TARGET_MONTH
    
    ACTIVITY_NAME = activity
    ACTIVITY_HOUR = hour
    TARGET_DAY = day
    TARGET_MONTH = month
    
    log(f"🕵️‍♂️ INICIANDO MONITORIZACIÓN: {activity} a las {hour} - DÍA {day}/{month}")
    
    # 5 minutos = 300 segundos
    SLEEP_SECONDS = 300 
    
    while True:
        log("🔄 Ejecutando verificación en modo monitor...")
        
        # Llamamos a la función principal en modo silencioso (headless=True)
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
            break # Salir del bucle
        
        elif plazas == 0:
            log(f"😴 Actividad sigue COMPLETA. Esperando {SLEEP_SECONDS // 60} minutos.")
            time.sleep(SLEEP_SECONDS)
            
        elif plazas == -2:
             log("🥳 El usuario se ha inscrito durante la monitorización. Deteniendo.")
             break # Ya inscrito, detener monitor
            
        else: # plazas == -1 (Error)
            log("❌ Error en la verificación. Intentando de nuevo en 5 minutos.")
            time.sleep(SLEEP_SECONDS)

# ===============================
# INTERFAZ GRÁFICA
# ===============================
class EnjoyForm:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Enjoy - Buscador de Actividades")
        self.root.geometry("480x550") 
        self.root.resizable(False, False)
        self.executor = ThreadPoolExecutor(max_workers=2) 
        self.setup_ui()
    
    def setup_ui(self):
        # ... (setup_ui, _add_combo, update_result_text, on_close permanecen igual) ...
        main_frame = ttk.Frame(self.root, padding="25")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        ttk.Label(main_frame, text="Reserva tu Actividad", 
                 font=("Segoe UI", 16, "bold")).grid(row=0, column=0, columnspan=2, pady=(0, 25))
        
        self.activity_var = self._add_combo(main_frame, "Actividad:", ACTIVIDADES_DISPONIBLES[0], ACTIVIDADES_DISPONIBLES, 1)
        self.hour_var = self._add_combo(main_frame, "Hora:", HORAS_DISPONIBLES[0], HORAS_DISPONIBLES, 2)
        
        dia_actual = str(datetime.now().day)
        self.day_var = self._add_combo(main_frame, "Día:", dia_actual, DIAS_DISPONIBLES, 3)
        
        mes_actual = MESES_DISPONIBLES[datetime.now().month - 1]
        self.month_var = self._add_combo(main_frame, "Mes:", mes_actual, MESES_DISPONIBLES, 4)
        
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=5, column=0, columnspan=2, pady=30)
        
        self.search_btn = ttk.Button(button_frame, text="🔍 BUSCAR PLAZAS", 
                                     command=self.iniciar_busqueda, width=20)
        self.search_btn.grid(row=0, column=0, padx=10)
        
        ttk.Button(button_frame, text="❌ Salir", 
                  command=self.on_close).grid(row=0, column=1, padx=10)
        
        lbl_result = ttk.Label(main_frame, text="Estado de la búsqueda:", font=("Segoe UI", 10, "bold"))
        lbl_result.grid(row=6, column=0, sticky=tk.W, pady=(10, 5))
        
        self.result_text = tk.Text(main_frame, height=8, width=50, font=("Consolas", 10))
        self.result_text.grid(row=7, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        self.result_text.config(state="disabled") 
        
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
        main_frame.columnconfigure(1, weight=1)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

    def _add_combo(self, parent, label_text, default_val, values_list, row):
        ttk.Label(parent, text=label_text, font=("Segoe UI", 10)).grid(row=row, column=0, sticky=tk.W, pady=8)
        var = tk.StringVar(value=default_val)
        combo = ttk.Combobox(parent, textvariable=var, values=values_list, state="readonly", width=28)
        combo.grid(row=row, column=1, sticky=(tk.W, tk.E), pady=8, padx=(10, 0))
        return var
    
    def update_result_text(self, text):
        self.result_text.config(state="normal")
        self.result_text.delete(1.0, tk.END)
        self.result_text.insert(tk.END, text)
        self.result_text.config(state="disabled")
    
    def on_close(self):
        self.executor.shutdown(wait=False)
        self.root.quit()
        self.root.destroy()
        
    def run(self):
        self.root.mainloop()

    # --- Lógica de Búsqueda ---
    def iniciar_busqueda(self):
        if not all([self.activity_var.get(), self.hour_var.get(), self.day_var.get(), self.month_var.get()]):
            messagebox.showerror("Error", "Por favor, selecciona todos los campos")
            return
        
        self.search_btn.config(state="disabled")
        self.update_result_text("🔄 Iniciando navegador...\nPor favor espera...")
        
        future = self.executor.submit(self.ejecutar_busqueda)
        self.root.after(100, self.check_search_result, future)
    
    def check_search_result(self, future):
        if future.done():
            try:
                plazas = future.result(timeout=1)
                self.mostrar_resultado(plazas)
            except TimeoutError:
                self.mostrar_error("El proceso tardó demasiado tiempo.")
            except Exception as e:
                self.mostrar_error(str(e))
        else:
            self.root.after(100, self.check_search_result, future)
    
    def ejecutar_busqueda(self):
        global ACTIVITY_NAME, ACTIVITY_HOUR, TARGET_DAY, TARGET_MONTH
        ACTIVITY_NAME = self.activity_var.get()
        ACTIVITY_HOUR = self.hour_var.get()
        TARGET_DAY = self.day_var.get()
        TARGET_MONTH = self.month_var.get()
        return run_bot() 
    
    def mostrar_error(self, error):
        self.search_btn.config(state="normal")
        self.update_result_text(f"💥 ERROR TÉCNICO:\n{error}")
        messagebox.showerror("Error", f"Ocurrió un error:\n{error}")

    # --- Lógica de Resultados y Monitorización (MODIFICADA) ---
    def mostrar_resultado(self, plazas):
        """Muestra el resultado en la interfaz y decide si lanzar monitorización"""
        self.search_btn.config(state="normal")
        
        info = f"📋 {ACTIVITY_NAME} | 🕒 {ACTIVITY_HOUR}\n📅 {TARGET_DAY} de {TARGET_MONTH}"
        
        if plazas > 0:
            msg_app = f"✅ ¡ÉXITO! {plazas} PLAZAS DISPONIBLES\n\n{info}"
            
            msg_telegram = f"🟢 *¡PLAZAS DISPONIBLES!* 🟢\n\n" \
                           f"Clase: *{ACTIVITY_NAME}*\n" \
                           f"Hora: {ACTIVITY_HOUR}\n" \
                           f"Día: {TARGET_DAY} de {TARGET_MONTH}\n" \
                           f"Plazas: **{plazas}**"
            self.executor.submit(send_telegram_message, msg_telegram)
            
            msg = msg_app 
            
        elif plazas == 0:
            msg_app = f"⚠️ COMPLETO (0 PLAZAS)\n\n{info}\n🔴 INICIANDO MONITORIZACIÓN..."
            
            msg_telegram_full = f"⚠️ *ACTIVIDAD COMPLETA* ⚠️\n\n" \
                                f"Clase: *{ACTIVITY_NAME}*\n" \
                                f"Hora: {ACTIVITY_HOUR}\n" \
                                f"Día: {TARGET_DAY} de {TARGET_MONTH}\n" \
                                f"**Activando monitorización (chequeo cada 5 min).**"
            self.executor.submit(send_telegram_message, msg_telegram_full)
            
            # LANZAR EL MONITOR EN UN NUEVO HILO
            self.executor.submit(run_monitor, ACTIVITY_NAME, ACTIVITY_HOUR, TARGET_DAY, TARGET_MONTH)
            
            msg = msg_app 
            
        elif plazas == -2: # Caso INSCRITO
            msg_app = f"🥳 ¡YA ESTÁS INSCRITO!\n\n{info}\n\nNo se requiere monitorización."
            
            msg_telegram_full = f"🥳 *¡INSCRITO CORRECTAMENTE!* 🥳\n\n" \
                                f"Clase: *{ACTIVITY_NAME}*\n" \
                                f"Hora: {ACTIVITY_HOUR}\n" \
                                f"Día: {TARGET_DAY} de {TARGET_MONTH}\n" \
                                f"No se requiere monitorización."
            self.executor.submit(send_telegram_message, msg_telegram_full)
            
            msg = msg_app 

        else: # plazas == -1 (Error/No encontrada)
            msg = f"❌ NO ENCONTRADA\n\n{info}\nRevisa si la clase existe ese día."
            
        self.update_result_text(msg)

# ===============================
# GESTIÓN DE SESIÓN
# ===============================
class SessionManager:
    
    @staticmethod
    def is_logged_in(page):
        """Detecta si hay sesión activa y NO estamos en la página de login."""
        try:
            # 1. Comprobar indicadores de éxito
            indicators_of_success = [
                page.locator("text=Planificación"),
                page.locator("a:has-text('Cerrar sesión')"),
            ]
            
            is_success_indicated = any(ind.count() > 0 for ind in indicators_of_success) or "planning" in page.url.lower()

            # 2. Comprobar si estamos en la URL de LOGIN (Esto anula el éxito)
            is_on_login_page = "login" in page.url.lower()

            return is_success_indicated and not is_on_login_page # Solo True si hay indicadores de éxito Y NO estamos en el login
        except Exception:
            return False
    
    @staticmethod
    def restore_session(page):
        """Intenta restaurar sesión guardada"""
        if not STATE_FILE.exists():
            return False
        
        log("🔄 Restaurando sesión guardada...")
        try:
            page.goto(PLANNING_URL, wait_until="domcontentloaded", timeout=TIMEOUT_CONFIG['navigation'])
            page.wait_for_load_state("networkidle", timeout=TIMEOUT_CONFIG['long_wait'])
            
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
    @staticmethod
    def _click_login_button(page):
        # 1. Selectores basados en texto (actuales, más un par de variantes)
        selectors = [
            "button:has-text('Iniciar sesión')",
            "a:has-text('Iniciar sesión')",
            "button:has-text('Acceder')",   # <--- NUEVO: "Acceder"
            "button:has-text('Entrar')"
        ]
        
        # 2. Selectores basados en la estructura o el rol (más robustos)
        robust_selectors = [
            "[role='button']:has-text('sesión' i), [role='button']:has-text('Acceder' i)", # Elementos con rol de botón y texto 'sesión' o 'Acceder'
            "button[type='submit']", # Botones de envío
            "a[href*='login']",      # Enlaces con 'login' en la URL
        ]
        
        all_selectors = selectors + robust_selectors
        
        log("🖱️ Buscando botón de inicio de sesión...")
        for selector in all_selectors:
            try:
                # Usamos page.locator(selector).all() para iterar
                elements = page.locator(selector).all()
                for elem in elements:
                    if elem.is_visible() and elem.is_enabled():
                        log(f"   ✅ Click en selector robusto: '{selector}'")
                        elem.click(timeout=TIMEOUT_CONFIG['element'])
                        page.wait_for_timeout(TIMEOUT_CONFIG['short_wait'])
                        return True
            except:
                continue
                
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
# GESTIÓN DE FECHAS (ROBUSTO)
# ===============================
class DateNavigator:
    @staticmethod
    def ensure_date_selected(page, max_retries=3):
        """Garantiza que la fecha objetivo esté seleccionada"""
        log(f"🎯 Seleccionando fecha: {TARGET_DAY} de {TARGET_MONTH}")
        screenshot(page, "antes_seleccion_fecha")
        
        for attempt in range(max_retries):
            try:
                log(f"🔄 Intento {attempt + 1}/{max_retries}")
                DateNavigator._debug_page_content(page)
                
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
    def _debug_page_content(page):
        try:
            day_elements = page.locator(f"text={TARGET_DAY}").all()
            log(f"🔍 Elementos con día '{TARGET_DAY}' encontrados: {len(day_elements)}")
            month_elements = page.locator(f"text=/{TARGET_MONTH[:3]}/i").all()
            log(f"🔍 Elementos con mes '{TARGET_MONTH}' encontrados: {len(month_elements)}")
        except Exception: pass
    
    @staticmethod
    def _click_day_directly(page):
        """Intenta hacer click directamente en el día sin navegar"""
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
        
        log("   ❌ No se pudo hacer click directo")
        return False
    
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
# BÚSQUEDA DE ACTIVIDADES (ROBUSTO)
# ===============================
class ActivityFinder:
    @staticmethod
    def get_planning_frame(page):
        """Obtiene el frame de planificación"""
        log("🧩 Buscando frame de planificación...")
        for frame in page.frames:
            if "planning" in frame.url or "resamania" in frame.url:
                return frame
        return page
    
    @staticmethod
    def wait_for_activities(frame):
        """Espera a que carguen las actividades"""
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
        """Realiza scroll agresivo"""
        try:
            for _ in range(3):
                page.mouse.wheel(0, 3000)
                page.wait_for_timeout(500)
            page.mouse.wheel(0, -3000)
            return True
        except: return False

    # --- MODIFICADO: Búsqueda robusta con subida de niveles ---
    # DENTRO DE LA CLASE ActivityFinder (REEMPLAZO COMPLETO)
    @staticmethod
    def find_activity(frame):
        """Busca la actividad usando filtros de contenido (MÁS ROBUSTO)"""
        global ACTIVITY_NAME, ACTIVITY_HOUR
        
        # 1. Usar expresión regular para búsqueda insensible a mayúsculas/minúsculas
        activity_regex = f"/{re.escape(ACTIVITY_NAME)}/i"
        
        log(f"🎯 Buscando tarjeta con: '{ACTIVITY_NAME}' (Regex: {activity_regex}) Y '{ACTIVITY_HOUR}'")
        
        try:
            # Búsqueda inicial del nombre de la actividad (Insensible a mayúsculas)
            candidates = frame.locator(f"text={activity_regex}")
            count = candidates.count()
            log(f"   🔎 Elementos con el nombre encontrados: {count}")
            
            if count == 0: return -1

            for i in range(count):
                element = candidates.nth(i)
                parent = element
                
                # 2. Buscamos en el contenedor (hasta 7 niveles de padre)
                for level in range(7): 
                    try:
                        text = parent.text_content()
                        clean_text = " ".join(text.split()).upper()
                        
                        # 3. Verificar si el contenedor contiene la HORA
                        # Usamos la hora completa o la hora sin minutos para mayor robustez
                        hour_check = ACTIVITY_HOUR.replace(':00', '') 
                        
                        if ACTIVITY_HOUR in clean_text or hour_check in clean_text:
                            log(f"   ✅ ¡Coincidencia de HORA encontrada en contenedor (Nivel {level})!")
                            log(f"   📄 Texto contenedor analizado: {clean_text[:100]}...")
                            
                            # 4. Extraemos plazas de este contenedor confirmado
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
    
    # --- MODIFICADO: Extracción de plazas (Filtra "Inscrito" y "42") ---
    # DENTRO DE LA CLASE ActivityFinder (REEMPLAZO COMPLETO)
    @staticmethod
    def _extract_spots(element):
        """Extrae plazas, maneja COMPLETO, INSCRITO, y ajusta la restricción de números."""
        text = element.text_content()
        clean_text = " ".join(text.split()) 
        
        log(f"   🔢 Analizando plazas en: '{clean_text[:60]}...'")

        # 1. BÚSQUEDA POR SELECTORES Y BOTONES (MÁXIMA PRIORIDAD)
        # --------------------------------------------------------
        
        # Buscar botones o indicadores de estado en el contenedor
        # Buscamos botones de "Anular", "Apuntarse" o indicadores visuales
        
        # Buscamos 'Anular' (si aparece 'Anular', el usuario está INSCRITO)
        try:
            if element.locator("button:has-text('Anular')").count() > 0 or \
               element.locator("button:has-text('Cancelar')").count() > 0:
                log("   ✅ DETECTADO BOTÓN 'Anular/Cancelar'. Usuario INSCRITO.")
                return -2 # Código para 'INSCRITO'
        except Exception: pass
        
        # Buscamos 'COMPLETO' o 'Lista de Espera'
        if "completo" in clean_text.lower() or "lista de espera" in clean_text.lower() or "no quedan plazas" in clean_text.lower():
            log("   🔴 DETECTADO TEXTO 'COMPLETO' o 'Lista de Espera'.")
            return 0

        # Si el texto ya contiene 'INSCRITO' y no tiene el botón 'Anular', es una lectura errónea,
        # pero para ser cautelosos, si no detectamos "COMPLETO" y vemos "INSCRITO" aún lo marcamos.
        if "inscrito" in clean_text.lower() or "reservado" in clean_text.lower():
            log("   ⚠️ DETECTADO TEXTO 'INSCRITO' (Sin botón Anular). Asumiendo INSCRITO.")
            return -2 # Código para 'INSCRITO'


        # 2. BÚSQUEDA POR CONTEO DE PLAZAS
        # --------------------------------

        # A. Regex: "N plazas vacantes" (Prioritaria)
        match_exact = re.search(r'(\d+)\s*plazas?\s*vacantes?', clean_text, re.IGNORECASE)
        if match_exact:
            spots = int(match_exact.group(1))
            log(f"   🎉 ¡Plazas encontradas (Específica 'vacantes'): {spots}!")
            return spots
            
        # B. Regex: "Quedan N plazas"
        match_quedan = re.search(r'(?:quedan|disponibles|libres):\s*(\d+)', clean_text, re.IGNORECASE)
        if match_quedan:
            spots = int(match_quedan.group(1))
            log(f"   🎉 ¡Plazas encontradas (Quedan/Disponibles): {spots}!")
            return spots

        # C. (FALLBACK y Ajuste para 54) Buscamos números seguidos por 'plazas'
        match_fallback = re.search(r'(\d+)\s*plazas', clean_text, re.IGNORECASE)
        if match_fallback:
             spots = int(match_fallback.group(1))
             
             # **AJUSTE CRÍTICO:** Subimos el límite para permitir 54 plazas.
             if spots < 100: 
                 log(f"   ⚠️ ¡Plazas encontradas (Fallback/Baja confianza): {spots}! (Límite: 100)")
                 return spots
             log("   ⚠️ Fallback ignorado (Número de plazas demasiado alto > 100).")

        log("   ⚠️ No se detectó un número de plazas válido en este contenedor.")
        return -1

# ===============================
# FUNCIÓN PRINCIPAL
# ===============================
def run_bot(headless=False):
    """Ejecuta el bot y retorna número de plazas. Acepta headless para monitorización."""
    log("🚀 Iniciando bot...")
    log(f"🎯 Objetivo: {ACTIVITY_NAME} {ACTIVITY_HOUR} ({TARGET_DAY} {TARGET_MONTH})")
    
    with sync_playwright() as p:
        # Pasa el argumento 'headless'
        browser = p.chromium.launch(headless=headless) 
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        
        try:
            # --- SECCIÓN MODIFICADA ---
            if SessionManager.restore_session(page):
                # 1. Si la restauración se hizo (logueado = True en restore_session):
                #    Aseguramos que la URL sea la de PLANNING y el estado sea 'networkidle'.
                page.goto(PLANNING_URL, wait_until="networkidle", timeout=TIMEOUT_CONFIG['navigation'])
                page.wait_for_timeout(TIMEOUT_CONFIG['long_wait'])

                if SessionManager.is_logged_in(page):
                    log("✅ Sesión restaurada y verificada.")
                else:
                    log("⚠️ Sesión restaurada inválida. Forzando login completo.")
                    if not SessionManager.perform_login(page, context):
                        log("❌ Fallo de autenticación tras restauración")
                        return -1
            
            else:
                # 2. Si restore_session devolvió False (no existe archivo o fallo la navegacion inicial):
                if not SessionManager.perform_login(page, context):
                    log("❌ Fallo de autenticación")
                    return -1
            # --- FIN SECCIÓN MODIFICADA ---
            
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

# ===============================================================
# MODO DUAL: LOCAL (GUI) o SERVIDOR (RENDER)
# ===============================================================

if __name__ == "__main__":

    if IS_SERVER:
        log("🌐 MODO SERVIDOR ACTIVADO (Render)")

        # Actividad desde variables de entorno o valores por defecto
        activity = os.getenv("ENJOY_ACTIVITY", "AQUAGYM    ")
        hour = os.getenv("ENJOY_HOUR", "09:30")
        day = os.getenv("ENJOY_DAY", "21")
        month = os.getenv("ENJOY_MONTH", "DICIEMBRE")

        log(f"📌 Monitorizando automáticamente: {activity} {hour} {day}/{month}")

        run_monitor(activity, hour, day, month)

    else:
        log("🖥️ MODO LOCAL (GUI)")
        app = EnjoyForm()
        app.run()



