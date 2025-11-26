#!/usr/bin/env python3
"""
Prueba envío de texto vía WhatsAppClient.
Uso:
  python test_whatsapp_text.py --to +569XXXXXXXX --message "Mensaje de prueba"
"""
import argparse
from core.whatsapp_client import WhatsAppClient

parser = argparse.ArgumentParser(description='Enviar texto de prueba por WhatsApp Cloud API')
parser.add_argument('--to', required=True, help='Número destino (E.164)')
parser.add_argument('--message', required=True, help='Texto del mensaje')
args = parser.parse_args()

client = WhatsAppClient()
print('Enviando a', args.to)
ok = client.send_text(to_number=args.to, message=args.message)
print('Resultado send_text:', ok)
if not ok:
    raise SystemExit(1)
