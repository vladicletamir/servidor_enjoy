from playwright.sync_api import sync_playwright
from datetime import datetime
from pathlib import Path
import json
import requests 
import time
import os
from flask import Flask, request, jsonify
import sys
import re

# ===============================
# CONFIGURACIÓN
# ===============================
LOGIN_URL = "https://member.resamania.com/enjoy"
PLANNING_URL = "https://member.resamania.com/enjoy/planning"
STATE_FILE = Path("enjoy_state.json")

# Variables de entorno en Render
USERNAME = os.environ.get("ENJOY_USERNAME", "anaurma@hotmail.com")
PASSWORD = os.environ.get("ENJOY_PASSWORD", "Kerkrade1126")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# ===============================
# UTILIDADES
# ===============================
def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def simple_login(page):
    """Login SIMPLIFICADO y rápido"""
    try:
        log("🔐 Intentando login rápido...")
        
        # Ir directamente a planning (a veces ya estás logueado)
        page.goto(PLANNING_URL, wait_until="domcontentloaded", timeout=10000)
        time.sleep(2)
        
        # Verificar si ya estamos logueados
        page_content = page.content()
        if "Cerrar sesión" in page_content or "Desconexión" in page_content:
            log("✅ Ya estás logueado")
            return True
        
        # Si no, ir a login
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=10000)
        time.sleep(2)
        
        # Estrategia 1: Buscar formulario de login directo
        try:
            # Intentar llenar email si el campo está visible
            page.fill("input[type='email']", USERNAME)
            time.sleep(1)
            
            # Buscar y hacer clic en "Continuar" o similar
            continue_buttons = page.locator("button:has-text('Continuar'), button:has-text('Continue'), button:has-text('Siguiente')")
            if continue_buttons.count() > 0:
                continue_buttons.first.click()
                time.sleep(2)
            
            # Llenar contraseña
            page.fill("input[type='password']", PASSWORD)
            time.sleep(1)
            
            # Buscar botón de login final
            login_buttons = page.locator("button:has-text('Conectarme'), button:has-text('Log in'), button:has-text('Entrar'), button:has-text('Acceder')")
            if login_buttons.count() > 0:
                login_buttons.first.click()
            
            time.sleep(3)
            
            # Verificar si login fue exitoso
            page_content = page.content()
            if "Cerrar sesión" in page_content or "Desconexión" in page_content:
                log("✅ Login exitoso (método directo)")
                return True
        except:
            pass
        
        # Estrategia 2: Buscar botón "Iniciar sesión" primero
        try:
            login_links = page.locator("a:has-text('Iniciar sesión'), button:has-text('Iniciar sesión')")
            if login_links.count() > 0:
                login_links.first.click()
                time.sleep(2)
                
                # Ahora intentar el formulario
                page.fill("input[type='email']", USERNAME)
                time.sleep(1)
                page.fill("input[type='password']", PASSWORD)
                time.sleep(1)
                
                submit_buttons = page.locator("button[type='submit'], button:has-text('Conectarme')")
                if submit_buttons.count() > 0:
                    submit_buttons.first.click()
                
                time.sleep(3)
                
                page_content = page.content()
                if "Cerrar sesión" in page_content or "Desconexión" in page_content:
                    log("✅ Login exitoso (método con botón)")
                    return True
        except:
            pass
        
        # Estrategia 3: JavaScript directo
        try:
            page.evaluate(f"""
                () => {{
                    // Buscar inputs de email
                    const emailInputs = document.querySelectorAll("input[type='email'], input[name='email']");
                    if (emailInputs.length > 0) {{
                        emailInputs[0].value = '{USERNAME}';
                    }}
                    
                    // Buscar inputs de password
                    const passInputs = document.querySelectorAll("input[type='password'], input[name='password']");
                    if (passInputs.length > 0) {{
                        passInputs[0].value = '{PASSWORD}';
                    }}
                    
                    // Buscar y hacer clic en botón de submit
                    const submitButtons = document.querySelectorAll("button[type='submit'], button:has-text('Conectarme'), button:has-text('Log in')");
                    if (submitButtons.length > 0) {{
                        submitButtons[0].click();
                    }}
                }}
            """)
            
            time.sleep(5)
            
            page_content = page.content()
            if "Cerrar sesión" in page_content or "Desconexión" in page_content:
                log("✅ Login exitoso (método JavaScript)")
                return True
                
        except Exception as e:
            log(f"⚠️ Error en JS: {e}")
        
        log("❌ No se pudo hacer login")
        return False
        
    except Exception as e:
        log(f"💥 Error en login: {e}")
        return False

