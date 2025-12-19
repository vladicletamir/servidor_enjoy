# Imagen oficial de Playwright con Python
FROM mcr.microsoft.com/playwright/python:v1.44.0-jammy

# Crear carpeta de trabajo
WORKDIR /app

# Copiar dependencias
COPY requirements.txt .

# Instalar dependencias
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el resto del proyecto
COPY . .

# Exponer puerto (si usas interfaz web)
EXPOSE 8000

# Comando de ejecución
CMD ["python", "main.py"]


CMD ["python", "servidor_enjoy.py"]

