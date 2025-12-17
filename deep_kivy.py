# ===============================
# EJECUCIÓN ADAPTATIVA (CORREGIDA)
# ===============================
if __name__ == "__main__":
    # 1. Buscamos la variable específica que Render inyecta en sus servidores
    # Si esta variable NO existe, asumimos que estamos en tu PC.
    EN_RENDER = os.getenv('RENDER') == 'true'

    if EN_RENDER:
        log("🌐 Entorno Cloud (Render) detectado.")
        log("📡 Iniciando servidor Flask para recibir comandos CURL...")
        # Render usa la variable PORT para decirnos en qué puerto escuchar
        puerto = int(os.environ.get("PORT", 5000))
        api.run(host='0.0.0.0', port=puerto)
    else:
        log("💻 Entorno Local detectado.")
        log("🎨 Abriendo interfaz gráfica (GUI)...")
        try:
            app = EnjoyForm()
            app.run()
        except Exception as e:
            log(f"❌ Error al abrir la GUI: {e}")
            log("🔄 Intentando arrancar Flask como plan de emergencia...")
            api.run(host='127.0.0.1', port=5000)
