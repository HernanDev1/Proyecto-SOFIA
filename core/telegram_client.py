import asyncio
import time
import threading
from telegram import Bot
from telegram.request import HTTPXRequest
from config.settings import TOKEN, HTTP_CONFIG, DELAY_ENTRE_ENVIOS
from utils.logger import logger
from utils.file_manager import validate_file

class TelegramClient:
    def __init__(self):
        self.ultimo_envio = 0
        self.envio_en_proceso = False
        self.lock_envio = threading.Lock()
        
        # Configurar bot
        request = HTTPXRequest(**HTTP_CONFIG)
        self.bot = Bot(token=TOKEN, request=request)
    
    def puede_enviar(self):
        """Verifica si puede enviar (rate limiting)"""
        with self.lock_envio:
            tiempo_actual = time.time()
            
            if self.envio_en_proceso:
                logger.info("[⏳] Envío ya en proceso, esperando...")
                return False
            
            if tiempo_actual - self.ultimo_envio < DELAY_ENTRE_ENVIOS:
                tiempo_restante = DELAY_ENTRE_ENVIOS - (tiempo_actual - self.ultimo_envio)
                logger.info(f"[⏳] Esperando {tiempo_restante:.1f}s más entre envíos...")
                return False
            
            return True
    
    async def enviar_foto_seguro(self, archivo, mensaje, chat_id):
        """Función unificada para envío seguro con mejor manejo de errores"""
        if not self.puede_enviar():
            logger.info(f"[⏭️] Envío bloqueado por rate limiting: {archivo}")
            return False
        
        with self.lock_envio:
            self.envio_en_proceso = True
        
        max_intentos = 2
        delay_base = 10
        
        try:
            for intento in range(max_intentos):
                try:
                    logger.info(f"[📤] Intento {intento + 1}/{max_intentos} - Enviando: {archivo}")
                    
                    if not validate_file(archivo):
                        return False
                    
                    if intento > 0:
                        logger.info("[🔄] Recreando conexión del bot...")
                        await asyncio.sleep(5)
                    
                    with open(archivo, 'rb') as f:
                        await self.bot.send_photo(
                            chat_id=chat_id,
                            photo=f,
                            caption=mensaje,
                            connect_timeout=60,
                            read_timeout=120,
                            write_timeout=120
                        )
                    
                    logger.info(f"[✅] Imagen enviada exitosamente: {archivo}")
                    with self.lock_envio:
                        self.ultimo_envio = time.time()
                    return True
                    
                except Exception as e:
                    error_msg = str(e).lower()
                    logger.error(f"[⚠️] Intento {intento + 1} fallido: {e}")
                    
                    if "pool timeout" in error_msg or "pool" in error_msg:
                        delay = delay_base * (2 ** intento)
                        logger.info(f"[⏳] Error de pool, esperando {delay}s...")
                        await asyncio.sleep(delay)
                    elif "timeout" in error_msg:
                        delay = delay_base * (intento + 1)
                        logger.info(f"[⏳] Error de timeout, esperando {delay}s...")
                        await asyncio.sleep(delay)
                    elif "rate limit" in error_msg:
                        logger.info(f"[⏳] Rate limit, esperando 60s...")
                        await asyncio.sleep(60)
                    elif intento < max_intentos - 1:
                        await asyncio.sleep(delay_base)
                    else:
                        logger.error(f"[❌] Error final después de {max_intentos} intentos: {e}")
                        return False
            
            return False
            
        finally:
            with self.lock_envio:
                self.envio_en_proceso = False
    
    def enviar_foto_sync(self, archivo, mensaje, chat_id):
        """Wrapper síncrono mejorado con recreación de loop"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            try:
                result = loop.run_until_complete(self.enviar_foto_seguro(archivo, mensaje, chat_id))
                return result
            finally:
                loop.close()
                
        except Exception as e:
            logger.error(f"[❌] Error en envío síncrono: {e}")
            return False