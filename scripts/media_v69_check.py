"""Verificacion de multimedia v6.9 (compresion + almacenamiento + indice).

Genera una imagen PNG, un WAV y un MP4 de prueba dentro del contenedor, los
sube por la API como si fueran del panel, comprueba que la imagen quede WebP,
que el video se recomprima y que `media_assets` guarde la ruta correcta.
Borra todo lo que crea y los archivos del sandbox al terminar.

Uso:
    docker compose run --rm --no-deps core-api python scripts/media_v69_check.py

Sale con codigo 1 si una verificacion falla. No deja datos ni archivos.
"""

from __future__ import annotations

import asyncio
import io
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import _path  # noqa: F401

import asyncpg
import httpx
from PIL import Image

from app.services import media as media_svc
from app.settings import get_settings

BASE = "http://orminorth-core-api:8000"
TAG = "mediav69prueba"

_fallos = 0


def check(condicion: bool, mensaje: str, detalle: str = "") -> None:
    global _fallos
    if condicion:
        print(f"  [OK] {mensaje}")
        return
    _fallos += 1
    print(f"  [FALLO] {mensaje}" + (f" :: {detalle}" if detalle else ""))


def _generar_archivos(carpeta: Path) -> dict[str, Path]:
    imagen = carpeta / "foto.png"
    Image.new("RGB", (3200, 1800), (210, 120, 20)).save(imagen, "PNG")

    audio = carpeta / "nota.wav"
    with wave.open(str(audio), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8000)
        wav.writeframes(b"\x00\x00" * 8000)

    video = carpeta / "clip.mp4"
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        subprocess.run(
            [
                ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=24",
                "-t", "2", "-pix_fmt", "yuv420p", str(video),
            ],
            check=True,
            capture_output=True,
        )
    return {"foto": imagen, "audio": audio, "video": video}


async def main() -> int:
    settings = get_settings()
    pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=2)
    cliente_id = None
    conversacion_previa = None
    conversacion_id = None
    media_ids: list[str] = []
    mensajes_ids: list[str] = []
    rutas: list[str] = []
    try:
        async with httpx.AsyncClient(base_url=BASE, timeout=120) as http:
            respuesta = await http.get("/api/v1/secretaria/clientes")
            respuesta.raise_for_status()
            clientes = respuesta.json().get("clientes") or []
            if not clientes:
                print("  [FALLO] no hay clientes para la prueba")
                return 1
            cliente_id = clientes[0]["cliente_id"]
            print(f"Cliente de prueba: {clientes[0]['nombre']} ({cliente_id})")
            conversacion_previa = await pool.fetchval(
                "SELECT id::text FROM chat_conversaciones WHERE cliente_id=$1::uuid AND canal='WHATSAPP'",
                cliente_id,
            )

            with tempfile.TemporaryDirectory(prefix="media-check-") as tmp:
                archivos = _generar_archivos(Path(tmp))
                if not archivos["video"].is_file():
                    print("  [FALLO] no se pudo generar el MP4 de prueba (ffmpeg)")
                    return 1
                casos = [
                    ("foto", "image/png", "IMAGEN"),
                    ("audio", "audio/wav", "AUDIO"),
                    ("video", "video/mp4", "VIDEO"),
                ]
                for clave, mime, tipo_esperado in casos:
                    ruta = archivos[clave]
                    with ruta.open("rb") as fh:
                        respuesta = await http.post(
                            f"/api/v1/clients/{cliente_id}/chat/adjuntos",
                            files={"archivo": (ruta.name, fh, mime)},
                            data={"canal": "WHATSAPP"},
                        )
                    check(
                        respuesta.status_code == 200,
                        f"subida {clave} responde 200",
                        respuesta.text[:240],
                    )
                    if respuesta.status_code != 200:
                        continue
                    cuerpo = respuesta.json()
                    mensaje = cuerpo["mensaje"]
                    adjunto = (mensaje.get("adjuntos") or [{}])[0]
                    mensajes_ids.append(mensaje["id"])
                    media_ids.append(adjunto.get("media_id"))
                    conversacion_id = cuerpo.get("conversacion_id") or conversacion_id
                    check(adjunto.get("tipo") == tipo_esperado, f"{clave} se clasifica como {tipo_esperado}", str(adjunto.get("tipo")))
                    check(bool(adjunto.get("url")), f"{clave} tiene URL de descarga", str(adjunto.get("url")))
                    if adjunto.get("url"):
                        descarga = await http.get(adjunto["url"])
                        check(descarga.status_code == 200, f"{clave} se puede descargar", str(descarga.status_code))

            filas = await pool.fetch(
                "SELECT id::text, tipo, backend, storage_path, mime_final, bytes_final, "
                "ancho, alto, duracion_seg, sha256 FROM media_assets WHERE id = ANY($1::uuid[])",
                media_ids,
            )
            por_tipo = {f["tipo"]: f for f in filas}
            check(len(filas) == 3, "media_assets registra los 3 archivos", str(len(filas)))
            check(all(f["backend"] == "SANDBOX" for f in filas), "sin Bunny configurado se usa el sandbox")
            check(
                all(f["storage_path"].startswith("clientes/") for f in filas),
                "las rutas viven bajo clientes/",
            )
            foto = por_tipo.get("IMAGEN")
            check(foto is not None, "la imagen quedo indexada")
            if foto:
                check(foto["mime_final"] == "image/webp", "la imagen se convirtio a WebP", foto["mime_final"])
                check(max(int(foto["ancho"] or 0), int(foto["alto"] or 0)) <= 1920, "la imagen se redujo a 1920 px")
                rutas.append(foto["storage_path"])
            audio = por_tipo.get("AUDIO")
            check(audio is not None, "el audio quedo indexado")
            if audio:
                rutas.append(audio["storage_path"])
            video = por_tipo.get("VIDEO")
            check(video is not None, "el video quedo indexado")
            if video:
                check(video["mime_final"] == "video/mp4", "el video quedo en MP4", video["mime_final"])
                check(float(video["duracion_seg"] or 0) <= 180, "el video respeta el maximo de 180 s")
                rutas.append(video["storage_path"])
            check(
                all(f["sha256"] and len(f["sha256"]) == 64 for f in filas),
                "cada archivo tiene hash SHA-256",
            )

        return 0
    finally:
        if media_ids:
            await pool.execute("DELETE FROM media_assets WHERE id = ANY($1::uuid[])", media_ids)
        if mensajes_ids:
            await pool.execute("DELETE FROM chat_mensajes WHERE id = ANY($1::uuid[])", mensajes_ids)
        if conversacion_id and conversacion_previa is None:
            await pool.execute(
                "DELETE FROM chat_conversaciones WHERE id=$1::uuid AND NOT EXISTS ("
                "SELECT 1 FROM chat_mensajes WHERE conversacion_id=$1::uuid)",
                conversacion_id,
            )
        for ruta in rutas:
            try:
                media_svc.ruta_sandbox(settings.media_dir, ruta).unlink(missing_ok=True)
            except Exception:
                pass
        restantes = await pool.fetchval("SELECT count(*) FROM media_assets")
        print(f"Limpieza: media_assets restantes = {restantes}")
        await pool.close()


if __name__ == "__main__":
    resultado = asyncio.run(main())
    print("MEDIA V6.9: OK" if resultado == 0 and _fallos == 0 else "MEDIA V6.9: FALLO")
    sys.exit(0 if resultado == 0 and _fallos == 0 else 1)
