import os
import time
import yfinance as yf
import feedparser
from google import genai
import requests
from xhtml2pdf import pisa
import smtplib
from email.message import EmailMessage

# Configuración de credenciales de forma segura
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
SENDER_EMAIL = "foggialucianoa@gmail.com"
RECEIVER_EMAIL = "foggialucianoa@gmail.com"

# Inicializar cliente de Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

# Descarga de datos de mercado (threads=False para evitar bloqueos de base de datos en Linux)
print("Descargando datos de mercado...")
tickers = ["^MERV", "GGAL", "YPF", "SPY"]
data = yf.download(tickers, period="5d", progress=False, threads=False)["Close"]

# Análisis de noticias con RSS
print("Procesando noticias financieras...")
rss_url = "https://www.cronista.com/files/rss/finanzas-mercados.xml"
feed = feedparser.parse(rss_url)
titulares = "\n".join([f"- {entry.title}" for entry in feed.entries[:5]])

# Generación de contenido con Gemini (con reintentos automáticos)
print("Generando análisis con Gemini...")
prompt = f"""
Actúa como un analista financiero experto. Con base en los siguientes titulares recientes:
{titulares}
Y los datos de cierre recientes de los activos {tickers}, redacta un resumen ejecutivo breve y profesional para el Morning Briefing de hoy centrado en el mercado argentino e internacional.
"""

analisis_ia = ""
max_intentos = 3
for intento in range(max_intentos):
    try:
        response = client.models.generate_content(
            model="gemini-1.5-flash",
            contents=prompt,
        )
        analisis_ia = response.text
        break
    except Exception as e:
        print(f"Intento {intento + 1} fallido: {e}")
        if intento < max_intentos - 1:
            time.sleep(5)
        else:
            raise e

# Generación del reporte HTML / PDF
html_content = f"""
<html>
<head>
<style>
  body {{ font-family: Helvetica, Arial, sans-serif; color: #333; margin: 30px; }}
  h1 {{ color: #1a365d; border-bottom: 2px solid #1a365d; padding-bottom: 5px; }}
  h2 {{ color: #2b6cb0; margin-top: 20px; }}
  p, li {{ font-size: 14px; line-height: 1.5; }}
  .box {{ background-color: #f7fafc; border: 1px solid #e2e8f0; padding: 15px; border-radius: 5px; }}
</style>
</head>
<body>
    <h1>Morning Briefing Financiero</h1>
    <p><b>Fecha:</b> Reporte Automático Diario</p>
    
    <h2>1. Análisis de Mercado (Gemini)</h2>
    <div class="box">
        {analisis_ia.replace(chr(10), '<br>')}
    </div>

    <h2>2. Titulares Clave del Día</h2>
    <ul>
        { "".join([f"<li>{entry.title}</li>" for entry in feed.entries[:5]]) }
    </ul>
</body>
</html>
"""

pdf_filename = "morning_brief.pdf"
with open(pdf_filename, "wb") as pdf_file:
    pisa.CreatePDF(html_content, dest=pdf_file)

print("PDF generado correctamente.")

# Envío del correo vía Gmail SMTP
print("Enviando correo...")
msg = EmailMessage()
msg["Subject"] = "Morning Briefing Financiero Automático"
msg["From"] = SENDER_EMAIL
msg["To"] = RECEIVER_EMAIL
msg.set_content("Adjunto encontrarás el informe financiero automatizado del día.")

with open(pdf_filename, "rb") as f:
    file_data = f.read()
    file_name = f.name

msg.add_attachment(file_data, maintype="application", subtype="pdf", filename=file_name)

try:
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(SENDER_EMAIL, GMAIL_APP_PASSWORD)
        smtp.send_message(msg)
    print("¡Correo enviado con éxito!")
except Exception as e:
    print(f"Error al enviar el correo: {e}")
