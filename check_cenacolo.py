#!/usr/bin/env python3
"""
Vigilante de entradas del Cenacolo Vinciano (Milan).

Carga las paginas de evento de Vivaticket con un navegador headless y lee el
array JS `eventi[<id>]` que ya contiene la disponibilidad de TODO el trimestre.
Cada fila es: [tcode, pcode, fecha, plazas_libres, n_turnos, max_por_compra]

No compra nada. No rellena formularios. No toca captchas ni proxies.
Solo lee una pagina publica y avisa por Telegram.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

from playwright.sync_api import sync_playwright

# --------------------------------------------------------------------------
# Configuracion
# --------------------------------------------------------------------------

BASE = "https://cenacolovinciano.vivaticket.it"

EVENTOS = {
    "151991": ("Entrada normal (15 EUR)",
               "/it/event/cenacolo-vinciano/151991?idt=2547"),
    "238362": ("Visita guiada en italiano",
               "/it/event/cenacolo-visite-guidate-a-orario-fisso-in-italiano/238362?idt=2547"),
    "238363": ("Visita guiada en ingles",
               "/it/event/cenacolo-visite-guidate-a-orario-fisso-in-inglese/238363?idt=2547"),
    "238367": ("Visita-laboratorio (ITA/ENG)",
               "/it/event/cenacolo-vinciano-laboratorio-individuali-famiglie-ita-eng/238367?idt=2547"),
}

# Dias que buscamos. El 19 de octubre es lunes y el museo cierra.
FECHAS_OBJETIVO = [date(2026, 10, d) for d in (14, 15, 16, 17, 18)]

# Minimo de plazas que necesitas juntas.
MIN_PLAZAS = 2

STATE_FILE = "state.json"

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")

# JS que se ejecuta dentro de la pagina para extraer el array de disponibilidad.
EXTRACT_JS = """
() => {
  if (typeof eventi === 'undefined') return null;
  const out = {};
  for (const id of Object.keys(eventi)) {
    out[id] = eventi[id].map(x => ({
      tcode: x[0],
      pcode: x[1],
      y: x[2].getFullYear(),
      m: x[2].getMonth() + 1,
      d: x[2].getDate(),
      plazas: x[3],
      turnos: x[4],
      max_compra: x[5],
    }));
  }
  return out;
}
"""


# --------------------------------------------------------------------------
# Telegram
# --------------------------------------------------------------------------

def diagnostico_credenciales() -> bool:
    """Comprueba los secretos sin imprimir su contenido."""
    ok = True

    if not TG_TOKEN:
        print("[X] Falta el secret TELEGRAM_BOT_TOKEN (o esta vacio).")
        ok = False
    elif ":" not in TG_TOKEN or not TG_TOKEN.split(":")[0].isdigit():
        print(f"[X] TELEGRAM_BOT_TOKEN no tiene forma de token "
              f"({len(TG_TOKEN)} caracteres). Debe ser '123456789:AAH...'.")
        ok = False
    else:
        print(f"[v] TELEGRAM_BOT_TOKEN presente ({len(TG_TOKEN)} caracteres).")

    if not TG_CHAT:
        print("[X] Falta el secret TELEGRAM_CHAT_ID (o esta vacio).")
        ok = False
    elif not TG_CHAT.lstrip("-").isdigit():
        print(f"[X] TELEGRAM_CHAT_ID deberia ser solo numeros, y es "
              f"'{TG_CHAT[:4]}...'. Si empieza por @ o tiene espacios, corrigelo.")
        ok = False
    else:
        print(f"[v] TELEGRAM_CHAT_ID presente ({len(TG_CHAT)} digitos).")

    return ok


def telegram(texto: str) -> bool:
    """Envia el mensaje. Devuelve True si Telegram lo acepto."""
    if not diagnostico_credenciales():
        print("--- El mensaje que se habria enviado ---")
        print(texto)
        return False

    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    datos = urllib.parse.urlencode({
        "chat_id": TG_CHAT,
        "text": texto,
        "parse_mode": "HTML",
        "disable_web_page_preview": "false",
    }).encode()

    try:
        with urllib.request.urlopen(url, data=datos, timeout=30) as r:
            r.read()
        print("[ok] Telegram acepto el mensaje. Deberia estar en tu movil.")
        return True

    except urllib.error.HTTPError as e:
        # Telegram explica el motivo exacto en el cuerpo de la respuesta.
        try:
            cuerpo = json.loads(e.read().decode())
            motivo = cuerpo.get("description", "")
        except Exception:  # noqa: BLE001
            motivo = ""
        print(f"[X] Telegram rechazo el mensaje: HTTP {e.code} {motivo}",
              file=sys.stderr)

        pistas = {
            "chat not found":
                "El TELEGRAM_CHAT_ID no es correcto. Pide tu Id a @userinfobot.",
            "bot was blocked":
                "Has bloqueado a tu propio bot. Desbloquealo en Telegram.",
            "can't initiate conversation":
                "Abre el chat con TU bot en Telegram y pulsa Start (/start).",
            "unauthorized":
                "El TELEGRAM_BOT_TOKEN es incorrecto. Pideselo otra vez a @BotFather.",
        }
        for clave, pista in pistas.items():
            if clave in motivo.lower():
                print(f"    -> {pista}", file=sys.stderr)
                break
        else:
            print("    -> Revisa los dos secrets en Settings > Secrets and "
                  "variables > Actions.", file=sys.stderr)
        return False

    except Exception as e:  # noqa: BLE001
        print(f"[X] No se pudo contactar con Telegram: {type(e).__name__}: {e}",
              file=sys.stderr)
        return False


# --------------------------------------------------------------------------
# Scraping
# --------------------------------------------------------------------------

def leer_evento(page, ruta: str):
    """Devuelve el dict de disponibilidad de una pagina de evento."""
    page.goto(BASE + ruta, wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_function("typeof eventi !== 'undefined'", timeout=30_000)
    return page.evaluate(EXTRACT_JS)


def buscar_huecos():
    """Recorre los 4 eventos y devuelve (hallazgos, errores)."""
    hallazgos = []
    errores = []
    objetivo = {(f.year, f.month, f.day) for f in FECHAS_OBJETIVO}

    with sync_playwright() as p:
        navegador = p.chromium.launch(headless=True)
        ctx = navegador.new_context(
            locale="it-IT",
            timezone_id="Europe/Rome",
            viewport={"width": 1366, "height": 900},
        )
        page = ctx.new_page()

        for ev_id, (nombre, ruta) in EVENTOS.items():
            try:
                datos = leer_evento(page, ruta)
                if not datos or ev_id not in datos:
                    errores.append(f"{nombre}: la pagina cargo sin el calendario")
                    continue

                for fila in datos[ev_id]:
                    clave = (fila["y"], fila["m"], fila["d"])
                    if clave not in objetivo:
                        continue
                    try:
                        plazas = int(fila["plazas"])
                        max_compra = int(fila["max_compra"])
                    except (TypeError, ValueError):
                        continue
                    # plazas == -1 significa aforo sin limite declarado
                    if plazas == 0:
                        continue
                    if plazas != -1 and max_compra < MIN_PLAZAS:
                        continue
                    hallazgos.append({
                        "evento": nombre,
                        "fecha": f"{fila['d']:02d}/{fila['m']:02d}/{fila['y']}",
                        "plazas": plazas,
                        "max_compra": max_compra,
                        "url_evento": BASE + ruta,
                        "url_directa": (
                            f"{BASE}/index.php?nvpg[sell]&cmd=prices"
                            f"&pcode={fila['pcode']}&tcode={fila['tcode']}"
                        ),
                    })
            except Exception as e:  # noqa: BLE001
                errores.append(f"{nombre}: {type(e).__name__}: {e}")

            time.sleep(3)  # no atosigar la web

        ctx.close()
        navegador.close()

    return hallazgos, errores


# --------------------------------------------------------------------------
# Estado: no repetir el mismo aviso cada hora
# --------------------------------------------------------------------------

def firma(hallazgos) -> str:
    return "|".join(sorted(
        f"{h['evento']}@{h['fecha']}={h['plazas']}" for h in hallazgos
    ))


def estado_previo() -> str:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f).get("firma", "")
    except Exception:  # noqa: BLE001
        return ""


def guardar_estado(f: str) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as fh:
        json.dump({"firma": f, "ts": time.time()}, fh)


# --------------------------------------------------------------------------

def main() -> int:
    # Modo prueba: solo comprueba que Telegram te llega. No mira entradas.
    if os.environ.get("MODO_PRUEBA", "").lower() in ("true", "1", "yes"):
        print("Modo prueba: enviando un Telegram de comprobacion.")
        enviado = telegram(
            "✅ <b>Prueba del vigilante del Cenacolo</b>\n\n"
            "Si lees esto, el bot puede avisarte. Ya esta vigilando "
            "el 14-18 de octubre de 2026."
        )
        # Si el envio falla, el run sale en ROJO para que se note.
        return 0 if enviado else 1

    hallazgos, errores = buscar_huecos()

    for e in errores:
        print(f"[error] {e}", file=sys.stderr)

    if not hallazgos:
        print("Sin disponibilidad en el 14-18 de octubre de 2026.")
        guardar_estado("")
        # Si TODOS los eventos fallaron, salimos en error para que GitHub
        # te mande el aviso de workflow fallido.
        return 1 if len(errores) == len(EVENTOS) else 0

    nueva = firma(hallazgos)
    if nueva == estado_previo():
        print("Hay disponibilidad, pero ya te avise de esta misma. No repito.")
        return 0

    lineas = ["\U0001f6a8 <b>HAY ENTRADAS DEL CENACOLO</b>", ""]
    for h in hallazgos:
        plazas = "sin limite" if h["plazas"] == -1 else f"{h['plazas']} plazas"
        lineas.append(
            f"• <b>{h['fecha']}</b> - {h['evento']}\n"
            f"  {plazas} (max {h['max_compra']} por compra)\n"
            f"  <a href=\"{h['url_directa']}\">Comprar</a> | "
            f"<a href=\"{h['url_evento']}\">Calendario</a>"
        )
    lineas += [
        "",
        "Recuerda: 1 sola compra por ano natural, max 5 entradas,",
        "nominativas y con control de DNI. Corre.",
    ]
    telegram("\n".join(lineas))
    guardar_estado(nueva)
    return 0


if __name__ == "__main__":
    sys.exit(main())
