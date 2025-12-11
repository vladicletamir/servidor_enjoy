from playwright.sync_api import sync_playwright, expect, TimeoutError as PlaywrightTimeoutError
from datetime import datetime
from pathlib import Path
import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError
import re
import requests 
import time
import os

# ==========================================================
# CONDICIONAL PARA ENTORNO HEADLESS (Tkinter/ttk/messagebox)
# ==========================================================
try:
    import tkinter as tk
    from tkinter import ttk, messagebox
    GUI_AVAILABLE = True
    print("[SETUP] ✅ Módulos GUI (Tkinter) cargados para entorno local.")
    
except ImportError:
    print("[SETUP] ⚠️ Módulos GUI (Tkinter/ttk) no encontrados. Ejecutando en modo servidor (headless).")
    GUI_AVAILABLE = False
    
    # ------------------------------------------------------
    # DEFINICIÓN DE MOCKS PARA EVITAR 'NameError'
    # ------------------------------------------------------
    class DummyModule:
        def __init__(self, *args, **kwargs): pass
        def __getattr__(self, name): return lambda *args, **kwargs: self
        def Tk(self): return self
        def mainloop(self): pass
        def protocol(self, *args): pass
        def quit(self): pass
        def destroy(self): pass
        def geometry(self, *args): pass
        def resizable(self, *args): pass
        def columnconfigure(self, *args): pass
        def rowconfigure(self, *args): pass
        def after(self, *args): pass
        def config(self, *args, **kwargs): return self
        def delete(self, *args): pass
        def insert(self, *args): pass
        def grid(self, *args, **kwargs): pass
        def submit(self, *args): pass
        def shutdown(self, *args): pass

    class DummyStringVar:
        def __init__(self, *args, **kwargs): self.value = kwargs.get('value', '')
        def get(self): return self.value
        def set(self, val): self.value = val
    
    class DummyMessagebox:
        def showerror(*args, **kwargs): 
            print("Mock: messagebox.showerror llamado (Ignorado en servidor)")

    tk = DummyModule()
    ttk = DummyModule()
    messagebox = DummyMessagebox()
    tk.StringVar = DummyStringVar


# ===============================
# CONFIGURACIÓN
# ===============================
LOGIN_URL = "https://member.resamania.com/enjoy"
PLANNING_URL = "https://member.resamania.com/enjoy/planning?autologintoken=4a6425141ee392a2b1a1"
STATE_FILE = Path("enjoy_state.json")

# --- CREDENCIALES ---
USERNAME = "anaurma@hotmail.com" # <--- VERIFICAR
PASSWORD = "Kerkrade1126" # <--- VERIFICAR
# --------------------

# Configuración de timeouts (ms)
TIMEOUT_CONFIG = {
    'navigation': 30000,
    'element': 10000,
    'short_wait': 2000,
    'long_wait': 5000
}

# --- CONFIGURACIÓN DE TELEGRAM ---
TELEGRAM_BOT_TOKEN = "7576773682:AAE8_4OC9lLAFNlOWBbFmYGj5MFDfkQxAsU" # <--- TU TOKEN
TELEGRAM_CHAT_ID = "1326867840" # <--- TU ID
# ------------------------------------
# Variables globales (se establecen al iniciar la búsqueda)
ACTIVITY_NAME = ""
ACTIVITY_HOUR = ""
TARGET_DAY = ""
TARGET_MONTH = ""

# ===============================
# CONFIGURACIÓN DE LISTAS
# ===============================
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
    
    SLEEP_SECONDS = 300  # 5 minutos
    
    while True:
        log("🔄 Ejecutando verificación en modo monitor...")
        
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
            break
        
        elif plazas == 0:
            log(f"😴 Actividad sigue COMPLETA. Esperando {SLEEP_SECONDS // 60} minutos.")
            time.sleep(SLEEP_SECONDS)
            
        elif plazas == -2:
             log("🥳 El usuario se ha inscrito durante la monitorización. Deteniendo.")
             break
            
        else: # plazas == -1 (Error)
            log("❌ Error en la verificación. Intentando de nuevo en 5 minutos.")
            time.sleep(SLEEP_SECONDS)


# ===============================
# INTERFAZ GRÁFICA (SOLO LOCAL)
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

    def mostrar_resultado(self, plazas):
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
    def _click_login_button(page):
        # AÑADIDO: Selectores en INGLÉS ('Log in')
        selectors = [
            "button:has-text('Log in')",  # <--- CRUCIAL: Esto es lo que sale en tu HTML
            "button:has-text('Sign in')",
            "button:has-text('Iniciar sesión')",
            "a:has-text('Iniciar sesión')",
            "button:has-text('Acceder')",
            "button:has-text('Entrar')"
        ]
        
        robust_selectors = [
            "[role='button']:has-text('sesión' i), [role='button']:has-text('Acceder' i)",
            "[role='button']:has-text('Log in' i)", # <--- Robustez extra
            "button[type='submit']",
            "a[href*='login']",
        ]
        
        all_selectors = selectors + robust_selectors
        
        log("🖱️ Buscando botón de inicio de sesión...")
        for selector in all_selectors:
            try:
                elements = page.locator(selector).all()
                for elem in elements:
                    if elem.is_visible() and elem.is_enabled():
                        log(f"   ✅ Click en selector: '{selector}'")
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
        # AÑADIDO: 'Continue', 'Next', 'Password'
        selectors = [
            "button:has-text('Continue')", 
            "button:has-text('Next')",
            "button:has-text('Password')", # A veces el botón dice "Password" para ir al siguiente paso
            "button:has-text('Introducir mi contraseña')", 
            "button:has-text('Siguiente')"
        ]
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
        # AÑADIDO: 'Log in', 'Sign in'
        selectors = [
            "button:has-text('Log in')", # A veces el botón final también se llama Log in
            "button:has-text('Sign in')",
            "button:has-text('Conectarme a mi club')", 
            "button:has-text('Conectarme')", 
            "button:has-text('Entrar')"
        ]
        for frame in [page] + page.frames:
            for selector in selectors:
                try:
                    if frame.locator(selector).count() > 0:
                        frame.locator(selector).first.click(timeout=TIMEOUT_CONFIG['element'])
                        return True
                except: continue
        return False


