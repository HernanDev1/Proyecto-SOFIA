import tkinter as tk
import tkinter.messagebox
import re


def validar_chat_id(chat_id):
    """Valida formato de número de WhatsApp en E.164 (acepta opcional +)."""
    # Acepta + seguido de 6-15 dígitos o solo dígitos entre 6 y 15
    return re.match(r"^\+?\d{6,15}$", chat_id) is not None


def pedir_chat_id():
    """Ventana para solicitar número de WhatsApp (E.164). Devuelve string."""
    chat_id_resultado = None

    root = tk.Tk()
    root.title("S.O.F.I.A - OCR Edition")
    root.geometry("400x160")
    root.resizable(False, False)

    tk.Label(root, text="Ingrese su número de WhatsApp (E.164). Ej: +54911XXXXXXXX").pack(pady=10)
    entry_chat_id = tk.Entry(root, font=("Arial", 12))
    entry_chat_id.pack(pady=5)

    def confirmar():
        nonlocal chat_id_resultado
        chat_id = entry_chat_id.get().strip()
        if validar_chat_id(chat_id):
            chat_id_resultado = chat_id
            root.destroy()
        else:
            tk.messagebox.showerror("Error", "Número inválido. Usa formato E.164, por ejemplo +54911XXXXXXXX")

    tk.Button(root, text="Confirmar", command=confirmar).pack(pady=10)
    root.mainloop()

    return chat_id_resultado


def pedir_numero_whatsapp_popup(parent=None):
    """Abre una ventana modal para pedir el número de WhatsApp con código de país.

    Devuelve el número validado como string en formato E.164 (ej: +569XXXXXXXX).
    """
    resultado = None

    popup = tk.Toplevel(parent) if parent else tk.Tk()
    popup.title("Número de WhatsApp destino")
    popup.geometry("420x160")
    popup.resizable(False, False)

    tk.Label(popup, text="Ingrese su número de WhatsApp con prefijo de país (ej: +56 para Chile):").pack(pady=10)
    entry = tk.Entry(popup, font=("Arial", 12))
    entry.pack(pady=5)

    def confirmar():
        nonlocal resultado
        val = entry.get().strip()
        if validar_chat_id(val):
            resultado = val
            popup.destroy()
        else:
            tk.messagebox.showerror("Error", "Número inválido. Usa formato E.164, por ejemplo +569XXXXXXXX")

    def cancelar():
        nonlocal resultado
        resultado = None
        popup.destroy()

    btn_frame = tk.Frame(popup)
    btn_frame.pack(pady=10)
    tk.Button(btn_frame, text="Confirmar", command=confirmar).pack(side=tk.LEFT, padx=8)
    tk.Button(btn_frame, text="Cancelar", command=cancelar).pack(side=tk.LEFT, padx=8)

    # Si se creó como Toplevel, bloquear interacción con la ventana padre
    try:
        if parent:
            popup.transient(parent)
            popup.grab_set()
    except Exception:
        pass

    popup.mainloop()
    return resultado