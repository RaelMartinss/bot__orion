import time
import subprocess
from datetime import datetime

HORA_ALARME = 16
MINUTO_ALARME = 55

print("⏰ Alarme de água ativado! Aguardando 16h55...")

while True:
    agora = datetime.now()
    if agora.hour == HORA_ALARME and agora.minute == MINUTO_ALARME:
        subprocess.Popen([
            "powershell", "-Command",
            """
            Add-Type -AssemblyName System.Windows.Forms;
            [System.Windows.Forms.MessageBox]::Show(
                'Rael, nao esquece de se hidratar! Beba um copo dagua agora! 💧',
                'Hora de Tomar Agua!',
                'OK',
                'Information'
            )
            """
        ])
        print("✅ Notificação enviada às 16h55!")
        break
    time.sleep(30)
