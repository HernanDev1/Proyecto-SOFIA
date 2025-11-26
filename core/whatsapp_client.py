import time
import threading
from typing import Optional

import requests
import re

from config.settings import (
    WHATSAPP_TOKEN,
    WHATSAPP_PHONE_NUMBER_ID,
    WHATSAPP_API_VERSION,
    DELAY_ENTRE_ENVIOS,
)
from utils.logger import logger


class WhatsAppClient:
    """Cliente mínimo para la WhatsApp Cloud API (Meta).

    Provee métodos para enviar mensajes de texto y enviar imágenes mediante
    subida de medios. Lee la configuración desde `config.settings`.
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.ultimo_envio = 0
        self.envio_en_proceso = False

        self.token = WHATSAPP_TOKEN
        self.phone_number_id = WHATSAPP_PHONE_NUMBER_ID
        self.api_version = WHATSAPP_API_VERSION or "v17.0"

        if not self.phone_number_id:
            self.base_url = None
        else:
            self.base_url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}"

        if not self.token:
            logger.warning("[WHATSAPP] No se encontró WHATSAPP_TOKEN en la configuración; los envíos fallarán hasta configurar el token.")

    def puede_enviar(self) -> bool:
        with self.lock:
            ahora = time.time()
            if self.envio_en_proceso:
                logger.info("[WHATSAPP] Envío ya en proceso, esperando...")
                return False
            if ahora - self.ultimo_envio < DELAY_ENTRE_ENVIOS:
                restante = DELAY_ENTRE_ENVIOS - (ahora - self.ultimo_envio)
                logger.info(f"[WHATSAPP] Rate limit: esperar {restante:.1f}s")
                return False
            return True

    def _headers(self):
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        # JSON default header for message sends
        headers.setdefault("Content-Type", "application/json")
        return headers

    def _normalize_number(self, number: str) -> str:
        """Normaliza el número a dígitos solo (sin '+', espacios ni paréntesis).

        La API de WhatsApp Cloud espera el número en formato internacional sin el '+'.
        """
        if not number:
            return ""
        s = re.sub(r"\D", "", str(number))
        return s

    def send_text(self, to_number: str, message: str, timeout: int = 30) -> bool:
        """Enviar mensaje de texto simple al número en formato E.164 (ej: '54911...')."""
        if not self.base_url:
            logger.error("[WHATSAPP] phone_number_id no configurado; abortando envío de texto.")
            return False

        if not self.puede_enviar():
            return False

        url = f"{self.base_url}/messages"
        to_norm = self._normalize_number(to_number)
        if not to_norm:
            logger.error(f"[WHATSAPP] Número destino inválido: {to_number}")
            return False
        payload = {
            "messaging_product": "whatsapp",
            "to": to_norm,
            "type": "text",
            "text": {"body": message},
        }

        with self.lock:
            self.envio_en_proceso = True

        try:
            # retries for transient errors
            max_attempts = 2
            for intento in range(1, max_attempts + 1):
                resp = requests.post(url, json=payload, headers=self._headers(), timeout=timeout)
                if resp.status_code in (200, 201):
                    logger.info(f"[WHATSAPP] Mensaje enviado a {to_norm}")
                    with self.lock:
                        self.ultimo_envio = time.time()
                    return True
                # retry on server errors or rate limit
                if resp.status_code >= 500 or resp.status_code == 429:
                    wait = 2 ** intento
                    logger.warning(f"[WHATSAPP] intento {intento} fallo ({resp.status_code}), reintentando en {wait}s...")
                    time.sleep(wait)
                    continue
                logger.error(f"[WHATSAPP] Error al enviar texto ({resp.status_code}): {resp.text}")
                return False

        except Exception as e:
            logger.error(f"[WHATSAPP] Excepción en send_text: {e}")
            return False
        finally:
            with self.lock:
                self.envio_en_proceso = False

    def upload_media(self, file_path: str, timeout: int = 120) -> Optional[str]:
        """Sube un archivo como media y devuelve el media id si tiene éxito.

        Nota: la API espera multipart/form-data con el campo 'file'.
        """
        if not self.base_url:
            logger.error("[WHATSAPP] phone_number_id no configurado; abortando subida de media.")
            return None

        url = f"{self.base_url}/media"

        try:
            import os
            import mimetypes

            if not os.path.exists(file_path):
                logger.error(f"[WHATSAPP] upload_media: archivo no encontrado: {file_path}")
                return None

            size = os.path.getsize(file_path)
            if size == 0:
                logger.error(f"[WHATSAPP] upload_media: archivo vacío: {file_path}")
                return None

            content_type, _ = mimetypes.guess_type(file_path)
            if not content_type:
                # Fallback a octet-stream si no se puede adivinar
                content_type = "application/octet-stream"

            logger.info(f"[WHATSAPP] Subiendo media: {file_path} (size={size}, mimetype={content_type})")

            with open(file_path, "rb") as f:
                filename = os.path.basename(file_path)
                # Enviar tupla (filename, fileobj, content_type) para asegurar que el servidor reciba el MIME
                files = {"file": (filename, f, content_type)}
                data = {"messaging_product": "whatsapp"}
                # For multipart, remove Content-Type header so requests sets the boundary
                headers = self._headers().copy()
                headers.pop("Content-Type", None)
                resp = requests.post(url, files=files, data=data, headers=headers, timeout=timeout)

            if resp.status_code in (200, 201):
                j = resp.json()
                media_id = j.get("id")
                logger.info(f"[WHATSAPP] Media subido, id={media_id}")
                return media_id
            else:
                logger.error(f"[WHATSAPP] Error subiendo media ({resp.status_code}): {resp.text}")
                return None

        except Exception as e:
            logger.error(f"[WHATSAPP] Excepción upload_media: {e}")
            return None

    def send_image(self, to_number: str, file_path: str, caption: Optional[str] = None, timeout: int = 60) -> bool:
        """Sube la imagen y la envía al número destino (combinado)."""
        media_id = self.upload_media(file_path, timeout=timeout)
        if not media_id:
            return False

        if not self.puede_enviar():
            return False

        url = f"{self.base_url}/messages"
        to_norm = self._normalize_number(to_number)
        if not to_norm:
            logger.error(f"[WHATSAPP] Número destino inválido: {to_number}")
            return False
        payload = {
            "messaging_product": "whatsapp",
            "to": to_norm,
            "type": "image",
            "image": {"id": media_id},
        }
        if caption:
            payload["image"]["caption"] = caption

        with self.lock:
            self.envio_en_proceso = True

        try:
            max_attempts = 2
            for intento in range(1, max_attempts + 1):
                resp = requests.post(url, json=payload, headers=self._headers(), timeout=timeout)
                if resp.status_code in (200, 201):
                    logger.info(f"[WHATSAPP] Imagen enviada a {to_norm}")
                    with self.lock:
                        self.ultimo_envio = time.time()
                    return True
                if resp.status_code >= 500 or resp.status_code == 429:
                    wait = 2 ** intento
                    logger.warning(f"[WHATSAPP] intento {intento} fallo ({resp.status_code}), reintentando en {wait}s...")
                    time.sleep(wait)
                    continue
                logger.error(f"[WHATSAPP] Error al enviar imagen ({resp.status_code}): {resp.text}")
                return False

        except Exception as e:
            logger.error(f"[WHATSAPP] Excepción send_image: {e}")
            return False
        finally:
            with self.lock:
                self.envio_en_proceso = False
