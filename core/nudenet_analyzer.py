import sys
import os
if __name__ == "__main__":
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from utils.logger import logger

try:
    from nudenet import NudeClassifier
    _NUDENET_OK = True
except Exception as e:
    logger.warning(f"[NudeNet] No se pudo importar NudeNet o su modelo: {e}. El análisis NSFW estará desactivado.")
    _NUDENET_OK = False

class NudeNetAnalyzer:
    def __init__(self):
        if _NUDENET_OK:
            try:
                logger.info("Inicializando NudeNet...")
                self.classifier = NudeClassifier()
                logger.info("NudeNet listo!")
                self.enabled = True
            except Exception as e:
                logger.warning(f"[NudeNet] Error al inicializar NudeNet: {e}. El análisis NSFW estará desactivado.")
                self.enabled = False
        else:
            self.enabled = False

    def analizar_imagen(self, archivo):
        """Analiza una imagen y retorna True si es NSFW. Si NudeNet no está disponible, retorna False y loguea advertencia."""
        if not getattr(self, 'enabled', False):
            logger.warning("[NudeNet] Análisis NSFW desactivado. No se analizará la imagen.")
            return False
        try:
            resultado = self.classifier.classify(archivo)
            if archivo in resultado:
                unsafe_score = resultado[archivo].get('unsafe', 0)
                logger.info(f"[🔞] NudeNet unsafe score: {unsafe_score}")
                return unsafe_score > 0.5  # Umbral configurable
            return False
        except Exception as e:
            logger.error(f"[❌] Error en NudeNet: {e}")
            return False