# ===============================
# GESTIÓN DE FECHAS - VERSIÓN CORREGIDA
# ===============================
class DateNavigator:
    @staticmethod
    def get_current_selected_day(page):
        """Obtiene el día que está actualmente seleccionado en la página"""
        try:
            # Buscar elementos que indiquen día seleccionado
            selectors = [
                "[class*='selected']", 
                "[class*='active']", 
                "[aria-selected='true']",
                "button[aria-current='date']",
                ".fc-day-today.fc-day-selected",  # Para FullCalendar
                ".rbc-day-selected"  # Para React Big Calendar
            ]
            
            for selector in selectors:
                elements = page.locator(selector).all()
                for elem in elements:
                    text = elem.text_content().strip()
                    # Extraer número del día
                    import re
                    day_match = re.search(r'\b(\d{1,2})\b', text)
                    if day_match:
                        return day_match.group(1)
            
            # Si no encuentra seleccionado, buscar día destacado "HOY"
            hoy_elements = page.locator("text=/hoy/i, text=/today/i").all()
            for elem in hoy_elements:
                parent_text = elem.evaluate('el => el.parentElement.textContent')
                day_match = re.search(r'\b(\d{1,2})\b', parent_text)
                if day_match:
                    return day_match.group(1)
            
            return None
        except:
            return None
    
    @staticmethod
    def ensure_date_selected(page, max_retries=3):
        """Garantiza que la fecha objetivo esté seleccionada - VERSIÓN CORREGIDA"""
        log(f"🎯 Fecha objetivo: {TARGET_DAY} de {TARGET_MONTH}")
        
        # 1. Obtener día actualmente seleccionado
        current_selected_day = DateNavigator.get_current_selected_day(page)
        log(f"   Día actualmente seleccionado: {current_selected_day or 'No detectado'}")
        
        # 2. Si el día objetivo YA está seleccionado, no hacer nada
        if current_selected_day == TARGET_DAY:
            log("✅ El día objetivo YA está seleccionado. No se hace clic.")
            return True
        
        # 3. Si estamos buscando HOY y ya está seleccionado HOY
        from datetime import datetime
        today = datetime.now().day
        if str(today) == TARGET_DAY and current_selected_day == str(today):
            log("✅ Buscamos HOY y HOY ya está seleccionado. No se hace clic.")
            return True
        
        # 4. Si necesitamos cambiar de día
        log(f"🔁 Necesitamos cambiar al día {TARGET_DAY}")
        
        # Intentar seleccionar el día objetivo
        for attempt in range(max_retries):
            try:
                log(f"   Intento {attempt + 1}/{max_retries}")
                
                # PRIMERO: Intentar con el calendario desplegable
                if DateNavigator._select_via_calendar_picker(page):
                    log("✅ Fecha seleccionada via calendario")
                    page.wait_for_timeout(3000)
                    return True
                
                # SEGUNDO: Intentar clic directo en día
                if DateNavigator._click_day_safely(page):
                    log("✅ Día clickeado directamente")
                    page.wait_for_timeout(3000)
                    return True
                
            except Exception as e:
                log(f"💥 Error en intento {attempt + 1}: {e}")
                page.wait_for_timeout(1000)
        
        log("⚠️ No se pudo seleccionar la fecha, continuando...")
        return False
    
    @staticmethod
    def ensure_correct_date_loaded(page):
        """Solución ESPECÍFICA para el problema de la web Enjoy"""
        log("🔍 Verificando estado de la fecha en la página...")
        
        # Obtener todo el texto de la página
        all_text = page.text_content()
        
        # Caso 1: ¿Aparece "Fecha inválida" o "Ningún resultado para este día"?
        if "Fecha inválida" in all_text or "Ningún resultado para este día" in all_text:
            log("⚠️ ¡DETECTADO! La página muestra 'Fecha inválida'")
            log("🔄 Haciendo clic en 'HOY' para corregir...")
            
            # INTENTAR HACER CLIC EN "HOY"
            hoy_selectors = [
                "button:has-text('HOY')",
                "button:has-text('Hoy')", 
                "button:has-text('TODAY')",
                "button:has-text('Today')",
                "[aria-label*='hoy' i]",
                "[aria-label*='today' i]"
            ]
            
            for selector in hoy_selectors:
                try:
                    if page.locator(selector).count() > 0:
                        page.click(selector)
                        log(f"✅ Clic en '{selector}' para seleccionar HOY")
                        page.wait_for_timeout(3000)  # Esperar a que cargue
                        return True
                except:
                    continue
            
            # Si no encuentra "HOY", intentar con la fecha actual
            from datetime import datetime
            today = datetime.now().day
            log(f"🔍 Intentando clic en día {today} (hoy)...")
            
            try:
                page.locator(f"text='{today}'").first.click()
                log(f"✅ Clic en día {today}")
                page.wait_for_timeout(3000)
                return True
            except:
                log("❌ No se pudo hacer clic en HOY o día actual")
        
        # Caso 2: ¿Aparecen fechas antiguas (junio 2022)?
        if "jun. de 2022" in all_text or "junio 2022" in all_text.lower():
            log("⚠️ ¡DETECTADO! La página muestra fechas de junio 2022")
            log("🔄 Intentando corregir fecha a HOY...")
            
            # Buscar selector de fecha y abrirlo
            date_selectors = [
                "button:has-text('FECHA')",
                "input[placeholder*='fecha' i]",
                "[aria-label*='fecha' i]"
            ]
            
            for selector in date_selectors:
                try:
                    if page.locator(selector).count() > 0:
                        page.click(selector)
                        log(f"✅ Abierto selector de fecha: {selector}")
                        page.wait_for_timeout(1000)
                        
                        # Ahora buscar y hacer clic en "HOY" en el calendario
                        hoy_in_calendar = page.locator("button:has-text('HOY'), button:has-text('Hoy'), [aria-label*='hoy' i]").first
                        if hoy_in_calendar.count() > 0:
                            hoy_in_calendar.click()
                            log("✅ Clic en HOY dentro del calendario")
                            page.wait_for_timeout(2000)
                            return True
                except:
                    continue
        
        # Caso 3: Verificar si hay actividades visibles
        actividades_visibles = "INSCRIBIRSE" in all_text or "PLAZA" in all_text
        if not actividades_visibles:
            log("⚠️ No hay actividades visibles, podría ser problema de fecha")
            
            # Esperar un poco más por si está cargando
            page.wait_for_timeout(2000)
            all_text = page.text_content()
            
            # Si después de esperar sigue sin actividades, intentar HOY
            if not ("INSCRIBIRSE" in all_text or "PLAZA" in all_text):
                log("🔄 Sin actividades después de espera, intentando HOY...")
                try:
                    page.locator("button:has-text('HOY'), button:has-text('Hoy')").first.click()
                    page.wait_for_timeout(3000)
                    return True
                except:
                    pass
        
        return True
    
    @staticmethod
    def _select_via_calendar_picker(page):
        """Selecciona fecha usando el selector de calendario (más seguro)"""
        try:
            # Buscar y abrir selector de fecha
            date_selectors = [
                "input[placeholder*='fecha' i]",
                "input[type='date']",
                "[aria-label*='fecha' i]",
                ".date-picker",
                "button:has-text('FECHA')"
            ]
            
            for selector in date_selectors:
                if page.locator(selector).count() > 0:
                    page.click(selector)
                    log(f"   📅 Selector de fecha abierto: {selector}")
                    page.wait_for_timeout(1000)
                    break
            
            # Esperar a que aparezca el calendario
            page.wait_for_selector(".calendar, [role='dialog'], .picker", timeout=5000)
            
            # Buscar y hacer clic en el día objetivo dentro del calendario
            day_in_calendar = page.locator(f".calendar [role='gridcell']:has-text('{TARGET_DAY}'), "
                                          f"[role='dialog'] button:has-text('{TARGET_DAY}'), "
                                          f".picker td:has-text('{TARGET_DAY}')").first
            
            if day_in_calendar.count() > 0:
                day_in_calendar.click()
                log(f"   ✅ Día {TARGET_DAY} seleccionado en calendario")
                
                # Buscar y hacer clic en OK/Confirmar
                ok_buttons = ["button:has-text('OK')", "button:has-text('Aceptar')", 
                            "button:has-text('Confirmar')", "button:has-text('Seleccionar')"]
                for btn in ok_buttons:
                    if page.locator(btn).count() > 0:
                        page.click(btn)
                        log(f"   ✅ Botón {btn} clickeado")
                        return True
                
                # Si no hay botón OK, simplemente cerrar haciendo clic fuera
                page.click("body")
                return True
                
        except Exception as e:
            log(f"   ⚠️ Calendario no disponible: {e}")
            return False
    
    @staticmethod
    def _click_day_safely(page):
        """Hace clic en un día de forma segura (solo si no está seleccionado)"""
        try:
            # Buscar el día en la vista de calendario semanal/mensual
            day_selectors = [
                f"button:has-text('{TARGET_DAY}'):not([class*='selected']):not([class*='active'])",
                f"div:has-text('{TARGET_DAY}'):not([class*='selected']):not([class*='active'])",
                f"td:has-text('{TARGET_DAY}'):not([class*='selected'])",
                f"[role='gridcell']:has-text('{TARGET_DAY}'):not([aria-selected='true'])"
            ]
            
            for selector in day_selectors:
                elements = page.locator(selector).all()
                for elem in elements:
                    if elem.is_visible():
                        # Verificar que no sea el día actual seleccionado
                        elem_class = elem.get_attribute("class") or ""
                        if "selected" not in elem_class and "active" not in elem_class:
                            elem.click()
                            log(f"   ✅ Clic seguro en día {TARGET_DAY}")
                            return True
            
            return False
        except:
            return False


