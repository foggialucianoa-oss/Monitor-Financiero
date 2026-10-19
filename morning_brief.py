import os
import time
import tempfile
import re
import yfinance as yf
import feedparser
from google import genai
import requests
from xhtml2pdf import pisa
import smtplib
from email.message import EmailMessage

# Evitar errores de caché de yfinance
cache_dir = tempfile.mkdtemp()
yf.set_tz_cache_location(cache_dir)

# Configuración de credenciales de forma segura
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
SENDER_EMAIL = "foggialucianoa@gmail.com"
RECEIVER_EMAIL = "foggialucianoa@gmail.com"

# Inicializar cliente de Gemini
client = genai.Client(api_key=GEMINI_API_KEY)

# Descarga de datos de mercado
print("Descargando datos de mercado...")
tickers = ["^MERV", "GGAL", "YPF", "SPY"]
data = yf.download(tickers, period="5d", progress=False, threads=False)["Close"]

# Análisis de noticias con RSS
print("Procesando noticias financieras...")
rss_url = "https://www.cronista.com/files/rss/finanzas-mercados.xml"
feed = feedparser.parse(rss_url)
titulares = "\n".join([f"- {entry.title}" for entry in feed.entries[:5]])

# Generación de contenido con Gemini
print("Generando análisis con Gemini...")
prompt = f"""
Actúa como un analista financiero experto. Con base en los siguientes titulares recientes:
{titulares}
Y los datos de cierre recientes de los activos {tickers}, redacta un resumen ejecutivo breve y profesional para el Morning Briefing de hoy centrado en el mercado argentino e internacional. Usá subtítulos claros y formato de texto limpio.
"""

analisis_ia = ""
max_intentos = 5
for intento in range(max_intentos):
    try:
        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt,
        )
        analisis_ia = response.text
        break
    except Exception as e:
        print(f"Intento {intento + 1} fallido: {e}")
        if intento < max_intentos - 1:
            time.sleep(8)
        else:
            raise e

# Función simple para limpiar el markdown de la IA y pasarlo a HTML legible en el PDF
def markdown_a_html(texto):
    # Reemplazar títulos ###
    texto = re.sub(r'###\s+(.*)', r'<h3>\1</h3>', texto)
    texto = re.sub(r'##\s+(.*)', r'<h2>\1</h2>', texto)
    # Reemplazar negritas **texto**
    texto = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', texto)
    # Reemplazar saltos de línea
    texto = texto.replace('\n', '<br>')
    return texto

analisis_html = markdown_a_html(analisis_ia)

# Generación del reporte HTML / PDF estilizado
html_content = f"""
<html>
<head>
<style>
  body {{ font-family: Helvetica, Arial, sans-serif; color: #2d3748; margin: 30px; font-size: 13px; line-height: 1.6; }}
  h1 {{ color: #1a365d; border-bottom: 2px solid #2b6cb0; padding-bottom: 8px; font-size: 22px; }}
  h2 {{ color: #2b6cb0; margin-top: 25px; font-size: 16px; border-bottom: 1px solid #e2e8f0; padding-bottom: 4px; }}
  h3 {{ color: #2c5282; margin-top: 15px; font-size: 14px; }}
  p, li {{ font-size: 13px; line-height: 1.5; }}
  .box {{ background-color: #f8fafc; border: 1px solid #cbd5e0; padding: 15px; border-radius: 6px; margin-top: 10px; }}
  ul {{ margin-top: 5px; padding-left: 20px; }}
  li {{ margin-bottom: 6px; }}
</style>
</head>
<body>
    <h1>Morning Briefing Financiero</h1>
    <p><b>Fecha de Emisión:</b> Reporte Automático Diario</p>
    
    <h2>1. Análisis de Mercado (Gemini)</h2>
    <div class="box">
        {analisis_html}
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

print("PDF generado correctamente con formato limpio.")

# Envío del correo vía Gmail SMTP
print("Enviando correo...")
msg = EmailMessage()
msg["Subject"] = "Morning Briefing Financiero Automático"
msg["From"] = SENDER_EMAIL
msg["To"] = RECEIVER_EMAIL
msg.set_content("Adjunto encontrarás el informe financiero automatizado del día con formato profesional.")

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
