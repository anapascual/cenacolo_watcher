# Vigilante de entradas — Cenacolo Vinciano

Avisa por Telegram en cuanto se libere una entrada para el **14–18 de octubre de 2026**.
Corre en GitHub Actions, así que funciona con tu ordenador apagado.

No compra nada, no rellena formularios, no toca captchas ni proxies. Carga una
página pública una vez por hora y lee un número.

---

## Qué mira exactamente

El calendario de Vivaticket no consulta al servidor cuando cambias de mes: la
disponibilidad de los 93 días de septiembre a diciembre viene entera en el HTML,
en un array JS `eventi[<id>]`. Cada fila es:

```
[tcode, pcode, fecha, plazas_libres, n_turnos, max_por_compra]
```

El script lee ese array en los cuatro eventos del museo y comprueba tus cinco días:

| Evento | ID |
|---|---|
| Entrada normal (15 €) | `151991` |
| Visita guiada en italiano | `238362` |
| Visita guiada en inglés | `238363` |
| Visita-laboratorio (ITA/ENG) | `238367` |

Salta el aviso cuando `plazas_libres > 0` **y** `max_por_compra >= 2`.

---

## Puesta en marcha (10 minutos)

### 1. Crear el bot de Telegram

1. Abre Telegram y busca **@BotFather**.
2. Manda `/newbot`. Te pide un nombre y un usuario que acabe en `bot`.
3. Te devuelve un token tipo `8123456789:AAH...`. **Ese es tu `TELEGRAM_BOT_TOKEN`.**
4. Busca **@userinfobot**, mándale cualquier cosa y te contesta con tu `Id`.
   **Ese número es tu `TELEGRAM_CHAT_ID`.**
5. Importante: abre un chat con **tu** bot y dale a *Start*. Si no, no puede escribirte.

### 2. Crear el repo

Crea un repositorio **privado** en GitHub y sube estos tres archivos tal cual:

```
check_cenacolo.py
README.md
.github/workflows/cenacolo.yml
```

### 3. Guardar los secretos

En el repo: **Settings → Secrets and variables → Actions → New repository secret**.
Crea dos:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Van cifrados y no aparecen en los logs. Nadie más los ve.

### 4. Probar

**Actions → Vigilante Cenacolo → Run workflow**.

Mira el log del paso *Comprobar disponibilidad*:

- `Sin disponibilidad en el 14-18 de octubre de 2026.` → **funciona**. Ya está vigilando.
- Errores de timeout en los cuatro eventos → **Imperva está bloqueando a GitHub**.
  Entonces esta vía no sirve; no intentes esquivarlo con proxies.

Para comprobar que Telegram va bien, baja `MIN_PLAZAS` a `1` y cambia temporalmente
`FECHAS_OBJETIVO` a una fecha de diciembre con hueco (las guiadas en italiano tienen);
te llegará el mensaje. Luego lo dejas como estaba.

---

## Cuándo comprueba

- Cada hora en punto.
- Los miércoles, ráfaga entre las 11:50 y las 12:20 hora de Madrid, que es cuando
  el museo suelta las entradas extra de la semana siguiente.

**Los cron de GitHub Actions se retrasan.** En horas de carga pueden tardar de 5 a
15 minutos, y no hay forma de evitarlo en el plan gratuito. Para los miércoles
críticos —**30 de septiembre, 7 y 14 de octubre**— ponte tú también delante a las
12:00. El bot es la red de seguridad, no el plan principal.

---

## Cuando consigas la entrada

Desactiva el workflow: **Actions → Vigilante Cenacolo → ⋯ → Disable workflow**.
Si no, te sigue avisando.

---

## Reglas del museo que conviene no olvidar

- **1 sola compra por año natural**, máximo 5 entradas. No puedes reservar "por si acaso".
- Entradas **nominativas**, con control de DNI en taquilla.
- **Ni cambios ni reembolsos** una vez comprada.
- Hay que estar en taquilla **30 minutos antes** o pierdes la entrada.
- El museo cierra los **lunes** (por eso el 19 no está en la lista).
