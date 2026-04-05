
# VozTexto

Aplicación web para transcribir audios a texto usando FastAPI y faster-whisper.

---

## Características

- Subida de archivos de audio desde navegador
- Transcripción automática a texto
- Historial de transcripciones en SQLite
- Descarga de texto y audio desde el historial
- Persistencia local en carpeta `data/`
- Despliegue con Docker

---

## Estructura del proyecto
```bash
voz_a_texto/
├── app.py
├── data/
│ ├── db/
│ ├── history_audio/
│ ├── history_text/
│ ├── outputs/
│ └── uploads/
├── docker-compose.yml
├── dockerfile
├── requirements.txt
└── templates/
```
￼

---

## Requisitos

### Opción recomendada
- Docker
- Docker Compose

### Opción alternativa
- Python 3.10+
- pip

---

## Instalación con Docker

### 1. Clonar el repositorio

```bash
git clone https://github.com/superegi/VozTexto.git
cd VozTexto
```

### 2. Levantar la aplicación

```bash
docker compose up --build
```

### 3. Abrir en navegador
￼
http://localhost:8000


### Primera ejecución
La primera vez puede tardar más porque se descarga el modelo Whisper.

Esto es normal.

## Uso
### Abrir la página web

### Ingresar nombre de usuario

### Subir audio

### Obtener transcripción

### Formatos soportados

- wav
- mp3
- m4a 
- flac
- ogg

## Límites

Tamaño máximo: 5 MB

Máximo 10 transcripciones simultáneas

## Persistencia de datos

Todo se guarda en la carpeta data/:
- audios
- textos
- historial
- base de datos

Esta carpeta NO se sube a GitHub (solo su estructura).

## Comandos útiles

### Levantar

```bash
￼
docker compose up --build
```
### Detener

```bash
docker compose down
```
### Logs

```bash
docker compose logs -f
```

## Instalación sin Docker (opcional)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload
```

Luego abrir:

http://localhost:8000

Problemas comunes
Error: fastapi no encontrado
Significa que no instalaste dependencias o no usas entorno virtual.

Solución:

usar Docker o instalar requirements

La página no carga
Probablemente está descargando el modelo Whisper.

Revisar:
```bash
docker compose logs -f
```

Problemas de permisos
```bash
sudo chown -R $USER:$USER data
```