# ===============================
# BÚSQUEDA DE ACTIVIDADES
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

    @staticmethod
    def find_activity(frame):
        """Busca la actividad - VERSIÓN MEJORADA CON DEBUG"""
        global ACTIVITY_NAME, ACTIVITY_HOUR
        
        log(f"🔍 Búsqueda: '{ACTIVITY_NAME}' a las '{ACTIVITY_HOUR}'")
        
        # Obtener TODO el texto de la página
        all_text = frame.text_content().upper()
        log(f"   Texto total: {len(all_text)} caracteres")
        
        # DEBUG: Mostrar si aparece la actividad y hora
        activity_in_text = ACTIVITY_NAME.upper() in all_text
        hour_in_text = ACTIVITY_HOUR in all_text or ACTIVITY_HOUR.replace(':', '.') in all_text
        
        log(f"   '{ACTIVITY_NAME}' en texto: {activity_in_text}")
        log(f"   '{ACTIVITY_HOUR}' en texto: {hour_in_text}")
        
        if not activity_in_text:
            log(f"   ❌ '{ACTIVITY_NAME}' NO aparece en la página")
            return -1
        
        if not hour_in_text:
            log(f"   ⚠️ '{ACTIVITY_HOUR}' NO aparece, buscando solo actividad")
        
        # Buscar elementos que contengan la actividad
        activity_patterns = [
            f"text=/{ACTIVITY_NAME}/i",
            f"text=/{ACTIVITY_NAME.replace(' ', '.*')}/i",
            f":has-text('{ACTIVITY_NAME}')"
        ]
        
        for pattern in activity_patterns:
            try:
                elements = frame.locator(pattern).all()
                log(f"   Patrón '{pattern}': {len(elements)} elementos")
                
                for i, element in enumerate(elements):
                    try:
                        text = element.text_content().upper()
                        
                        # Verificar si también contiene la hora (opcional)
                        hour_found = ACTIVITY_HOUR in text or ACTIVITY_HOUR.replace(':', '.') in text
                        
                        if hour_found or len(elements) == 1:  # Si coincide hora o es el único elemento
                            log(f"   ✅ Coincidencia {i+1}: '{text[:100]}...'")
                            
                            # Extraer plazas
                            plazas = ActivityFinder._extract_spots(element)
                            if plazas != -1:
                                return plazas
                            
                    except Exception as e:
                        continue
                        
            except Exception as e:
                continue
        
        # Último intento: buscar por contexto
        log("   🔄 Intentando búsqueda por contexto...")
        try:
            # Buscar cualquier elemento que tenga "INSCRIBIRSE" cerca
            inscripcion_elements = frame.locator("button:has-text('INSCRIBIRSE'), button:has-text('Inscribirse')").all()
            
            for element in inscripcion_elements:
                # Subir en el DOM para encontrar el contenedor de la actividad
                parent_text = element.evaluate('''el => {
                    let parent = el.parentElement;
                    let text = '';
                    // Subir 3 niveles máximo
                    for (let i = 0; i < 3 && parent; i++) {
                        text = parent.textContent + ' ' + text;
                        parent = parent.parentElement;
                    }
                    return text;
                }''')
                
                parent_text_upper = parent_text.upper()
                if ACTIVITY_NAME.upper() in parent_text_upper:
                    log(f"   ✅ Encontrado via botón INSCRIBIRSE: '{parent_text_upper[:150]}...'")
                    plazas = ActivityFinder._extract_spots(element)
                    if plazas != -1:
                        return plazas
                        
        except Exception as e:
            pass
        
        return -1
