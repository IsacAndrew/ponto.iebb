from math import radians, sin, cos, sqrt, atan2

def calcular_distancia_metros(lat1, lng1, lat2, lng2):
    RAIO_DA_TERRA_METROS = 6371000

    # A fórmula trabalha com radianos, não com graus -- por isso convertemos.
    lat1_rad, lng1_rad, lat2_rad, lng2_rad = map(radians, [lat1, lng1, lat2, lng2])

    diferenca_lat = lat2_rad - lat1_rad
    diferenca_lng = lng2_rad - lng1_rad

    a = (
        sin(diferenca_lat / 2) ** 2
        + cos(lat1_rad) * cos(lat2_rad) * sin(diferenca_lng / 2) ** 2
    )
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    return RAIO_DA_TERRA_METROS * c


def esta_dentro_do_raio(lat_usuario, lng_usuario, lat_escola, lng_escola, raio_metros):
    distancia = calcular_distancia_metros(lat_usuario, lng_usuario, lat_escola, lng_escola)
    return distancia <= raio_metros, distancia


def calcular_minutos_atraso(horario_esperado, horario_batido):
    diferenca = horario_batido - horario_esperado
    minutos = diferenca.total_seconds() / 60
    return max(0, round(minutos))


def calcular_minutos_hora_extra(horario_esperado, horario_batido):
    diferenca = horario_batido - horario_esperado
    minutos = diferenca.total_seconds() / 60
    return max(0, round(minutos))


MAPA_CAMPO_HORARIO = {
    "entrada": "horario_entrada",
    "saida_almoco": "horario_saida_almoco",
    "volta_almoco": "horario_volta_almoco",
    "saida": "horario_saida",
}

def horario_esperado_do_usuario(usuario, tipo_batimento):
    nome_campo = MAPA_CAMPO_HORARIO.get(tipo_batimento)
    if not nome_campo:
        return None
    return getattr(usuario, nome_campo, None)
