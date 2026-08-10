"""
config.py
----------
Arquivo central de configurações do sistema de ponto.
Aqui ficam guardadas as informações que "moldam" o comportamento do
sistema, sem precisar mexer no banco de dados ou nas regras de negócio.

Se algum dia a escola mudar de endereço, ou você quiser ajustar o raio
de tolerância do GPS, é só mudar os valores aqui.
"""

import os


class Config:
    # ------------------------------------------------------------
    # CHAVE SECRETA DO FLASK
    # ------------------------------------------------------------
    # O Flask usa essa chave para proteger sessões de login (cookies
    # criptografados). Em produção, o ideal é pegar esse valor de uma
    # variável de ambiente (mais seguro), e não deixar escrito aqui.
    # Por enquanto, deixamos um valor padrão para você testar local.
    SECRET_KEY = os.environ.get("SECRET_KEY", "troque-essa-chave-antes-de-colocar-no-ar")

    # ------------------------------------------------------------
    # BANCO DE DADOS
    # ------------------------------------------------------------
    # No começo (desenvolvimento, testando no seu PC), vamos usar SQLite,
    # que é só um arquivo (ponto.db) -- não precisa instalar nada.
    # Quando for para a VPS de verdade, você troca essa URL pela do
    # PostgreSQL (o SQLAlchemy entende os dois do mesmo jeito).
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///ponto.db"
    )
    # Desliga um recurso do SQLAlchemy que fica "escutando" mudanças nos
    # objetos o tempo todo -- gasta memória à toa e não vamos usar.
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # ------------------------------------------------------------
    # LOCALIZAÇÃO DA ESCOLA (para validação por GPS)
    # ------------------------------------------------------------
    # Endereço: R. Vicenzo Catena, 100 - Vila Remo, São Paulo - SP, 05864-230
    #
    # IMPORTANTE: essas coordenadas foram obtidas por uma busca aproximada
    # da rua. O ideal é você confirmar o ponto exato abrindo o Google Maps,
    # clicando bem em cima do prédio da escola, e copiando a latitude e
    # longitude que aparecem lá (geralmente dá para ver clicando com o
    # botão direito no mapa). Depois é só substituir os valores abaixo.
    ESCOLA_LATITUDE = -23.6763196
    ESCOLA_LONGITUDE = -46.7626033

    # Raio de tolerância em METROS. O GPS de celular normalmente tem uma
    # margem de erro de 5 a 20 metros ao ar livre, e pode piorar bastante
    # (30-50m) dentro de prédios. Por isso usamos um raio mais folgado.
    RAIO_TOLERANCIA_METROS = 120

    # ------------------------------------------------------------
    # REGRA DE ATRASO
    # ------------------------------------------------------------
    # Depois de quantos minutos de atraso o ponto "trava" e precisa de
    # autorização manual da direção (não se aplica à saída final).
    TOLERANCIA_ATRASO_MINUTOS = 5