def search_activity_simple(page, activity_name, activity_hour):
    """Búsqueda SIMPLE de actividad"""
    try:
        log(f"🔍 Buscando '{activity_name}' a las '{activity_hour}'")
        
        # Obtener todo el texto
        all_text = page.evaluate("() => document.body.textContent")
        
        # Convertir a mayúsculas para búsqueda insensible
        all_text_upper = all_text.upper()
        activity_upper = activity_name.upper()
        
        # Verificar si la actividad está en la página
        if activity_upper not in all_text_upper:
            log(f"❌ '{activity_name}' no encontrado")
            return -1
        
        # Buscar la hora (formato HH:MM o HH.MM)
        hour_pattern1 = activity_hour
        hour_pattern2 = activity_hour.replace(':', '.')
        
        # Buscar líneas que contengan actividad y hora
        lines = all_text.split('\n')
        for line in lines:
            line_upper = line.upper()
            if activity_upper in line_upper and (hour_pattern1 in line or hour_pattern2 in line):
                log(f"✅ Encontrada línea: {line[:80]}...")
                
                # Extraer número de plazas
                import re
                
                # Patrón: "3 plazas vacantes"
                match = re.search(r'(\d+)\s+plazas?\s+vacantes?', line_upper)
                if match:
                    plazas = int(match.group(1))
                    log(f"🎉 {plazas} plazas encontradas")
                    return plazas
                
                # Patrón: "COMPLETO"
                if "COMPLETO" in line_upper or "LLENO" in line_upper:
                    log("🔴 Actividad COMPLETA")
                    return 0
                
                # Patrón: "INSCRITO"
                if "INSCRITO" in line_upper or "RESERVADO" in line_upper:
                    log("✅ Ya estás inscrito")
                    return -2
        
        log("⚠️ Actividad encontrada pero sin información de plazas")
        return -1
        
    except Exception as e:
        log(f"💥 Error buscando actividad: {e}")
        return -1

def run_quick_bot(activity_name, activity_hour, target_day, target_month):
    """Bot RÁPIDO optimizado para Render"""
    log(f"🚀 Búsqueda rápida: {activity_name} {activity_hour}")
    
    with sync_playwright() as p:
        try:
            # Configuración mínima para Render
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--single-process"  # Menos consumo de memoria
                ]
            )
            
            # Contexto simple
            context = browser.new_context(
                viewport={"width": 1280, "height": 900}
            )
            
            page = context.new_page()
            
            # 1. Login rápido
            if not simple_login(page):
                return {"status": "error", "message": "Login fallido"}
            
            # 2. Ir a planning
            page.goto(PLANNING_URL, wait_until="domcontentloaded", timeout=15000)
            time.sleep(2)
            
            # 3. Intentar seleccionar día si no es hoy
            from datetime import datetime
            today = datetime.now().day
            
            if str(today) != target_day:
                log(f"📅 Intentando seleccionar día {target_day}")
                try:
                    # Buscar el día en la página
                    day_elements = page.locator(f"text='{target_day}'")
                    if day_elements.count() > 0:
                        day_elements.first.click()
                        time.sleep(2)
                except:
                    log("⚠️ No se pudo cambiar el día, continuando...")
            
            # 4. Esperar a que carguen actividades
            time.sleep(3)
            
            # 5. Buscar actividad
            plazas = search_activity_simple(page, activity_name, activity_hour)
            
            # 6. Interpretar resultados
            if plazas > 0:
                return {
                    "status": "success",
                    "plazas": plazas,
                    "message": f"{plazas} plazas disponibles para {activity_name} a las {activity_hour}"
                }
            elif plazas == 0:
                return {
                    "status": "complete",
                    "plazas": 0,
                    "message": f"Actividad {activity_name} COMPLETA"
                }
            elif plazas == -2:
                return {
                    "status": "inscrito",
                    "message": f"Ya estás inscrito en {activity_name}"
                }
            else:
                return {
                    "status": "not_found",
                    "message": f"No se encontró {activity_name} a las {activity_hour}"
                }
                
        except Exception as e:
            log(f"💥 Error en bot: {e}")
            return {"status": "error", "message": str(e)}
        
        finally:
            try:
                browser.close()
            except:
                pass

