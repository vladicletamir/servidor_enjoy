# Usa la imagen oficial de Playwright - YA TIENE TODO INSTALADO
FROM mcr.microsoft.com/playwright/python:v1.40.0-jammy

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p screenshots

EXPOSE 5000

# Ejecutar con python directamente (sin gunicorn)
CMD ["python", "deep_kivy.py"]
