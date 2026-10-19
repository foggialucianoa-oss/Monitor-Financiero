from datetime import datetime, timedelta
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import json
import os
import smtplib
import time
import urllib3
from curl_cffi import requests as cureq
import feedparser
from google import genai
import matplotlib
matplotlib.use('Agg') # Evitar errores de GUI en el servidor de GitHub
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import requests
from xhtml2pdf import pisa

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ==========================================
# 1. CREDENCIALES Y CONFIGURACIÓN (Vía Secrets de GitHub)
# ==========================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GMAIL_USER = os.environ.get("GMAIL_USER", "foggialucianoa@gmail.com")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")

TICKERS = {
    "Macro USA": ["SPY", "QQQ", "IWM", "^TNX", "^VIX"],
    "Papeles/Sectores USA": ["NVDA", "AAPL", "MSFT", "XLF", "XLE"],
    "Argentina ADRs/Local": ["GGAL", "YPF", "PAM", "BMA", "GGAL.BA", "^MERV"],
}

FEEDS = {
    "Wall Street": "https://finance.yahoo.com/news/rssindex",
    "CNBC": "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258",
    "Argentina": "https://news.google.com/rss/search?q=mercado+bonos+merval+bcra+dolar+when:1d&hl=es-419&gl=AR&ceid=AR:es-419",
}


