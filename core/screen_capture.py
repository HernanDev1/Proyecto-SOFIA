import pyautogui
import datetime
import os
import threading
import time
from config.settings import CARPETA_CAPTURAS, CAPTURA_INTERVALO
from utils.logger import logger
from utils.file_manager import cleanup_file
from core.nudenet_analyzer3 import NudeNetAnalyzer

class ScreenCapture:
    def __init__(self, telegram_client, ocr_analyzer):
        # telegram_client parameter now expected to be a WhatsAppClient instance
        self.telegram_client = telegram_client
        self.ocr_analyzer = ocr_analyzer
        self.nudenet_analyzer = NudeNetAnalyzer()
        self.chat_id = None
        self.stop_event = threading.Event()  # Evento para detener el hilo de captura
    
    def set_chat_id(self, chat_id):
        """Establece el Chat ID para envíos"""
        self.chat_id = chat_id
    
    def capturar_y_enviar_rapido(self, palabra_detectada):
        """Captura y envío rápido para detección por teclado"""
        try:
            if hasattr(self.telegram_client, "puede_enviar") and not self.telegram_client.puede_enviar():
                logger.info("[⏭️] Saltando envío por rate limiting")
                return
            
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            archivo = os.path.join(CARPETA_CAPTURAS, f"teclado_{timestamp}.png")
            
            logger.info(f"[⚡] Captura rápida por teclado: {palabra_detectada}")
            
            # Capturar pantalla
            screenshot = pyautogui.screenshot()
            screenshot.save(archivo)
            
            # Verificar que se guardó correctamente
            if not os.path.exists(archivo) or os.path.getsize(archivo) == 0:
                logger.error(f"[❌] Error al guardar captura: {archivo}")
                return
            
            # NudeNet análisis y alerta
            def enviar_en_hilo():
                try:
                    nsfw = self.nudenet_analyzer.analizar_imagen(archivo)
                    print(f"[DEBUG] Resultado NudeNet3 para {archivo}: {nsfw}")
                    if nsfw:
                        mensaje_nsfw = f"🔞 Alerta: posible desnudo detectado por NudeNet3\n📅 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        # enviar imagen por WhatsApp
                        self.telegram_client.send_image(self.chat_id, archivo, caption=mensaje_nsfw)

                    mensaje = f"⚡ Detección rápida por teclado\n🔍 Palabra: {palabra_detectada}\n📅 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

                    resultado = self.telegram_client.send_image(self.chat_id, archivo, caption=mensaje)
                    if not resultado:
                        logger.error(f"[❌] Falló envío de captura rápida: {archivo}")
                    else:
                        logger.info(f"[✅] Captura rápida enviada: {archivo}")
                except Exception as e:
                    logger.error(f"[❌] Error en hilo de envío rápido: {e}")
            
            hilo_envio = threading.Thread(target=enviar_en_hilo, daemon=False)
            hilo_envio.start()
            
        except Exception as e:
            logger.error(f"[❌] Error en captura rápida: {e}")
    
    def capturar_y_analizar_ocr(self):
        """Captura y análisis OCR para capturas periódicas"""
        try:
            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            archivo = os.path.join(CARPETA_CAPTURAS, f"ocr_{timestamp}.png")
            
            logger.info(f"[📸] Captura periódica para análisis OCR...")
            
            # Capturar pantalla
            screenshot = pyautogui.screenshot()
            screenshot.save(archivo)
            
            # Verificar que se guardó correctamente
            if not os.path.exists(archivo) or os.path.getsize(archivo) == 0:
                logger.error(f"[❌] Error al guardar captura OCR: {archivo}")
                return
            
            def procesar_en_hilo():
                try:
                    # Analizar con OCR
                    ocr_detectado, palabras_ocr, texto_ocr = self.ocr_analyzer.analizar_texto_ocr(archivo)
                    # Analizar con NudeNet3 la misma captura
                    nsfw = self.nudenet_analyzer.analizar_imagen(archivo)
                    print(f"[DEBUG] Resultado NudeNet3 para {archivo}: {nsfw}")
                    # Enviar alerta si se detecta NSFW
                    if nsfw:
                        mensaje_nsfw = f"🔞 Alerta: posible desnudo detectado por NudeNet3\n📅 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        self.telegram_client.send_image(self.chat_id, archivo, caption=mensaje_nsfw)
                    # Enviar alerta si se detecta palabra clave por OCR
                    if ocr_detectado:
                        mensaje = f"⚠️ Palabra clave detectada por OCR\n🔍 Palabras encontradas: {', '.join(palabras_ocr)}"
                        if texto_ocr and len(texto_ocr) > 0:
                            texto_preview = texto_ocr[:200] + "..." if len(texto_ocr) > 200 else texto_ocr
                            mensaje += f"\n📝 Texto detectado: {texto_preview}"
                        mensaje += f"\n📅 {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        resultado = self.telegram_client.send_image(self.chat_id, archivo, caption=mensaje)
                        if not resultado:
                            logger.error(f"[❌] Falló envío de captura OCR: {archivo}")
                        else:
                            logger.info(f"[✅] Captura OCR enviada: {archivo}")
                    # Si no se detecta nada, eliminar la imagen
                    if not nsfw and not ocr_detectado:
                        logger.info(f"[ℹ️] No se detectaron amenazas en OCR ni NSFW")
                        cleanup_file(archivo)
                except Exception as e:
                    logger.error(f"[❌] Error en procesamiento OCR: {e}")
            
            hilo_procesamiento = threading.Thread(target=procesar_en_hilo, daemon=False)
            hilo_procesamiento.start()
            
        except Exception as e:
            logger.error(f"[❌] Error en captura OCR: {e}")
    
    def capturar_periodica(self):
        """Captura periódica de pantalla SOLO para análisis OCR"""
        while not self.stop_event.is_set():
            try:
                time.sleep(10)  # Intervalo de 10 segundos entre capturas (puedes ajustar este valor)
                self.capturar_y_analizar_ocr()
            except Exception as e:
                logger.error(f"[❌] Error en captura periódica: {e}")
                time.sleep(10)

