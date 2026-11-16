"""Prueba de codificación del arnés (UTF-8 de punta a punta).

No llama al modelo: comprueba la cadena fuente → payload → archivo.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import httpx

TEXTO = "Que secretaría revise el despacho de mañana; ¿falta algún viaje? Sí, José."


def _payload() -> dict:
    return {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": "Responde en español."},
            {"role": "user", "content": TEXTO},
        ],
        "temperature": 0,
    }


def main() -> None:
    print("fuente:", repr(TEXTO))
    assert "secretaría" in TEXTO and "mañana" in TEXTO
    assert "¿" in TEXTO and "José" in TEXTO

    peticion = httpx.Request(
        "POST", "https://api.deepseek.com/chat/completions", json=_payload()
    )
    crudo = peticion.content
    decodificado = crudo.decode("utf-8")
    print("payload bytes:", len(crudo))
    assert "secretaría" in decodificado
    assert "mañana" in decodificado
    assert "¿falta" in decodificado
    assert "José" in decodificado
    assert "Ã" not in decodificado

    # Recepción: una respuesta JSON con acentos se decodifica igual.
    respuesta = json.dumps(
        {"choices": [{"message": {"content": "{\"nota\":\"mañana y secretaría\"}"}}]},
        ensure_ascii=False,
    ).encode("utf-8")
    leido = json.loads(respuesta)["choices"][0]["message"]["content"]
    assert "mañana" in leido and "secretaría" in leido

    # Serialización de evidencia: UTF-8 sin BOM, ida y vuelta.
    destino = Path(__file__).resolve().parent / "runs" / "_prueba_encoding.json.txt"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(json.dumps({"dictado": TEXTO}, ensure_ascii=False), encoding="utf-8")
    vuelta = json.loads(destino.read_text(encoding="utf-8"))["dictado"]
    assert vuelta == TEXTO
    assert not destino.read_bytes().startswith(b"\xef\xbb\xbf")
    destino.unlink()

    print("OK: fuente, payload, recepción y archivo conservan tildes, ñ y ¿")


if __name__ == "__main__":
    main()