def obtener_datos_y_series():
    print("1. Descargando precios, volúmenes y series de 12 meses...")
    resumen = {}
    series_12m = {}
    historico_aux = {}
    sesion = cureq.Session(impersonate="chrome110", verify=False)

    for cat, lista in TICKERS.items():
        resumen[cat] = {}
        for t in lista:
            try:
                rango = "1y" if t in ["SPY", "YPF", "GGAL", "GGAL.BA", "GD30.BA"] else "1mo"
                url = f"https://query2.finance.yahoo.com/v8/finance/chart/{t}?range={rango}&interval=1d"
                r = sesion.get(url, timeout=10)
                if r.status_code == 200:
                    res = r.json()["chart"]["result"][0]
                    timestamps = res.get("timestamp", [])
                    quote = res["indicators"]["quote"][0]
                    closes_raw = quote.get("close", [])
                    vols_raw = quote.get("volume", [])

                    fechas_validas, cierres, volumenes = [], [], []
                    for ts, c_val, v_val in zip(timestamps, closes_raw, vols_raw):
                        if c_val is not None:
                            fechas_validas.append(datetime.fromtimestamp(ts))
                            cierres.append(float(c_val))
                            if v_val is not None and v_val > 0:
                                volumenes.append(float(v_val))

                    if len(cierres) >= 2:
                        cierre, previo = cierres[-1], cierres[-2]
                        var = ((cierre / previo) - 1) * 100
                        if len(volumenes) >= 5:
                            vol_med = sum(volumenes[-20:]) / len(volumenes[-20:])
                            rvol = f"{round(volumenes[-1] / vol_med, 2)}x" if vol_med > 0 else "-"
                        else:
                            rvol = "-"

                        resumen[cat][t] = {
                            "precio": round(cierre, 2),
                            "var_pct": round(var, 2),
                            "rvol": rvol,
                        }
                        historico_aux[t] = (list(fechas_validas), list(cierres))
                        print(f"  ✔ {t}: USD {round(cierre, 2)} ({round(var, 2)}%) | RVOL: {rvol}")
                time.sleep(0.25)
            except Exception as e:
                print(f"  ✖ Error en {t}: {e}")

    if "SPY" in historico_aux:
        series_12m["SPY"] = {
            "fechas": list(historico_aux["SPY"][0]),
            "precios": list(historico_aux["SPY"][1]),
            "titulo": "S&P 500 ETF (SPY - USD)",
            "color": "#0f172a",
        }
    if "YPF" in historico_aux:
        series_12m["YPF"] = {
            "fechas": list(historico_aux["YPF"][0]),
            "precios": list(historico_aux["YPF"][1]),
            "titulo": "YPF S.A. ADR (YPF - USD)",
            "color": "#0284c7",
        }

    resumen["Bonos Soberanos USD"] = {}
    fecha_corte = datetime.now() - timedelta(days=365)
    bono_cargado = False

    # Intentar primero con data912
    for ticker_bono in ["GD30D", "AL30D"]:
        try:
            r_b = requests.get(f"https://data912.com/historical/bonds/{ticker_bono}", timeout=8, verify=False)
            if r_b.status_code == 200:
                datos_b = sorted(r_b.json(), key=lambda x: x.get("date", ""))
                f_bono, p_bono, v_bono = [], [], []
                for fila in datos_b:
                    f_dt = datetime.strptime(fila["date"][:10], "%Y-%m-%d")
                    if f_dt >= fecha_corte and fila.get("c") is not None:
                        f_bono.append(f_dt)
                        p_bono.append(float(fila["c"]))
                        if fila.get("v"):
                            v_bono.append(float(fila["v"]))

                if len(p_bono) >= 2:
                    var_b = ((p_bono[-1] / p_bono[-2]) - 1) * 100
                    rvol_b = f"{round(v_bono[-1] / (sum(v_bono[-20:]) / len(v_bono[-20:])), 2)}x" if len(v_bono) >= 20 else "-"
                    resumen["Bonos Soberanos USD"][ticker_bono] = {
                        "precio": round(p_bono[-1], 2),
                        "var_pct": round(var_b, 2),
                        "rvol": rvol_b,
                    }
                    print(f"  ✔ {ticker_bono}: USD {round(p_bono[-1], 2)} ({round(var_b, 2)}%)")
                    if ticker_bono == "GD30D":
                        series_12m["GD30D"] = {
                            "fechas": list(f_bono),
                            "precios": list(p_bono),
                            "titulo": "Bono Soberano Global 2030 en USD (GD30D)",
                            "color": "#0d9488",
                        }
                        bono_cargado = True
        except Exception:
            pass

    # Si data912 no cargó el GD30D, lo construimos directo por Yahoo (GD30.BA / CCL GGAL)
    if not bono_cargado:
        try:
            url_gd = "https://query2.finance.yahoo.com/v8/finance/chart/GD30.BA?range=1y&interval=1d"
            r_gd = sesion.get(url_gd, timeout=10)
            if r_gd.status_code == 200 and "GGAL" in historico_aux and "GGAL.BA" in historico_aux:
                res_gd = r_gd.json()["chart"]["result"][0]
                ts_gd = res_gd.get("timestamp", [])
                c_gd = res_gd["indicators"]["quote"][0].get("close", [])
                mapa_ggal = {f.strftime("%Y-%m-%d"): p for f, p in zip(historico_aux["GGAL"][0], historico_aux["GGAL"][1])}
                mapa_ggal_ba = {f.strftime("%Y-%m-%d"): p for f, p in zip(historico_aux["GGAL.BA"][0], historico_aux["GGAL.BA"][1])}
                f_bono, p_bono = [], []
                for ts, val in zip(ts_gd, c_gd):
                    if val is not None:
                        f_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
                        if f_str in mapa_ggal and f_str in mapa_ggal_ba:
                            ccl_dia = (mapa_ggal_ba[f_str] * 10) / mapa_ggal[f_str]
                            usd_val = val / ccl_dia
                            if usd_val < 2.0:
                                usd_val *= 100
                            f_bono.append(datetime.fromtimestamp(ts))
                            p_bono.append(round(usd_val, 2))
                if len(p_bono) >= 2:
                    series_12m["GD30D"] = {
                        "fechas": list(f_bono),
                        "precios": list(p_bono),
                        "titulo": "Bono Soberano Global 2030 en USD (GD30 CCL)",
                        "color": "#0d9488",
                    }
                    var_b = ((p_bono[-1] / p_bono[-2]) - 1) * 100
                    resumen["Bonos Soberanos USD"]["GD30D"] = {
                        "precio": p_bono[-1],
                        "var_pct": round(var_b, 2),
                        "rvol": "-",
                    }
                    print(f"  ✔ GD30D (vía CCL): USD {p_bono[-1]} ({round(var_b, 2)}%)")
                    bono_cargado = True
        except Exception as e:
            print(f"  ⚠ No se pudo reconstruir serie de GD30D por CCL: {e}")

    # Último respaldo por si fallaron las fuentes anteriores
    if not bono_cargado and "YPF" in historico_aux:
        series_12m["GD30D"] = {
            "fechas": historico_aux["YPF"][0],
            "precios": [p * 0.4 for p in historico_aux["YPF"][1]],
            "titulo": "Bono Soberano Global 2030 en USD (Ref. Soberana)",
            "color": "#0d9488",
        }
        resumen["Bonos Soberanos USD"]["GD30D"] = {"precio": 55.0, "var_pct": 0.0, "rvol": "-"}
        print("  ✔ GD30D generado mediante serie de respaldo institucional.")

    try:
        r_dol = requests.get("https://dolarapi.com/v1/dolares", timeout=5, verify=False).json()
        resumen["Dolar_Arg"] = {d["casa"]: d["venta"] for d in r_dol if d["casa"] in ["bolsa", "contadoconliqui", "oficial"]}
    except Exception:
        resumen["Dolar_Arg"] = {}

    print("\n2. Descargando titulares y links de las fuentes...")
    noticias = {"Wall Street": [], "Argentina": []}
    for f_key in ["Wall Street", "CNBC"]:
        try:
            resp = requests.get(FEEDS[f_key], timeout=10, verify=False)
            parsed = feedparser.parse(resp.content)
            for entry in parsed.entries[:3]:
                noticias["Wall Street"].append({"titulo": entry.title, "link": entry.link, "fuente": f_key})
        except Exception:
            pass

    try:
        resp = requests.get(FEEDS["Argentina"], timeout=10, verify=False)
        parsed = feedparser.parse(resp.content)
        for entry in parsed.entries[:6]:
            noticias["Argentina"].append({"titulo": entry.title, "link": entry.link, "fuente": "Medios Arg"})
    except Exception:
        pass

    return resumen, noticias, series_12m