# ---------------------------------------------------------
# CÓDIGO NUEVO
# ---------------------------------------------------------


def run_bot(headless=False):
    """Ejecuta el bot y retorna número de plazas"""
    log("🚀 Iniciando bot...")
    log(f"🎯 Objetivo: {ACTIVITY_NAME} {ACTIVITY_HOUR} ({TARGET_DAY} {TARGET_MONTH})")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
       
        try:
            # PASO 1: LOGIN O RESTAURAR
            log("1. Intentando restaurar sesión o login...")
            
            if SessionManager.restore_session(page):
                log("   ✅ Intento de restauración de sesión")
                page.goto(PLANNING_URL, wait_until="networkidle", timeout=TIMEOUT_CONFIG['navigation'])
                page.wait_for_timeout(TIMEOUT_CONFIG['long_wait'])
                
                current_url = page.url
                log(f"   📍 URL después de restore: {current_url}")
                
                if SessionManager.is_logged_in(page):
                    log("   ✅ ¡Sesión restaurada con éxito!")
                else:
                    log("   ❌ Restauración fallida, forzando login...")
                    if not SessionManager.perform_login(page, context):
                        log("   💥 Login fallido después de restore")
                        return -1
            else:
                log("   🔄 No hay sesión guardada, haciendo login completo...")
                if not SessionManager.perform_login(page, context):
                    log("   💥 Login completo fallido")
                    return -1
            
            # PASO 2: VERIFICAR QUE ESTAMOS EN PLANNING
            log("2. Verificando ubicación y esperando la planificación...")
            page.goto(PLANNING_URL, wait_until="networkidle", timeout=TIMEOUT_CONFIG['navigation'])
            page.wait_for_timeout(5000)  # Espera inicial
            
            # NUEVO PASO CRÍTICO: Verificar y corregir fecha si es necesario
            log("3. Verificando estado de la fecha...")
            DateNavigator.ensure_correct_date_loaded(page)
            
            # ESPERA ADICIONAL para asegurar carga completa
            page.wait_for_timeout(3000)
            
            # VERIFICAR: ¿Tenemos actividades visibles ahora?
            current_text = page.text_content()
            if "INSCRIBIRSE" not in current_text and "PLAZA" not in current_text:
                log("⚠️ Aún no hay actividades visibles después de corregir fecha")
                log("🔄 Intentando clic en HOY como último recurso...")
                
                # Último intento: buscar y hacer clic en HOY de forma agresiva
                hoy_selectors = [
                    "//button[contains(., 'HOY')]",
                    "//button[contains(., 'Hoy')]",
                    "//*[contains(text(), 'HOY') and @role='button']"
                ]
                
                for selector in hoy_selectors:
                    try:
                        if page.locator(selector).count() > 0:
                            page.locator(selector).first.click()
                            log(f"✅ Clic agresivo en HOY con selector: {selector}")
                            page.wait_for_timeout(3000)
                            break
                    except:
                        continue
            
            # PASO 4: GESTIÓN DE FECHA OBJETIVO
            log(f"4. Gestionando fecha objetivo: {TARGET_DAY} de {TARGET_MONTH}")
            
            from datetime import datetime
            today = datetime.now().day
            
            # Solo cambiar fecha si NO es hoy
            if str(today) != TARGET_DAY:
                log(f"   🔄 Buscamos día {TARGET_DAY} (no es hoy)")
                
                # Intentar seleccionar el día objetivo
                try:
                    # Buscar el día en la vista semanal
                    day_element = page.locator(f"text='{TARGET_DAY}'").first
                    if day_element.count() > 0 and day_element.is_visible():
                        day_element.click()
                        log(f"   ✅ Clic en día {TARGET_DAY}")
                        page.wait_for_timeout(3000)
                except Exception as e:
                    log(f"   ⚠️ No se pudo hacer clic en día {TARGET_DAY}: {e}")
            else:
                log(f"   🎯 Buscamos HOY ({TARGET_DAY}) - Ya debería estar seleccionado")
            
            # PASO 5: BUSCAR LA ACTIVIDAD
            log(f"5. Buscando actividad: {ACTIVITY_NAME}...")
            
            # Obtener frame de planificación
            frame = ActivityFinder.get_planning_frame(page)
            
            # Hacer scroll para asegurar que todo está visible
            page.mouse.wheel(0, 500)
            page.wait_for_timeout(1000)
            
            # Buscar la actividad
            plazas = ActivityFinder.find_activity(frame)
            
            # PASO 6: RETORNAR RESULTADO
            if plazas != -1:
                log(f"🎉 ¡Resultado encontrado! Plazas: {plazas}")
                return plazas
            else:
                log("❌ No se encontró la actividad")
                
                # DEBUG EXTRA: Mostrar qué hay en la página
                all_text = page.text_content()
                log(f"📄 Contenido actual de la página (primeros 500 chars):")
                log(f"{all_text[:500]}...")
                
                return -1

        except Exception as e:
            log(f"💥 Error crítico: {e}")
            return -1
        
        finally:
            browser.close()
            log("👋 Bot finalizado")
            

         

            # ---------------------------------------------------------
            # FIN DEL CÓDIGO NUEVO
            # ---------------------------------------------------------

    

