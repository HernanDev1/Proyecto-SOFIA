#!/usr/bin/env python3
"""
Prueba envío de imagen vía WhatsAppClient.
Uso:
  python test_whatsapp_image.py --to +569XXXXXXXX --file "capturas/ejemplo.png" --caption "Prueba imagen"
"""
import argparse
import os
from core.whatsapp_client import WhatsAppClient

parser = argparse.ArgumentParser(description='Enviar imagen de prueba por WhatsApp Cloud API')
parser.add_argument('--to', required=True, help='Número destino (E.164)')
parser.add_argument('--file', required=True, help='Ruta al archivo a enviar')
parser.add_argument('--caption', required=False, default=None, help='Leyenda opcional')
args = parser.parse_args()

if not os.path.exists(args.file):
    print('ERROR: archivo no encontrado:', args.file)
    raise SystemExit(2)

client = WhatsAppClient()
print('Enviando imagen', args.file, 'a', args.to)
ok = client.send_image(to_number=args.to, file_path=args.file, caption=args.caption)
print('Resultado send_image:', ok)
if not ok:
    raise SystemExit(1)