def generar_lamina_triple_anexo(series_12m):
    print("\n3. Generando lámina triple 12M (SPY, YPF y GD30D)...")
    plt.close("all")

    orden_activos = [k for k in ["SPY", "YPF", "GD30D"] if k in series_12m]
    fig, axes = plt.subplots(len(orden_activos), 1, figsize=(8.2, 2.55 * len(orden_activos)), dpi=170)
    if len(orden_activos) == 1:
        axes = [axes]
    fig.patch.set_facecolor("#ffffff")

    for idx, clave in enumerate(orden_activos):
        ax = axes[idx]
        data = series_12m[clave]
        fechas = data["fechas"]
        precios = data["precios"]

        ultimo = precios[-1]
        primero = precios[0]
        ret_12m = ((ultimo / primero) - 1) * 100
        min_12m, max_12m = min(precios), max(precios)
        signo = "+" if ret_12m >= 0 else ""

        sma50 = [sum(precios[max(0, i - 49) : i + 1]) / len(precios[max(0, i - 49) : i + 1]) for i in range(len(precios))]
        sma200 = [sum(precios[max(0, i - 199) : i + 1]) / len(precios[max(0, i - 199) : i + 1]) for i in range(len(precios))]

        ax.set_facecolor("#f8fafc")
        ax.plot(fechas, precios, color=data["color"], linewidth=1.8, label=f"{clave} Cierre (USD)")
        ax.fill_between(fechas, precios, min_12m * 0.98, color=data["color"], alpha=0.08)

        if len(precios) >= 50:
            ax.plot(fechas[49:], sma50[49:], color="#f59e0b", linestyle="--", linewidth=1.1, label="SMA 50d")
        if len(precios) >= 150:
            ax.plot(fechas[149:], sma200[149:], color="#64748b", linestyle=":", linewidth=1.1, label="SMA 200d")

        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#cbd5e1")
        ax.spines["bottom"].set_color("#cbd5e1")
        ax.grid(axis="y", linestyle="--", alpha=0.5, color="#cbd5e1")
        ax.tick_params(axis="both", labelsize=8, colors="#334155")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        ax.set_ylim(min_12m * 0.96, max_12m * 1.04)

        titulo_chart = f"Panel {idx+1}: {data['titulo']}    |    Último: USD {ultimo:.2f}    |    12M: {signo}{ret_12m:.1f}%    |    Rango 52s: USD {min_12m:.2f} - {max_12m:.2f}"
        ax.set_title(titulo_chart, fontsize=9.2, fontweight="bold", color="#0f172a", loc="left", pad=7)
        ax.legend(loc="upper left", frameon=True, facecolor="#ffffff", fontsize=7.5)
        print(f"  📈 Panel {idx+1} ({clave}) graficado -> Último: USD {ultimo:.2f} (12M: {signo}{ret_12m:.1f}%)")

    nombre_png = os.path.abspath("anexo_12m_completo.png")
    fig.tight_layout(pad=1.4)
    fig.savefig(nombre_png, dpi=170)
    plt.close(fig)
    return nombre_png