# ===============================
# API FLASK
# ===============================
app = Flask(__name__)

@app.route('/')
def index():
    return jsonify({
        "service": "Enjoy Bot API",
        "version": "2.0",
        "status": "running",
        "endpoint": "/buscar?actividad=ZUMBA&hora=20:00&dia=17&mes=diciembre",
        "note": "Usa el endpoint /buscar con los parámetros actividad, hora, dia, mes"
    })

@app.route('/buscar', methods=['GET'])
def buscar():
    """Endpoint principal - versión rápida"""
    try:
        # Obtener parámetros
        actividad = request.args.get('actividad', '').strip()
        hora = request.args.get('hora', '').strip()
        dia = request.args.get('dia', '').strip()
        mes = request.args.get('mes', '').strip().lower()
        
        # Validaciones básicas
        if not all([actividad, hora, dia, mes]):
            return jsonify({
                "status": "error",
                "message": "Faltan parámetros. Ejemplo: /buscar?actividad=ZUMBA&hora=20:00&dia=17&mes=diciembre"
            })
        
        # Validar formato de hora
        if not re.match(r'^\d{2}:\d{2}$', hora):
            return jsonify({
                "status": "error", 
                "message": "Formato de hora inválido. Usa HH:MM (ej: 20:00)"
            })
        
        log(f"🎯 Nueva búsqueda: {actividad} {hora} {dia}/{mes}")
        
        # Ejecutar bot
        result = run_quick_bot(actividad, hora, dia, mes)
        
        # Enviar notificación si hay plazas
        if result.get("status") == "success" and TELEGRAM_BOT_TOKEN:
            try:
                telegram_msg = f"✅ *PLAZAS ENCONTRADAS!*\n\nClase: *{actividad}*\nHora: {hora}\nDía: {dia} {mes}\nPlazas: {result['plazas']}"
                requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                    json={"chat_id": TELEGRAM_CHAT_ID, "text": telegram_msg, "parse_mode": "Markdown"},
                    timeout=5
                )
            except:
                pass
        
        return jsonify(result)
        
    except Exception as e:
        log(f"💥 Error en endpoint: {e}")
        return jsonify({
            "status": "error",
            "message": f"Error interno: {str(e)}"
        })

@app.route('/health', methods=['GET'])
def health():
    """Health check simple"""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    })

@app.route('/test', methods=['GET'])
def test():
    """Endpoint de prueba rápida"""
    return jsonify({
        "message": "Servicio funcionando",
        "time": datetime.now().strftime("%H:%M:%S"),
        "credentials_set": bool(USERNAME and PASSWORD)
    })

@app.route('/debug_login', methods=['GET'])
def debug_login():
    """Debug del login (sin búsqueda)"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        page = browser.new_context().new_page()
        
        try:
            page.goto(LOGIN_URL, timeout=15000)
            time.sleep(3)
            
            # Tomar screenshot (en base64 para debug)
            screenshot_data = page.screenshot()
            import base64
            screenshot_b64 = base64.b64encode(screenshot_data).decode()
            
            # Verificar elementos
            has_email = page.locator("input[type='email']").count() > 0
            has_password = page.locator("input[type='password']").count() > 0
            has_login_button = page.locator("button:has-text('Iniciar sesión')").count() > 0
            
            browser.close()
            
            return jsonify({
                "status": "success",
                "has_email_field": has_email,
                "has_password_field": has_password,
                "has_login_button": has_login_button,
                "screenshot": screenshot_b64[:100] + "..." if len(screenshot_b64) > 100 else screenshot_b64
            })
            
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)})

# ===============================
# EJECUCIÓN
# ===============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    
    print("=" * 60)
    print("🚀 ENJOY BOT API - Versión Optimizada para Render")
    print(f"🌐 Puerto: {port}")
    print(f"🔐 Usuario: {USERNAME[:3]}...{'✅' if USERNAME else '❌'}")
    print(f"🔑 Contraseña: {'✅ Configurada' if PASSWORD else '❌ No configurada'}")
    print("=" * 60)
    print("📡 Endpoints disponibles:")
    print(f"   • GET  /buscar?actividad=ZUMBA&hora=20:00&dia=17&mes=diciembre")
    print(f"   • GET  /health")
    print(f"   • GET  /test")
    print(f"   • GET  /debug_login")
    print("=" * 60)
    
    app.run(host="0.0.0.0", port=port, debug=False)
