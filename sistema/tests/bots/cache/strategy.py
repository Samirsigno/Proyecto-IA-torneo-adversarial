"""Bot de prueba: reporta si numba usó la caché para el kernel de jugadas del motor."""

from motor import Estado, nucleo, reportar


def preparar(config):
    Estado.inicial().jugadas()


def jugar(estado, tiempo_restante):
    stats = nucleo.generar.stats
    reportar(aciertos=sum(stats.cache_hits.values()), fallos=sum(stats.cache_misses.values()))
    return estado.jugadas()[0]
