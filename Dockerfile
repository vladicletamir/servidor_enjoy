# Usa una imagen base de Python que tenga permisos de root para apt
FROM python:3.11-slim

# Establece el directorio de trabajo
WORKDIR /app

# 1. Copia el archivo de requerimientos e instala las dependencias de Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2. INSTALA DEPENDENCIAS DE LINUX REQUERIDAS POR PLAYWRIGHT (USANDO EL COMANDO OFICIAL)
RUN apt-get update && \
    playwright install-deps chromium && \
    rm -rf /var/lib/apt/lists/*

# 3. DESCARGA E INSTALA EL BINARIO DE CHROMIUM
RUN playwright install chromium

# 4. Copia el resto de los archivos del proyecto (incluyendo tus .py)
COPY . .

# Comando para iniciar la aplicación (usa gunicorn si lo tienes en requirements.txt)
# Si no usas gunicorn, cámbialo a CMD ["python", "servidor_enjoy.py"]
CMD gunicorn servidor_enjoy:app --workers 4 --bind 0.0.0.0:$PORT
