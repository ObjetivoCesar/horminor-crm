"""Pruebas de idempotencia: mensaje_id vs intent_id.

No usa base de datos. Distingue:
- reintento técnico: mismo mensaje_id y mismo intent_id → una sola ejecución;
- mensaje repetido: mismo mensaje_id, otro intent_id → una sola ejecución;
- instrucción legítima repetida: otro mensaje_id y otro intent_id, aunque el
  texto sea idéntico → dos ejecuciones;
- inconsistencia: mismo intent_id con otro mensaje_id → error.

    python -m experiments.d_vs_dmas.idempotencia
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


class Inconsistencia(RuntimeError):
    pass


@dataclass
class Mensaje:
    mensaje_id: str
    intent_id: str
    texto: str


@dataclass
class Procesador:
    """Modelo mínimo de idempotencia en memoria."""

    ejecuciones: list[str] = field(default_factory=list)
    por_mensaje: dict[str, str] = field(default_factory=dict)
    por_intent: dict[str, str] = field(default_factory=dict)
    _candado: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def procesar(self, mensaje: Mensaje, *, demora: float = 0.02) -> dict:
        async with self._candado:
            if mensaje.intent_id in self.por_intent:
                previo = self.por_intent[mensaje.intent_id]
                if previo != mensaje.mensaje_id:
                    raise Inconsistencia(
                        f"intent {mensaje.intent_id} reutilizado para otro mensaje"
                    )
                return {"estado": "REINTENTO", "id": previo}

            if mensaje.mensaje_id in self.por_mensaje:
                previo = self.por_mensaje[mensaje.mensaje_id]
                self.por_intent[mensaje.intent_id] = mensaje.mensaje_id
                return {"estado": "DUPLICADO", "id": previo}

            self.por_mensaje[mensaje.mensaje_id] = mensaje.mensaje_id
            self.por_intent[mensaje.intent_id] = mensaje.mensaje_id

        # El trabajo real ocurre una sola vez, fuera del candado.
        await asyncio.sleep(demora)
        self.ejecuciones.append(mensaje.mensaje_id)
        return {"estado": "PROCESADO", "id": mensaje.mensaje_id}


async def main() -> None:
    resultados: list[tuple[str, bool, str]] = []

    # 1. Reintento técnico del mismo mensaje
    p = Procesador()
    a = Mensaje("wamid.1", "intent.1", "Que secretaría revise el despacho.")
    r1 = await p.procesar(a)
    r2 = await p.procesar(a)
    ok = r1["estado"] == "PROCESADO" and r2["estado"] == "REINTENTO" and len(p.ejecuciones) == 1
    resultados.append(("reintento técnico (mismo mensaje e intent)", ok, f"{r1} {r2}"))

    # 2. Mismo mensaje, otro intent (reenvío del cliente o doble clic)
    p = Procesador()
    r1 = await p.procesar(Mensaje("wamid.2", "intent.2a", "Que revisen el despacho."))
    r2 = await p.procesar(Mensaje("wamid.2", "intent.2b", "Que revisen el despacho."))
    ok = r1["estado"] == "PROCESADO" and r2["estado"] == "DUPLICADO" and len(p.ejecuciones) == 1
    resultados.append(("mismo mensaje, otro intent", ok, f"{r1} {r2}"))

    # 3. Instrucción legítima repetida: mismo texto, otro mensaje
    p = Procesador()
    r1 = await p.procesar(Mensaje("wamid.3", "intent.3", "Que revisen el despacho."))
    r2 = await p.procesar(Mensaje("wamid.4", "intent.4", "Que revisen el despacho."))
    ok = r1["estado"] == r2["estado"] == "PROCESADO" and len(p.ejecuciones) == 2
    resultados.append(("texto idéntico, mensaje distinto", ok, f"{r1} {r2}"))

    # 4. Mismo intent con otro mensaje: inconsistencia
    p = Procesador()
    await p.procesar(Mensaje("wamid.5", "intent.5", "Primera."))
    fallo = False
    try:
        await p.procesar(Mensaje("wamid.6", "intent.5", "Segunda."))
    except Inconsistencia:
        fallo = True
    resultados.append(("intent reutilizado", fallo, f"inconsistencia={fallo}"))

    # 5. Duplicados concurrentes del mismo mensaje
    p = Procesador()
    mensaje = Mensaje("wamid.7", "intent.7", "Concurrente.")
    respuestas = await asyncio.gather(
        *(p.procesar(mensaje) for _ in range(5))
    )
    estados = [r["estado"] for r in respuestas]
    ok = estados.count("PROCESADO") == 1 and len(p.ejecuciones) == 1
    resultados.append(("5 duplicados concurrentes", ok, str(estados)))

    # 6. Reintento tras timeout: mismo par, pasado el tiempo
    p = Procesador()
    await p.procesar(Mensaje("wamid.8", "intent.8", "Lento."))
    await asyncio.sleep(0.05)
    r = await p.procesar(Mensaje("wamid.8", "intent.8", "Lento."))
    ok = r["estado"] == "REINTENTO" and len(p.ejecuciones) == 1
    resultados.append(("reintento después de timeout", ok, str(r)))

    print()
    for nombre, ok, detalle in resultados:
        print(f"[{'OK' if ok else 'FALLA'}] {nombre}: {detalle}")
    total = len(resultados)
    aprobadas = sum(1 for _, ok, _ in resultados if ok)
    print(f"\n{aprobadas}/{total} pruebas de idempotencia")
    if aprobadas != total:
        raise SystemExit(1)


if __name__ == "__main__":
    asyncio.run(main())