# ===============================
# API FLASK PARA SERVICIO WEB
# ===============================
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/')
def index():
    return jsonify({
        "status": "online",
        "service": "Enjoy Bot Server",
        "endpoints": ["/buscar", "/monitor", "/health"],
        "usage": "GET /buscar?actividad=ZUMBA&hora=18:30&dia=15&mes=noviembre"
    })

@app.route('/debug_planning_html', methods=['GET'])
def debug_planning_html():
    """Returns the HTML of the planning page after login for debugging"""
    import traceback
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()

            # Use the existing session management
            if SessionManager.restore_session(page):
                page.goto(PLANNING_URL, wait_until="networkidle", timeout=30000)
                verificar(3000)
                if SessionManager.is_logged_in(page):
                    log("✅ Sesión restaurada")
                else:
                    log("❌ Sesión no válida, haciendo login...")
                    if not SessionManager.perform_login(page, context):
                        return jsonify({"error": "Login failed"})
            else:
                if not SessionManager.perform_login(page, context):
                    return jsonify({"error": "Login failed"})

            # Now we are on the planning page, get the HTML
            html = page.content()
            browser.close()

            return jsonify({
                "html": html,
                "html_length": len(html)
            })
    except Exception as e:
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500

@app.route('/debug_fecha_problema', methods=['GET'])
def debug_fecha_problema():
    """Debug ESPECÍFICO del problema de fecha inválida"""
    from playwright.sync_api import sync_playwright
    
    logs = []
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"]
            )
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            
            logs.append("1. Login...")
            page.goto("https://member.resamania.com/enjoy/planning", wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(5000)
            
            # Verificar estado inicial
            initial_text = page.text_content()
            logs.append(f"2. Texto inicial muestra:")
            
            # Buscar problemas específicos
            problemas = {
                "Fecha inválida": "Fecha inválida" in initial_text,
                "Ningún resultado": "Ningún resultado para este día" in initial_text,
                "junio 2022": "jun. de 2022" in initial_text or "junio 2022" in initial_text.lower(),
                "Actividades visibles": "INSCRIBIRSE" in initial_text or "PLAZA" in initial_text
            }
            
            for problema, encontrado in problemas.items():
                logs.append(f"   - {problema}: {'✅ SÍ' if encontrado else '❌ NO'}")
            
            # Intentar solución
            if any([problemas["Fecha inválida"], problemas["Ningún resultado"], problemas["junio 2022"]]):
                logs.append("3. ¡PROBLEMA DETECTADO! Aplicando solución...")
                
                # Buscar botón HOY
                hoy_selectors = ["button:has-text('HOY')", "button:has-text('Hoy')"]
                hoy_encontrado = False
                
                for selector in hoy_selectors:
                    if page.locator(selector).count() > 0:
                        logs.append(f"   ✅ Encontrado: {selector}")
                        page.click(selector)
                        logs.append(f"   ✅ Clic en {selector}")
                        hoy_encontrado = True
                        break
                
                if not hoy_encontrado:
                    logs.append("   ❌ No se encontró botón HOY")
                
                # Esperar y verificar resultado
                page.wait_for_timeout(3000)
                new_text = page.text_content()
                
                logs.append("4. Después del clic en HOY:")
                nuevos_problemas = {
                    "Fecha inválida": "Fecha inválida" in new_text,
                    "Actividades visibles": "INSCRIBIRSE" in new_text or "PLAZA" in new_text
                }
                
                for problema, encontrado in nuevos_problemas.items():
                    logs.append(f"   - {problema}: {'✅ SÍ' if encontrado else '❌ NO'}")
                
                if nuevos_problemas["Actividades visibles"]:
                    logs.append("5. ¡SOLUCIÓN EXITOSA! Ahora hay actividades visibles")
                else:
                    logs.append("5. ❌ La solución no funcionó")
            
            else:
                logs.append("3. ✅ No se detectaron problemas de fecha")
            
            # Mostrar líneas relevantes
            lines = [l.strip() for l in initial_text.split('\n') if l.strip()]
            relevant_lines = []
            for line in lines:
                if any(keyword in line for keyword in ['HOY', 'Hoy', 'FECHA', 'INSCRIBIRSE', 'PLAZA', 'jun.', '2022']):
                    relevant_lines.append(line[:80])
            
            if relevant_lines:
                logs.append("6. Líneas relevantes encontradas:")
                for i, line in enumerate(relevant_lines[:5]):
                    logs.append(f"   {i+1}. {line}")
            
            browser.close()
            
            return jsonify({
                "success": True,
                "logs": logs,
                "problema_detectado": any([problemas["Fecha inválida"], problemas["Ningún resultado"], problemas["junio 2022"]])
            })
            
    except Exception as e:
        logs.append(f"💥 ERROR: {str(e)}")
        return jsonify({
            "success": False,
            "error": str(e),
            "logs": logs
        }), 500



@app.route('/buscar', methods=['GET', 'POST'])
def buscar_actividad():
    """Endpoint para búsqueda desde AppInventor"""
    try:
        if request.method == 'GET':
            actividad = request.args.get('actividad', '')
            hora = request.args.get('hora', '')
            dia = request.args.get('dia', '')
            mes = request.args.get('mes', '')
        else:
            data = request.get_json() or request.form
            actividad = data.get('actividad', '')
            hora = data.get('hora', '')
            dia = data.get('dia', '')
            mes = data.get('mes', '')

        if not all([actividad, hora, dia, mes]):
            return jsonify({
                "estado": "error",
                "mensaje": "Faltan parámetros. Usa: actividad, hora, dia, mes"
            })

        global ACTIVITY_NAME, ACTIVITY_HOUR, TARGET_DAY, TARGET_MONTH
        ACTIVITY_NAME = actividad.upper()
        ACTIVITY_HOUR = hora
        TARGET_DAY = dia
        TARGET_MONTH = mes.lower()

        log(f"🔍 Búsqueda desde API: {ACTIVITY_NAME} {ACTIVITY_HOUR} {TARGET_DAY}/{TARGET_MONTH}")

        plazas = run_bot(headless=True)

        if plazas > 0:
            return jsonify({
                "estado": "éxito",
                "plazas": plazas,
                "mensaje": f"✅ {plazas} plazas disponibles para {ACTIVITY_NAME} a las {ACTIVITY_HOUR}"
            })
        elif plazas == 0:
            return jsonify({
                "estado": "completo",
                "plazas": 0,
                "mensaje": "⚠️ Actividad COMPLETA (0 plazas)"
            })
        elif plazas == -2:
            return jsonify({
                "estado": "inscrito",
                "mensaje": "🥳 Ya estás inscrito en esta actividad"
            })
        else:
            return jsonify({
                "estado": "error",
                "mensaje": "✗ No se encontró la actividad. Verifica la fecha/hora."
            })

    except Exception as e:
        log(f"💥 Error en endpoint /buscar: {e}")
        return jsonify({
            "estado": "error",
            "mensaje": f"Error interno: {str(e)}"
        })

@app.route('/monitor', methods=['POST'])
def iniciar_monitor():
    """Inicia monitorización continua"""
    try:
        data = request.get_json() or request.form
        actividad = data.get('actividad', '')
        hora = data.get('hora', '')
        dia = data.get('dia', '')
        mes = data.get('mes', '')

        if not all([actividad, hora, dia, mes]):
            return jsonify({
                "estado": "error",
                "mensaje": "Faltan parámetros para monitorización"
            })

        import threading
        thread = threading.Thread(
            target=run_monitor,
            args=(actividad.upper(), hora, dia, mes.lower())
        )
        thread.daemon = True
        thread.start()

        return jsonify({
            "estado": "éxito",
            "mensaje": f"Monitorización iniciada para {actividad} {hora}"
        })

    except Exception as e:
        return jsonify({
            "estado": "error",
            "mensaje": f"Error al iniciar monitor: {str(e)}"
        })

@app.route('/health')
def health_check():
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "gui_available": GUI_AVAILABLE
    })
