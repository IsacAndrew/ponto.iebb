"""
utils.py
---------
Funções auxiliares que não são "regra de negócio" pura, nem "modelo de
banco" -- são ferramentas que várias partes do sistema vão usar.

Por enquanto: cálculo de distância entre coordenadas (para o GPS) e
geração de código de autorização aleatório.
"""

from math import radians, sin, cos, sqrt, atan2


def calcular_distancia_metros(lat1, lng1, lat2, lng2):
    """
    Calcula a distância em metros entre dois pontos geográficos (latitude
    e longitude), usando a fórmula de Haversine.

    Essa fórmula existe porque a Terra é uma esfera (não um plano), então
    não dá para usar Pitágoras direto -- ela leva em conta a curvatura.

    Exemplo:
        distancia = calcular_distancia_metros(
            -23.6763196, -46.7626033,   # ponto 1 (escola)
            -23.6765000, -46.7628000    # ponto 2 (professor)
        )
        # distancia agora tem o resultado em metros
    """
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
    """
    Retorna (True/False, distancia_calculada).
    Facilita usar direto em um "if" nas rotas do Flask.
    """
    distancia = calcular_distancia_metros(lat_usuario, lng_usuario, lat_escola, lng_escola)
    return distancia <= raio_metros, distancia


def calcular_minutos_atraso(horario_esperado, horario_batido):
    """
    Recebe dois objetos datetime.time (ou datetime) e retorna quantos
    minutos de atraso houve. Se chegou no horário ou adiantado, retorna 0.
    """
    diferenca = horario_batido - horario_esperado
    minutos = diferenca.total_seconds() / 60
    return max(0, round(minutos))
