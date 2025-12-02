# 1. USAR LA IMAGEN BASE OFICIAL DE PLAYWRIGHT
FROM mcr.microsoft.com/playwright/python:latest

# Establece el directorio de trabajo
WORKDIR /app

# 2. Copia el archivo de requerimientos e instala SOLO las dependencias de Python
# Playwright ya está instalado en la imagen base.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Copia el resto de los archivos del proyecto (incluyendo tus .py)
COPY . .

# 4. Comando para iniciar la aplicación (Asumimos gunicorn)
CMD gunicorn servidor_enjoy:app --workers 4 --bind 0.0.0.0:$PORT
