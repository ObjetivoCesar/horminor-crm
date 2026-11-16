"""Modelo del router Horminor (prototipo aislado).

Principio: el sistema propone y organiza; Julio confirma. Falta de datos para
investigar no es motivo para bloquear una tarea interna.

Sin base de datos, sin ejecución real de herramientas.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

ROLES = ("JULIO", "SECRETARIA", "JEFE_PLANTA", "POR_DEFINIR")
CANALES = ("INTERNO", "WHATSAPP", "LLAMADA", "NINGUNO")
AMBITOS = ("INTERNO", "EXTERNO", "MIXTO")
ESTADOS = ("PROPUESTO", "CONDICIONADO", "POR_DEFINIR")


class Encargo(BaseModel):
    id: str
    titulo: str
    que_hacer: str
    responsable: Literal["JULIO", "SECRETARIA", "JEFE_PLANTA", "POR_DEFINIR"] = (
        "POR_DEFINIR"
    )
    responsable_sugerido: bool = False
    destinatario: str | None = None
    canal: Literal["INTERNO", "WHATSAPP", "LLAMADA", "NINGUNO"] = "INTERNO"
    ambito: Literal["INTERNO", "EXTERNO", "MIXTO"] = "INTERNO"
    resultado_esperado: str | None = None
    plazo: str | None = None
    datos: dict[str, Any] = Field(default_factory=dict)
    condiciones: list[str] = Field(default_factory=list)
    por_investigar: list[str] = Field(default_factory=list)
    requiere_autorizacion: bool = False
    autorizado: bool = False
    preparar_comunicacion: bool = False
    estado: Literal["PROPUESTO", "CONDICIONADO", "POR_DEFINIR"] = "PROPUESTO"
    citas: list[str] = Field(default_factory=list)
    origen: Literal["DICTADO", "CITA_CLIENTE", "SUGERIDO"] = "DICTADO"

    def resumen(self) -> str:
        partes = [f"{self.id}: {self.titulo}"]
        partes.append(f"responsable {self.responsable}")
        if self.responsable_sugerido:
            partes.append("(sugerido)")
        if self.plazo:
            partes.append(f"plazo {self.plazo}")
        if self.condiciones:
            partes.append("condicionado")
        if self.por_investigar:
            partes.append("con datos por investigar")
        return " · ".join(partes)


class BorradorRouter(BaseModel):
    version: int = 1
    padre: int | None = None
    resumen: str = ""
    encargos: list[Encargo] = Field(default_factory=list)
    informacion_sin_encargo: list[str] = Field(default_factory=list)
    consultas: list[str] = Field(default_factory=list)
    constancias: list[str] = Field(default_factory=list)
    decisiones_julio: list[str] = Field(default_factory=list)
    preguntas: list[str] = Field(default_factory=list)
    notas: list[str] = Field(default_factory=list)
    datos_contexto: dict[str, Any] = Field(default_factory=dict)

    def cambio(self, cambios: list[str], *, padre: int) -> "BorradorRouter":
        return BorradorRouter(
            version=self.version + 1,
            padre=padre,
            resumen=self.resumen,
            encargos=[e.model_copy(deep=True) for e in self.encargos],
            informacion_sin_encargo=list(self.informacion_sin_encargo),
            consultas=list(self.consultas),
            constancias=list(self.constancias),
            decisiones_julio=list(self.decisiones_julio),
            preguntas=list(self.preguntas),
            notas=[*self.notas, *cambios],
            datos_contexto=dict(self.datos_contexto),
        )


class PlanTarea(BaseModel):
    encargo_id: str
    titulo: str
    responsable: str
    accion: Literal["CREAR_TAREA"] = "CREAR_TAREA"
    notificar: bool = True
    resultado_esperado: str | None = None
    plazo: str | None = None
    clave_idempotencia: str
    condiciones: list[str] = Field(default_factory=list)
    datos_por_investigar: list[str] = Field(default_factory=list)


class PlanComunicacion(BaseModel):
    encargo_id: str
    destinatario: str | None
    accion: Literal["PREPARAR", "PREPARAR_Y_ENVIAR"]
    motivo: str


class PlanOperacion(BaseModel):
    encargo_id: str
    operacion: str
    autorizada: bool
    motivo: str


class PlanConfirmacion(BaseModel):
    confirmados: list[str]
    tareas: list[PlanTarea] = Field(default_factory=list)
    comunicaciones: list[PlanComunicacion] = Field(default_factory=list)
    operaciones: list[PlanOperacion] = Field(default_factory=list)
    pendientes: list[str] = Field(default_factory=list)
    advertencias: list[str] = Field(default_factory=list)

    def resumen(self) -> str:
        partes = [f"{len(self.tareas)} tarea(s) a crear"]
        if self.comunicaciones:
            preparar = sum(1 for c in self.comunicaciones if c.accion == "PREPARAR")
            enviar = len(self.comunicaciones) - preparar
            if preparar:
                partes.append(f"{preparar} comunicación(es) a preparar")
            if enviar:
                partes.append(f"{enviar} a enviar")
        if self.operaciones:
            partes.append(f"{len(self.operaciones)} operación(es)")
        if self.pendientes:
            partes.append(f"{len(self.pendientes)} pendiente(s)")
        return "; ".join(partes) + "."
