import easyocr
import time
from config.settings import OCR_LANGUAGES, OCR_CONFIDENCE_THRESHOLD
from utils.logger import logger
# Profanity libraries
from better_profanity import profanity as better_profanity


class OCRAnalyzer:
    def __init__(self):
        logger.info("Inicializando OCR...")
        self.reader = easyocr.Reader(OCR_LANGUAGES)
        logger.info("OCR listo!")
    # Inicializar better-profanity para inglés
    better_profanity.load_censor_words()

    def analizar_texto_ocr(self, archivo_imagen):
        """Analiza el texto en una imagen usando OCR y detecta lenguaje ofensivo con varias librerías"""
        try:
            logger.info(f"[📖] Analizando texto en imagen: {archivo_imagen}")
            start_time = time.time()

            # Leer texto de la imagen
            results = self.reader.readtext(archivo_imagen)

            # Extraer solo el texto
            texto_detectado = ""
            for (bbox, text, confidence) in results:
                if confidence > OCR_CONFIDENCE_THRESHOLD:
                    texto_detectado += text + " "

            end_time = time.time()
            logger.info(f"[📖] OCR completado en {end_time - start_time:.2f} segundos")

            texto_lower = texto_detectado.lower()
            palabras_encontradas = []

            # Usar better-profanity (inglés)
            if better_profanity.contains_profanity(texto_lower):
                palabras_encontradas.append("better-profanity")

            if palabras_encontradas:
                logger.info(f"[⚠️] Lenguaje ofensivo detectado por: {palabras_encontradas}")
                return True, palabras_encontradas, texto_detectado

            return False, [], texto_detectado

        except Exception as e:
            logger.error(f"[❌] Error en OCR: {e}")
            return False, [], ""