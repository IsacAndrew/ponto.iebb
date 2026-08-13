import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "troque-essa-chave-antes-de-colocar-no-ar")
    _url_banco = os.environ.get("DATABASE_URL", "sqlite:///ponto.db")
    if _url_banco.startswith("postgres://"):
        _url_banco = _url_banco.replace("postgres://", "postgresql://", 1)
    SQLALCHEMY_DATABASE_URI = _url_banco
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    ESCOLA_LATITUDE = -23.6763196
    ESCOLA_LONGITUDE = -46.7626033
    RAIO_TOLERANCIA_METROS = 120
    TOLERANCIA_ATRASO_MINUTOS = 5

DIAS_SEMANA = [
    ("seg", "Segunda"),
    ("ter", "Terça"),
    ("qua", "Quarta"),
    ("qui", "Quinta"),
    ("sex", "Sexta"),
    ("sab", "Sábado"),
    ("dom", "Domingo"),
]

CARGOS_SEM_ACESSO_ADMIN = ["professor", "secretaria"]
CARGOS_COM_ACESSO_ADMIN = ["administracao", "suporte"]

CARGOS_ROTULOS = {
    "professor": "Professor",
    "secretaria": "Secretária",
    "administracao": "Administração",
    "suporte": "Suporte",
}

SERIES_DISPONIVEIS = [
    "Jardim", "Pré-Escola",
    "1ºA", "1ºB", "2ºA", "2ºB", "3ºA", "3ºB", "4ºA", "4ºB", "5ºA", "5ºB",
    "6ºA", "7ºA", "8ºA", "8ºB", "9ºA",
    "1ºEM", "2ºEM", "3ºEM",
]
