from utils.logger import logger

try:
    from nudenet import NudeDetector
    _NUDENET3_OK = True
except Exception as e:
    logger.warning(f"[NudeNet3] No se pudo importar NudeNet3: {e}. El análisis NSFW estará desactivado.")
    _NUDENET3_OK = False

class NudeNetAnalyzer:
    def __init__(self):
        if _NUDENET3_OK:
            try:
                logger.info("Inicializando NudeNet3...")
                self.detector = NudeDetector()
                logger.info("NudeNet3 listo!")
                self.enabled = True
            except Exception as e:
                logger.warning(f"[NudeNet3] Error al inicializar NudeNet3: {e}. El análisis NSFW estará desactivado.")
                self.enabled = False
        else:
            self.enabled = False

    def analizar_imagen(self, archivo):
        """Analiza una imagen y retorna True si es NSFW. Si NudeNet3 no está disponible, retorna False y loguea advertencia."""
        if not getattr(self, 'enabled', False):
            logger.warning("[NudeNet3] Análisis NSFW desactivado. No se analizará la imagen.")
            return False
        try:
            # NudeNet3 retorna una lista de detecciones, cada una con una 'label' y 'score'
            resultados = self.detector.detect(archivo)
            print(f"[DEBUG] Resultado completo NudeNet3 para {archivo}: {resultados}")
            nsfw_labels = {
                'BUTTOCKS_EXPOSED',
                'FEMALE_BREAST_EXPOSED',
                'FEMALE_GENITALIA_EXPOSED',
                'MALE_GENITALIA_EXPOSED',
                'ANUS_EXPOSED',
                'SEX_ACT',
                'SEX_TOY',
                'MISC_GENITALIA_EXPOSED',
                'MISC_BREAST_EXPOSED',
                'MISC_BUTTOCKS_EXPOSED',
            }
            for r in resultados:
                label = r.get('label') or r.get('class')
                if label in nsfw_labels and r.get('score', 0) > 0.5:
                    logger.info(f"[🔞] NudeNet3 NSFW detectado: {r}")
                    return True
            return False
        except Exception as e:
            logger.error(f"[❌] Error en NudeNet3: {e}")
            return False