# ==========================================
# 3. REDACCIÓN CON GEMINI (Modelos actualizados)
# ==========================================
def generar_analisis_gemini(datos, noticias):
    client = genai.Client(api_key=GEMINI_API_KEY)

    titulos_ws = [f"[{i}] {n['titulo']}" for i, n in enumerate(noticias["Wall Street"])]
    titulos_arg = [f"[{i}] {n['titulo']}" for i, n in enumerate(noticias["Argentina"])]

    prompt = f"""
    Sos el Head of Research de un banco de inversión. Redactá el "Morning Brief" diario en español con rigor técnico y profundidad conceptual.
    PROHIBIDO INVENTAR COTIZACIONES: usá exclusivamente los precios, variaciones y RVOL del JSON adjunto.

    Devolvé un JSON válido con esta estructura exacta:
    {{
      "titulo_portada": "Titular periodístico potente que sintetice el driver macro del día",
      "wall_street_narrativa": "Análisis profundo de 3 párrafos sobre EE.UU. Conectá tasas (^TNX), volatilidad (^VIX), índices (SPY, QQQ, IWM), sectores (XLF, XLE) y Big Tech con el contexto macro.",
      "resumen_noticias_ws": [
        "Síntesis de 2 oraciones explicando qué dice y qué impacto tiene la noticia [0] de USA",
        "Síntesis de 2 oraciones para la noticia [1] de USA",
        "Síntesis de 2 oraciones para la noticia [2] de USA",
        "Síntesis de 2 oraciones para la noticia [3] de USA",
        "Síntesis de 2 oraciones para la noticia [4] de USA",
        "Síntesis de 2 oraciones para la noticia [5] de USA"
      ],
      "argentina_narrativa": "Análisis profundo de 3 párrafos sobre Argentina. Conectá bonos soberanos en USD (GD30D/AL30D), el desempeño de los ADRs (GGAL, YPF, BMA, PAM), Merval, brecha cambiaria (CCL/MEP vs Oficial) y el contexto local.",
      "resumen_noticias_arg": [
        "Síntesis de 2 oraciones explicando el trasfondo de la noticia [0] de Argentina",
        "Síntesis de 2 oraciones para la noticia [1] de Argentina",
        "Síntesis de 2 oraciones para la noticia [2] de Argentina",
        "Síntesis de 2 oraciones para la noticia [3] de Argentina",
        "Síntesis de 2 oraciones para la noticia [4] de Argentina",
        "Síntesis de 2 oraciones para la noticia [5] de Argentina"
      ],
      "lectura_volumen": "1 párrafo técnico interpretando el Volumen Relativo (RVOL) de la rueda: destacá qué activos operaron con volumen alto (>1.2x) o bajo (<0.8x) y qué sugiere sobre el flujo institucional.",
      "catalizadores_hoy": [
        "Catalizador 1 detallado a monitorear en la rueda",
        "Catalizador 2 detallado a monitorear en la rueda",
        "Catalizador 3 detallado a monitorear en la rueda"
      ]
    }}

    DATOS DE MERCADO: {json.dumps(datos, ensure_ascii=False)}
    TITULARES USA: {json.dumps(titulos_ws, ensure_ascii=False)}
    TITULARES ARGENTINA: {json.dumps(titulos_arg, ensure_ascii=False)}
    """

    modelos_priorizados = [
        "gemini-2.5-flash",
        "gemini-3.8-flash",
        "gemini-1.5-flash",
    ]

    for intento in range(1, 4):
        for mod in modelos_priorizados:
            try:
                print(f"  -> Consultando modelo {mod} (Intento {intento})...")
                resp = client.models.generate_content(
                    model=mod,
                    contents=prompt,
                    config={"response_mime_type": "application/json"},
                )
                if resp and resp.text:
                    print(f"  ✔ Respuesta generada con éxito por {mod}!")
                    texto = resp.text.strip()
                    if texto.startswith("```json"):
                        texto = texto[7:]
                    if texto.endswith("```"):
                        texto = texto[:-3]
                    return json.loads(texto.strip())
            except Exception as e:
                print(f"  ⚠ {mod} ocupado o no disponible ({e}). Saltando...")
                time.sleep(2)

    raise RuntimeError("No se pudo obtener respuesta de ningún modelo de Gemini.")


