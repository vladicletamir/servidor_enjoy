# Imagen oficial de Playwright con Python
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy
# Crear carpeta de trabajo
WORKDIR /app

# Copiar dependencias
COPY requirements.txt .

# Instalar dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del proyecto
COPY . .

# Exponer puerto (solo si usas API, si no puedes quitarlo)
EXPOSE 8000

# Comando de ejecución
CMD ["python", "servidor_enjoy.py"]

