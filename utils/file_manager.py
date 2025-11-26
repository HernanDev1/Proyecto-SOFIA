import os
from config.settings import CARPETA_CAPTURAS
from utils.logger import logger

def create_capture_directory():
    """Crea el directorio de capturas si no existe"""
    if not os.path.exists(CARPETA_CAPTURAS):
        os.makedirs(CARPETA_CAPTURAS)
        logger.info(f"Directorio creado: {CARPETA_CAPTURAS}")

def validate_file(archivo):
    """Valida que un archivo existe y tiene contenido"""
    if not os.path.exists(archivo):
        logger.error(f"Archivo no existe: {archivo}")
        return False
    
    file_size = os.path.getsize(archivo)
    if file_size == 0:
        logger.error(f"Archivo vacío: {archivo}")
        return False
    
    logger.info(f"Tamaño archivo: {file_size} bytes")
    return True

def cleanup_file(archivo):
    """Elimina un archivo de forma segura"""
    try:
        os.remove(archivo)
        logger.info(f"Archivo eliminado: {archivo}")
        return True
    except Exception as e:
        logger.error(f"Error al eliminar archivo {archivo}: {e}")
        return False