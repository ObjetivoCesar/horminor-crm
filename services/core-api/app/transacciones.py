"""Uso compartido de una conexión en operaciones con varias escrituras."""
from contextlib import asynccontextmanager


@asynccontextmanager
async def transaccion(pool_o_conexion):
    if not hasattr(pool_o_conexion, "acquire"):
        async with pool_o_conexion.transaction():
            yield pool_o_conexion
        return
    async with pool_o_conexion.acquire() as conn, conn.transaction():
        yield conn