@app.route('/debug_html', methods=['GET'])
@app.route('/debug_html', methods=['GET'])
def debug_html():
    """Versión robusta que devuelve HTML completo y no falla"""
    from playwright.sync_api import sync_playwright
    import time
    
    # 1. Inicializar variables POR DEFECTO para evitar NameError
    actividad = request.args.get('actividad', '')
    hora = request.args.get('hora', '')
    dia = request.args.get('dia', '')
    mes = request.args.get('mes', '')
    
    logs = []
    html_content = "No se pudo obtener contenido (Fallo antes de renderizar)"
    contains_activity = False
    
    try:
        with sync_playwright() as p:
            # Lanzamos navegador con argumentos Docker
            browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            
            # A. Login
            logs.append("1. Iniciando navegación...")
            if SessionManager.restore_session(page):
                logs.append("   Sesión restaurada.")
            else:
                logs.append("   Haciendo login completo...")
                SessionManager.perform_login(page, context)
            
            # B. Ir a Planning
            logs.append("2. Yendo a planning...")
            page.goto(PLANNING_URL, wait_until="networkidle", timeout=30000)
            
            # C. Intentar Clic en el Día (Lógica Simplificada para Debug)
            logs.append(f"3. Intentando clic en día {dia}...")
            try:
                # Selector agresivo por texto
                selector_dia = f"//button[normalize-space(.)='{dia}'] | //div[normalize-space(.)='{dia}']"
                page.wait_for_selector(selector_dia, timeout=5000)
                element = page.locator(selector_dia).first
                # Forzar clic JS
                page.evaluate('(el) => el.click()', element.element_handle())
                logs.append("   ✅ Clic JS realizado.")
                page.wait_for_timeout(3000) # Espera para carga
            except Exception as e:
                logs.append(f"   ⚠️ No se pudo hacer clic en el día: {e}")

            # D. Obtener HTML
            html_content = page.content()
            contains_activity = actividad.upper() in html_content.upper()
            logs.append(f"4. HTML capturado ({len(html_content)} chars)")
            
            browser.close()
            
    except Exception as e:
        logs.append(f"💥 ERROR CRÍTICO: {str(e)}")
    
    # 2. Retorno seguro (nunca fallará porque las variables ya existen)
    return jsonify({
        "logs": logs,
        "html_length": len(html_content),
        "contains_activity": contains_activity,
        "html": html_content  # <--- AQUÍ ESTÁ EL CÓDIGO FUENTE QUE NECESITAMOS
    })
