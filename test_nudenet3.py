from core.nudenet_analyzer3 import NudeNetAnalyzer
from utils.logger import logger
import sys

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python test_nudenet3.py ruta/a/imagen.jpg")
        sys.exit(1)
    ruta = sys.argv[1]
    analyzer = NudeNetAnalyzer()
    resultado = analyzer.analizar_imagen(ruta)
    print(f"¿NSFW detectado?: {resultado}")
