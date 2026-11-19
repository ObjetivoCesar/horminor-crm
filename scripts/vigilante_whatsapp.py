#!/usr/bin/env python3
"""Vigilante de WhatsApp para Horminor.

Detecta la sesion "zombie": la instancia figura abierta y los salientes salen,
pero no entran mensajes. Reinicia una vez con enfriamiento y deja evidencia.

Se ejecuta por cron en el host (no dentro del contenedor) porque necesita:
- la API de Evolution en localhost:8080,
- la base de Evolution (docker exec evolution-postgres),
- reiniciar la instancia por API.

Variables de entorno opcionales:
- VIGILANTE_WEBHOOK: URL que recibe {"texto": "..."} (Telegram/Slack/otro).
- VIGILANTE_ENTRANTE_MIN: minutos sin entrantes para alertar (default 90).
- VIGILANTE_REINICIO_MIN: enfriamiento entre reinicios (default 45).
- VIGILANTE_INSTANCIA: nombre de la instancia (default horminor).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

INSTANCIA = os.getenv("VIGILANTE_INSTANCIA", "horminor")
ENTRANTE_MIN = int(os.getenv("VIGILANTE_ENTRANTE_MIN", "90"))
REINICIO_MIN = int(os.getenv("VIGILANTE_REINICIO_MIN", "45"))
WEBHOOK = os.getenv("VIGILANTE_WEBHOOK", "").strip()
API = "http://localhost:8080"
ENTORNO = Path("/opt/horminor/.env")
ESTADO = Path("/opt/horminor/vigilante_status.json")
TZ = ZoneInfo("America/Guayaquil")


def ahora() -> datetime:
    return datetime.now(TZ)


def api_key() -> str:
    try:
        for linea in ENTORNO.read_text(encoding="utf-8", errors="ignore").splitlines():
            if linea.startswith("EVOLUTION_API_KEY="):
                return linea.split("=", 1)[1].strip()
    except OSError:
        pass
    return ""


def pedir(metodo: str, ruta: str, key: str) -> dict:
    req = urllib.request.Request(
        API + ruta, headers={"apikey": key}, method=metodo
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def ultimos() -> tuple[int | None, int | None]:
    consulta = (
        'SELECT max(CASE WHEN m.key->>\'fromMe\' = \'false\' '
        'THEN m."messageTimestamp"::bigint END), '
        'max(CASE WHEN m.key->>\'fromMe\' = \'true\' '
        'THEN m."messageTimestamp"::bigint END) '
        'FROM "Message" m JOIN "Instance" i ON i.id = m."instanceId" '
        f"WHERE i.name = '{INSTANCIA}';"
    )
    salida = subprocess.run(
        [
            "docker", "exec", "evolution-postgres",
            "psql", "-U", "evolution", "-d", "evolution",
            "-t", "-A", "-F", "|", "-c", consulta,
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if salida.returncode != 0:
        return None, None
    partes = (salida.stdout or "").strip().split("|")
    if len(partes) != 2:
        return None, None
    entrante = int(partes[0]) if partes[0].strip() else None
    saliente = int(partes[1]) if partes[1].strip() else None
    return entrante, saliente


def minutos_desde(epoch: int | None) -> int | None:
    if not epoch:
        return None
    return int((datetime.now(timezone.utc).timestamp() - epoch) / 60)


def en_horario(dt: datetime) -> bool:
    return dt.weekday() <= 5 and 7 <= dt.hour < 19


def avisar(texto: str) -> None:
    print(f"[{ahora().isoformat(timespec='seconds')}] {texto}", flush=True)
    if not WEBHOOK:
        return
    try:
        req = urllib.request.Request(
            WEBHOOK,
            data=json.dumps({"texto": texto}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=15)
    except Exception as exc:  # noqa: BLE001
        print(f"webhook fallo: {exc}", file=sys.stderr)


def leer_estado_previo() -> dict:
    try:
        return json.loads(ESTADO.read_text(encoding="utf-8"))
    except Exception:
        return {}


def main() -> int:
    key = api_key()
    if not key:
        avisar("Vigilante: falta EVOLUTION_API_KEY en /opt/horminor/.env")
        return 1

    previo = leer_estado_previo()
    entrante, saliente = ultimos()
    min_entrante = minutos_desde(entrante)
    min_saliente = minutos_desde(saliente)

    try:
        estado = pedir("GET", f"/instance/connectionState/{INSTANCIA}", key)
        conexion = str((estado.get("instance") or {}).get("state") or "")
    except Exception as exc:  # noqa: BLE001
        conexion = ""
        min_entrante = None
        avisar(f"Vigilante: no pude consultar la instancia: {exc}")

    ahora_dt = ahora()
    sospechoso = False
    motivo = ""

    if conexion and conexion != "open":
        sospechoso = True
        motivo = f"instancia en estado {conexion}"
    elif en_horario(ahora_dt) and min_entrante is not None:
        if min_entrante >= ENTRANTE_MIN and (min_saliente is not None):
            sospechoso = True
            motivo = f"{min_entrante} min sin entrantes (salientes hace {min_saliente} min)"

    reiniciado = False
    ultimo_reinicio = previo.get("ultimo_reinicio_epoch") or 0
    ultimo_aviso = previo.get("ultimo_aviso_epoch") or 0
    if sospechoso and conexion == "open":
        cooldown_ok = (
            datetime.now(timezone.utc).timestamp() - ultimo_reinicio
        ) > REINICIO_MIN * 60
        if cooldown_ok:
            try:
                pedir("POST", f"/instance/restart/{INSTANCIA}", key)
                reiniciado = True
                ultimo_reinicio = int(datetime.now(timezone.utc).timestamp())
                avisar(f"Vigilante: reinicie {INSTANCIA} porque {motivo}")
            except Exception as exc:  # noqa: BLE001
                avisar(f"Vigilante: no pude reiniciar {INSTANCIA}: {exc}")
        elif previo.get("motivo") != motivo or (
            datetime.now(timezone.utc).timestamp() - ultimo_aviso
        ) > 1800:
            avisar(f"Vigilante: SOSPECHOSO ({motivo}); reinicio reciente, no repito")
    elif sospechoso:
        # Cerrada a proposito o sesion perdida: no se reinicia sola, hace falta QR.
        if previo.get("motivo") != motivo or (
            datetime.now(timezone.utc).timestamp() - ultimo_aviso
        ) > 1800:
            avisar(f"Vigilante: {motivo}; requiere revincular con QR (no reinicio solo)")

    if sospechoso:
        ultimo_aviso = int(datetime.now(timezone.utc).timestamp())

    datos = {
        "consultado_en": ahora_dt.isoformat(timespec="seconds"),
        "instancia": INSTANCIA,
        "conexion": conexion,
        "ultimo_entrante": (
            datetime.fromtimestamp(entrante, tz=TZ).isoformat(timespec="seconds")
            if entrante else None
        ),
        "ultimo_saliente": (
            datetime.fromtimestamp(saliente, tz=TZ).isoformat(timespec="seconds")
            if saliente else None
        ),
        "minutos_sin_entrantes": min_entrante,
        "sospechoso": sospechoso,
        "motivo": motivo,
        "reiniciado": reiniciado,
        "ultimo_reinicio_epoch": ultimo_reinicio,
        "ultimo_aviso_epoch": ultimo_aviso,
    }
    ESTADO.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