@app.route('/test_ultra_simple', methods=['GET'])
def test_ultra_simple():
    """Bot ultra simplificado - solo busca texto"""
    import traceback
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            # Use chromium, and make sure to run in headless mode
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            # Set the navigation timeout to 30 seconds to match Render's timeout
            page.goto("https://member.resamania.com/enjoy/planning", timeout=30000)
            
            # Wait for 3 seconds instead of 5
            verificar(3000)
            all_text = page.text_content()
            
            # Close the browser
            browser.close()
            
            # Search for strings
            contains_aquagym = "AQUAGYM" in all_text.upper()
            contains_5 = "5" in all_text
            contains_diciembre = "diciembre" in all_text.lower()
            
            return jsonify({
                "aquagym_found": contains_aquagym,
                "day_5_found": contains_5,
                "december_found": contains_diciembre,
                "text_sample": all_text[:500] + "..." if len(all_text) > 500 else all_text
            })
    except Exception as e:
        # Return the error message and traceback for debugging
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@app.route('/debug_login', methods=['GET'])
def debug_login():
    """Solo verifica si el login funciona"""
    from playwright.sync_api import sync_playwright
    import time
    
    logs = []
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            logs.append("1. Navegando a enjoy...")
            page.goto("https://member.resamania.com/enjoy", wait_until="domcontentloaded", timeout=15000)
            time.sleep(2)
            
            current_url = page.url
            logs.append(f"2. URL actual: {current_url}")
            
            # Verificar estado
            if "login" in current_url:
                logs.append("❌ Estamos en página de login - NO logueado")
                page.screenshot(path="debug_not_logged.png")
            elif "planning" in current_url or "member" in current_url:
                logs.append("✅ ¡Parece que YA ESTÁ LOGEADO!")
                page.screenshot(path="debug_logged.png")
            else:
                logs.append(f"⚠️ Estado desconocido - URL: {current_url}")
            
            # Tomar contenido
            html = page.content()[:500]
            logs.append(f"3. Primeros 500 chars del HTML: {html}")
            
            browser.close()
            
            return jsonify({
                "success": "planning" in current_url or "member" in current_url,
                "url": current_url,
                "logs": logs
            })
            
    except Exception as e:
        return jsonify({"error": str(e), "logs": logs})