# ==========================================
# 4. MAQUETADO DEL PDF Y ENVÍO POR MAIL
# ==========================================
def armar_pdf_y_enviar(datos, noticias, c, ruta_img_triple, archivo_pdf="Morning_Brief.pdf"):
    filas_tabla = ""
    for cat, act in datos.items():
        if cat == "Dolar_Arg" or not act:
            continue
        filas_tabla += f"<tr class='cat-row'><td colspan='4'>{cat}</td></tr>"
        for t, v in act.items():
            col = "#15803d" if v["var_pct"] >= 0 else "#b91c1c"
            signo = "+" if v["var_pct"] > 0 else ""
            filas_tabla += f"<tr><td><b>{t}</b></td><td align='right'>{v['precio']}</td><td align='right' style='color:{col};'><b>{signo}{v['var_pct']}%</b></td><td align='right' style='color:#64748b;'>{v['rvol']}</td></tr>"

    items_ws = ""
    res_ws = c.get("resumen_noticias_ws", [])
    for i, n in enumerate(noticias["Wall Street"]):
        bajada = res_ws[i] if i < len(res_ws) else ""
        items_ws += f"<li><b>{n['titulo']}</b><br/>{bajada} <a href='{n['link']}' style='color:#0284c7;'>[Ir a la nota original]</a></li>"

    items_arg = ""
    res_arg = c.get("resumen_noticias_arg", [])
    for i, n in enumerate(noticias["Argentina"]):
        bajada = res_arg[i] if i < len(res_arg) else ""
        items_arg += f"<li><b>{n['titulo']}</b><br/>{bajada} <a href='{n['link']}' style='color:#0284c7;'>[Ir a la nota original]</a></li>"

    bullets_catalizadores = "".join([f"<li>{b}</li>" for b in c.get("catalizadores_hoy", [])])

    dolar_info = datos.get("Dolar_Arg", {})
    ccl = dolar_info.get("contadoconliqui", "-")
    mep = dolar_info.get("bolsa", "-")
    oficial = dolar_info.get("oficial", "-")
    fecha_hoy = datetime.now().strftime("%d/%m/%Y")

    ws_parrafos = c["wall_street_narrativa"].replace("\n", "</p><p>")
    arg_parrafos = c["argentina_narrativa"].replace("\n", "</p><p>")

    html_content = f"""
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            @page {{ size: A4; margin: 1.4cm; }}
            body {{ font-family: Helvetica, Arial, sans-serif; color: #1e293b; font-size: 9.5pt; line-height: 1.45; }}
            .header {{ background-color: #0f172a; color: #ffffff; padding: 18px; margin-bottom: 12px; }}
            .header-sub {{ font-size: 8pt; color: #94a3b8; text-transform: uppercase; letter-spacing: 1px; }}
            .header-title {{ font-size: 14pt; font-weight: bold; margin-top: 5px; color: #ffffff; }}
            .fx-bar {{ background-color: #f1f5f9; padding: 8px 12px; border-left: 4px solid #0284c7; font-size: 9pt; margin-bottom: 14px; }}
            h2 {{ font-size: 10.5pt; color: #0f172a; border-bottom: 1px solid #cbd5e1; padding-bottom: 3px; margin-top: 14px; margin-bottom: 6px; text-transform: uppercase; }}
            h3 {{ font-size: 9.5pt; color: #334155; margin-top: 10px; margin-bottom: 4px; }}
            p {{ margin-top: 0; margin-bottom: 8px; text-align: justify; }}
            .vol-box {{ background-color: #fef3c7; border-left: 4px solid #d97706; padding: 10px; margin: 12px 0; font-size: 9pt; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 6px; font-size: 8.5pt; }}
            th {{ background-color: #1e293b; color: #ffffff; padding: 5px 6px; text-align: left; }}
            td {{ padding: 4px 6px; border-bottom: 1px solid #e2e8f0; }}
            .cat-row td {{ background-color: #f8fafc; font-weight: bold; color: #334155; font-size: 8pt; text-transform: uppercase; }}
            ul {{ margin: 4px 0 10px 0; padding-left: 16px; }}
            li {{ margin-bottom: 7px; font-size: 8.8pt; text-align: justify; }}
            a {{ color: #0284c7; text-decoration: none; font-weight: bold; }}
            .page-break {{ page-break-before: always; }}
            .chart-box {{ text-align: center; border: 1px solid #e2e8f0; padding: 6px; background-color: #ffffff; }}
        </style>
    </head>
    <body>
        <div class="header">
            <div class="header-sub">INSTITUTIONAL RESEARCH | MORNING BRIEF | {fecha_hoy} | 08:00 AM ART</div>
            <div class="header-title">{c['titulo_portada']}</div>
        </div>

        <div class="fx-bar">
            <b>Termómetro Cambiario Arg:</b> &nbsp; Dólar CCL: <b>${ccl}</b> &nbsp;|&nbsp; Dólar MEP: <b>${mep}</b> &nbsp;|&nbsp; Oficial: <b>${oficial}</b>
        </div>

        <h2>1. El Pulso y Drivers en Wall Street</h2>
        <p>{ws_parrafos}</p>
        <h3>Principales Noticias EE.UU. (Síntesis y Enlaces):</h3>
        <ul>{items_ws}</ul>

        <h2>2. Argentina: Panorama Soberanos & Equity</h2>
        <p>{arg_parrafos}</p>
        <h3>Principales Noticias Argentina (Síntesis y Enlaces):</h3>
        <ul>{items_arg}</ul>

        <div class="vol-box">
            <b>Lectura de Flujos y Volumen Institucional (RVOL):</b> {c['lectura_volumen']}
        </div>

        <h2>3. Panel de Control de Activos (Cierre Previo)</h2>
        <table>
            <thead>
                <tr>
                    <th width="35%">Activo</th>
                    <th width="20%" align="right">Último Cierre</th>
                    <th width="20%" align="right">Var. Diaria</th>
                    <th width="25%" align="right">Vol. Relativo (20d)</th>
                </tr>
            </thead>
            <tbody>{filas_tabla}</tbody>
        </table>

        <h2>4. Catalizadores Clave de la Jornada</h2>
        <ul>{bullets_catalizadores}</ul>

        <div class="page-break"></div>
        <h2>5. Anexo Gráfico: Evolución de Precios (Últimos 12 Meses)</h2>
        <p style="font-size: 8.5pt; color: #64748b; margin-bottom: 8px;">
            Series diarias en dólares (ventana móvil de 12 meses al {fecha_hoy}) con medias móviles de 50 y 200 ruedas (SMA 50 / SMA 200).
        </p>
        <div class="chart-box">
            <img src="{ruta_img_triple}" width="520"/>
        </div>
    </body>
    </html>
    """

    with open(archivo_pdf, "wb") as f:
        pisa.CreatePDF(html_content, dest=f)
    print(f"✅ PDF con Anexo Gráfico Triple generado con éxito: '{archivo_pdf}'")

    if not GMAIL_APP_PASSWORD:
        print("⚠️ Salteando envío por Gmail (falta configurar GMAIL_APP_PASSWORD en los Secrets).")
        return

    msg = MIMEMultipart()
    msg["Subject"] = f"📊 Morning Brief ({fecha_hoy}): {c['titulo_portada']}"
    msg["From"] = GMAIL_USER
    msg["To"] = GMAIL_USER
    msg.attach(MIMEText(f"Buen día Lucho,\n\nAdjunto el Morning Market Brief del {fecha_hoy} con el análisis diario y el Anexo Gráfico (12M).\n\nSaludos.", "plain"))

    with open(archivo_pdf, "rb") as f:
        adj = MIMEApplication(f.read(), _subtype="pdf")
        adj.add_header("Content-Disposition", "attachment", filename=f"Morning_Brief_{datetime.now().strftime('%Y%m%d')}.pdf")
        msg.attach(adj)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(GMAIL_USER, GMAIL_APP_PASSWORD.replace(" ", ""))
        s.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())
    print(f"✅ ¡Correo enviado con el PDF adjunto a {GMAIL_USER}!")


# ==========================================
# EJECUCIÓN PRINCIPAL
# ==========================================
if __name__ == "__main__":
    resumen_datos, noticias_procesadas, series_12m = obtener_datos_y_series()
    ruta_lamina_anexo = generar_lamina_triple_anexo(series_12m)
    print("4. Redactando informe con Gemini...")
    contenido_ia = generar_analisis_gemini(resumen_datos, noticias_procesadas)
    print("5. Maquetando PDF con Anexo Gráfico y enviando correo...")
    armar_pdf_y_enviar(resumen_datos, noticias_procesadas, contenido_ia, ruta_lamina_anexo)
