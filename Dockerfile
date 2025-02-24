FROM python:3.10-slim

# 1. Instalar ffmpeg
RUN apt-get update && apt-get install -y ffmpeg

# 2. Crear directorio de trabajo
WORKDIR /app

# 3. Copiar requirements.txt e instalarlos
COPY requirements.txt /app
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copiar todo el resto de archivos
COPY . /app

# 5. Comando para ejecutar tu bot
CMD ["python", "djtoad_railway.0.1.py"]