@app.route('/debug_screenshot', methods=['GET'])
def debug_screenshot():
    """Describe lo que vería en un screenshot"""
    from playwright.sync_api import sync_playwright
    import base64
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Ir directo a planning (asumiendo cookies funcionan)
            page.goto("https://member.resamania.com/enjoy/planning", timeout=30000)
            verificar(5000)
            
            # Verificar estado
            current_url = page.url
            page_title = page.title()
            
            # Obtener texto visible
            visible_text = page.text_content()
            
            # Buscar día 5
            try:
                page.click("text=5", timeout=5000)
                page.wait_for_timeout(3000)
                clicked_day = True
            except:
                clicked_day = False
            
            # Analizar contenido
            lines = visible_text.split('\n')
            relevant_lines = []
            for line in lines:
                line_clean = line.strip()
                if line_clean and len(line_clean) > 10:
                    if 'AQUAGYM' in line_clean.upper() or 'ZUMBA' in line_clean.upper() or 'ACTIVIDAD' in line_clean.upper():
                        relevant_lines.append(line_clean)
            
            browser.close()
            
            return jsonify({
                "url": current_url,
                "title": page_title,
                "day_clicked": clicked_day,
                "relevant_lines": relevant_lines[:10],  # Solo primeras 10
                "total_lines": len(lines),
                "status": "success"
            })
            
    except Exception as e:
        return jsonify({"error": str(e), "status": "failed"})
@app.route('/test_fix', methods=['GET'])
def test_fix():
    """Prueba la corrección del problema del día"""
    from playwright.sync_api import sync_playwright
    from datetime import datetime
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)  # Headless=False para ver
            page = browser.new_page()
            
            # Login
            page.goto("https://member.resamania.com/enjoy/planning", timeout=30000)
            page.wait_for_timeout(3000)
            
            logs = []
            
            # Ver día actual
            today = datetime.now().day
            logs.append(f"Día actual del sistema: {today}")
            
            # Ver qué día muestra la página
            all_text = page.text_content()
            logs.append(f"Texto página (100 chars): {all_text[:100]}...")
            
            # Buscar "HOY" o números de día
            import re
            day_numbers = re.findall(r'\b(\d{1,2})\b', all_text)
            logs.append(f"Números de día encontrados: {list(set(day_numbers))[:10]}")
            
            # Ver si hay actividades visibles inicialmente
            actividades_visibles = "INSCRIBIRSE" in all_text or "PLAZA" in all_text
            logs.append(f"Actividades visibles inicialmente: {'✅ SÍ' if actividades_visibles else '❌ NO'}")
            
            # NO hacer clic en el día actual (simular lo que pasaba)
            logs.append("\n--- SIN hacer clic en día (dejar como está) ---")
            logs.append("Actividades deberían permanecer visibles")
            
            page.wait_for_timeout(5000)
            
            # Mostrar actividades actuales
            lines = all_text.split('\n')
            activity_lines = [l[:80] for l in lines if 'INSCRIBIRSE' in l or 'PLAZA' in l]
            logs.append(f"Actividades encontradas: {len(activity_lines)}")
            for i, line in enumerate(activity_lines[:3]):
                logs.append(f"  {i+1}. {line}")
            
            browser.close()
            
            return jsonify({
                "logs": logs,
                "conclusion": "Si actividades_visibles es TRUE, la corrección funciona"
            })
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===============================
# EJECUCIÓN PRINCIPAL
# ===============================
def main():
    if GUI_AVAILABLE:
        # Modo escritorio con interfaz gráfica
        print("🚀 Iniciando aplicación de escritorio...")
        app_gui = EnjoyForm()
        app_gui.run()
    else:
        # Modo servidor web (Render)
        print("🌐 Iniciando servidor web Flask...")
        print(f"🔧 GUI disponible: {GUI_AVAILABLE}")
        print(f"📡 Endpoints disponibles:")
        print(f"   • /buscar?actividad=ZUMBA&hora=18:30&dia=15&mes=noviembre")
        print(f"   • /health")
        print(f"   • /monitor (POST)")
        
        # Verificar credenciales básicas
        if not USERNAME or not PASSWORD:
            print("⚠️ ADVERTENCIA: Credenciales no configuradas. Usa variables de entorno:")
            print("   ENJOY_USERNAME, ENJOY_PASSWORD, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID")
        
        # Ejecutar Flask
        port = int(os.environ.get('PORT', 5000))
        app.run(host='0.0.0.0', port=port, debug=False)

# Solo ejecutar main si el script es ejecutado directamente, no importado.
if __name__ == "__main__":
    main()

































