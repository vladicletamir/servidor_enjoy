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
        selectors = [
            "button:has-text('Iniciar sesión')",
            "a:has-text('Iniciar sesión')",
            "button:has-text('Acceder')",
            "button:has-text('Entrar')"
        ]
        
        robust_selectors = [
            "[role='button']:has-text('sesión' i), [role='button']:has-text('Acceder' i)",
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
# GESTIÓN DE FECHAS
# ===============================
class DateNavigator:
    @staticmethod
    def ensure_date_selected(page, max_retries=3):
        """Garantiza que la fecha objetivo esté seleccionada"""
        log(f"🎯 DEBUG Fecha objetivo: {TARGET_DAY} de {TARGET_MONTH}")
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
    def _click_day_directly(page, target_day):
        log(f"   * Intentando FORZAR el clic en el día '{target_day}' con JS.")
        
        # Selector robusto (el mismo que ya usaste)
        DAY_SELECTOR = f"//button[normalize-space(.)='{target_day}'] | //div[normalize-space(.)='{target_day}']"
        
        try:
            # 1. Esperar a que el elemento esté en el DOM (visible, habilitado)
            element = page.wait_for_selector(DAY_SELECTOR, timeout=10000, state='visible')
            
            # 2. INYECTAR JAVASCRIPT para hacer clic (más robusto que .click())
            page.evaluate('(element) => element.click()', element)
            
            log(f"   ✅ Día '{target_day}' clicado correctamente mediante JS.")
            
            # 3. Espera crucial: esperar a que la red cargue los nuevos eventos del día
            page.wait_for_load_state("networkidle", timeout=15000) 
            
            log(f"   ✅ Red inactiva tras el clic. Contenido cargado.")
            return True
            
        except PlaywrightTimeoutError:
            log(f"   ❌ El elemento del día '{target_day}' no fue encontrado a tiempo.")
            return False
        except Exception as e:
            log(f"   💥 Error inesperado al forzar el clic: {e}")
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
        """Busca la actividad - VERSIÓN MEJORADA"""
        global ACTIVITY_NAME, ACTIVITY_HOUR
        
        log(f"🎯 BÚSQUEDA MEJORADA: '{ACTIVITY_NAME}' a las '{ACTIVITY_HOUR}'")
        
        # Obtener todo el texto de la página para debug
        all_text = frame.text_content()
        log(f"📄 Texto total disponible ({len(all_text)} chars)")
        log(f"📄 Muestra: '{all_text[:200]}...'")
        
        # Buscar todas las tarjetas/containers de actividades
        selectors = [
            "div", "article", "li", "section", 
            "[class*='activity']", "[class*='card']",
            "[class*='event']", "[class*='class']"
        ]
        
        for selector in selectors:
            try:
                elements = frame.locator(selector).all()
                log(f"🔍 Selector '{selector}': {len(elements)} elementos")
                
                for i, element in enumerate(elements[:10]):  # Limitar a 10 para debug
                    try:
                        text = element.text_content()
                        clean_text = " ".join(text.split()).upper()
                        
                        # Verificar si contiene actividad Y hora
                        activity_match = ACTIVITY_NAME.upper() in clean_text
                        hour_match = ACTIVITY_HOUR in clean_text or ACTIVITY_HOUR.lstrip('0') in clean_text
                        
                        if activity_match and hour_match:
                            log(f"✅ ¡COINCIDENCIA ENCONTRADA! Elemento {i} con selector '{selector}'")
                            log(f"📄 Contenido: '{clean_text[:150]}...'")
                            
                            plazas = ActivityFinder._extract_spots(element)
                            if plazas != -1:
                                return plazas
                                
                    except Exception as e:
                        continue
                        
            except Exception as e:
                continue
        
        log("❌ No se encontró ninguna coincidencia con los selectores básicos")
        
        # Último intento: buscar por texto directo
        log("🔄 Intentando búsqueda por texto directo...")
        try:
            # Buscar elemento que contenga tanto la actividad como la hora
            search_text = f"{ACTIVITY_NAME}.*{ACTIVITY_HOUR}"
            elements = frame.locator(f"text=/{search_text}/i").all()
            
            for element in elements:
                log(f"📌 Elemento encontrado por texto: '{element.text_content()[:100]}...'")
                plazas = ActivityFinder._extract_spots(element)
                if plazas != -1:
                    return plazas
        except:
            pass
            
        return -1
    def _extract_spots(element):
        """Extrae plazas, maneja COMPLETO, INSCRITO"""
        text = element.text_content()
        clean_text = " ".join(text.split()) 
        
        log(f"   🔢 DEBUG Analizando plazas en texto: '{clean_text[:100]}...'")
        
        # 1. Buscar número seguido de "plazas" (cualquier cosa después)
        import re
        
        # Patrones más flexibles
        patterns = [
            r'(\d+)\s*plazas?\s*vacantes?',
            r'(\d+)\s*plazas?\s*disponibles?',
            r'(\d+)\s*plazas?\s*libres?',
            r'quedan\s*(\d+)\s*plazas?',
            r'disponibles\s*(\d+)\s*plazas?',
            r'(\d+)\s*plazas?\s*restantes?',
            r'(\d+)\s*plazas?',  # Último recurso
        ]
        
        for pattern in patterns:
            match = re.search(pattern, clean_text, re.IGNORECASE)
            if match:
                spots = int(match.group(1))
                log(f"   🎉 DEBUG: Patrón '{pattern}' -> {spots} plazas")
                return spots
        
        # 2. Si no encuentra plazas, buscar botón "INSCRIBIRSE"
        try:
            if element.locator("button:has-text('INSCRIBIRSE'), button:has-text('Inscribirse'), button:has-text('Reservar')").count() > 0:
                log("   ✅ DEBUG: Botón 'INSCRIBIRSE' encontrado -> Hay plazas")
                return 25  # O un número positivo cualquiera
        except:
            pass
        
        log("   ❌ DEBUG: No se detectó número de plazas ni botón de inscripción")
        return -1

# ===============================
# FUNCIÓN PRINCIPAL DEL BOT
# ===============================

def run_bot(headless=False):
    """Ejecuta el bot y retorna número de plazas"""
    log("🚀 Iniciando bot...")
    log(f"🎯 Objetivo: {ACTIVITY_NAME} {ACTIVITY_HOUR} ({TARGET_DAY} {TARGET_MONTH})")
    
    # DEBUG: Verificar credenciales (parcialmente)
    log(f"🔑 Usuario configurado: {'SÍ' if USERNAME else 'NO'}")
    log(f"🔑 Contraseña configurada: {'SÍ' if PASSWORD else 'NO'}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
        headless=headless,
        # ✅ CORRECCIÓN: Los argumentos deben ir aquí
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
            
            # ✅ CORRECCIÓN CRÍTICA: Esperar a que un elemento de contenido real aparezca
            try:
                page.wait_for_selector("[class*='PlanningGrid-root'], [class*='MuiGrid-container'], [class*='MuiPaper-root'], [class*='planning']", 
                                       timeout=20000) # Subir a 20s por seguridad
                log("   ✅ Contenido de planificación detectado.")
            except PlaywrightTimeoutError:
                log("   ⚠️ Falla: El contenido de planificación no apareció tras 20s. Continuamos...")
            
            page.wait_for_timeout(2000) # Espera de seguridad extra
            
            current_url = page.url
            log(f"   📍 URL actual: {current_url}")
            
            if "planning" not in current_url:
                log(f"   ⚠️ No estamos en planning, estamos en: {current_url}")
            
           # ... después de la lógica de espera activa del PASO 2:
            
           # ---------------------------------------------------------
            # CÓDIGO NUEVO A INSERTAR EN run_bot (Justo después de la espera)
            # ---------------------------------------------------------
            
            # PASO 3: SELECCIONAR LA FECHA CORRECTA
            log(f"3. Seleccionando fecha objetivo: {TARGET_DAY} de {TARGET_MONTH}...")
            
            # Detectamos el frame principal (necesario en Resamania)
            frame = ActivityFinder.get_planning_frame(page)
            
            # Ejecutamos la lógica que busca el día '9' y le hace clic
            DateNavigator.ensure_date_selected(frame)
            
            # Pequeña espera para que la tabla se actualice tras el clic
            page.wait_for_timeout(2000)

            # PASO 4: BUSCAR LA ACTIVIDAD
            log(f"4. Buscando actividad: {ACTIVITY_NAME}...")
            plazas = ActivityFinder.find_activity(frame)
            
            # PASO 5: RETORNAR RESULTADO
            if plazas != -1:
                log(f"🎉 ¡Resultado encontrado! Plazas: {plazas}")
                return plazas
            else:
                log("❌ No se encontró la actividad tras navegar.")
                # Si falla, devolvemos -1
                return -1
            

         

            # ---------------------------------------------------------
            # FIN DEL CÓDIGO NUEVO
            # ---------------------------------------------------------

        except Exception as e:
            log(f"💥 Error crítico: {e}")
            screenshot(page, "error_critico")
            return -1
        
        finally:
            browser.close()
            log("👋 Bot finalizado")


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
def debug_html():
    """Devuelve el HTML cruto que ve el bot (sin ejecutar toda la lógica)"""
    from playwright.sync_api import sync_playwright
    import time
    
    # Configurar parámetros
    actividad = request.args.get('actividad', 'ZUMBA')
    hora = request.args.get('hora', '10:00')
    dia = request.args.get('dia', '6')
    mes = request.args.get('mes', 'diciembre')
    
    logs = []
    html_content = ""
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1280, "height": 900})
            page = context.new_page()
            
            # 1. Login rápido
            logs.append("🔐 1. Intentando login...")
            page.goto("https://member.resamania.com/enjoy", wait_until="networkidle", timeout=30000)
            time.sleep(2)
            
            # Verificar si ya está logueado
            if "login" in page.url:
                logs.append("❌ Parece que no está logueado")
            else:
                logs.append("✅ Ya estaba logueado o login automático funcionó")
            
            # 2. Ir a planning
            logs.append("📅 2. Navegando a planning y esperando contenido...")
            page.goto("https://member.resamania.com/enjoy/planning", wait_until="networkidle", timeout=30000)
            
            # Espera ACTIVA para renderizado
            try:
                page.wait_for_selector("[class*='PlanningGrid-root'], [class*='MuiGrid-container'], [class*='MuiPaper-root'], [class*='planning']", 
                                       timeout=20000)
                logs.append("✅ Contenido de planificación detectado después de espera activa.")
            except PlaywrightTimeoutError:
                logs.append("⚠️ Timeout en espera activa (20s). El contenido sigue siendo de carga.")
            
            time.sleep(2)
            
            # 3. Obtener HTML actual
            html_content = page.content()
            logs.append(f"📄 3. HTML obtenido: {len(html_content)} caracteres")
            
            # 4. Buscar evidencias
            if actividad.upper() in html_content.upper():
                logs.append(f"✅ ACTIVIDAD '{actividad}' ENCONTRADA en HTML")
            else:
                logs.append(f"❌ ACTIVIDAD '{actividad}' NO encontrada en HTML")
            
            if hora in html_content:
                logs.append(f"✅ HORA '{hora}' ENCONTRADA en HTML")
            else:
                logs.append(f"❌ HORA '{hora}' NO encontrada en HTML")
            
            if mes.lower() in html_content.lower():
                logs.append(f"✅ MES '{mes}' ENCONTRADO en HTML")
            else:
                logs.append(f"❌ MES '{mes}' NO encontrado en HTML")
            
            if dia in html_content:
                logs.append(f"✅ DÍA '{dia}' ENCONTRADO en HTML")
            else:
                logs.append(f"❌ DÍA '{dia}' NO encontrado en HTML")
            
            browser.close()
            
    except Exception as e:
        logs.append(f"💥 ERROR: {str(e)}")
    
    # Devolver HTML y logs
    return jsonify({
        "logs": logs,
        "html_length": len(html_content),
        "contains_activity": actividad.upper() in html_content.upper(),
        "contains_hour": hora in html_content,
        "html_preview": html_content[:2000] + "..." if len(html_content) > 2000 else html_content
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























