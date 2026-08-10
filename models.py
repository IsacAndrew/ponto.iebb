"""
models.py
----------
Aqui ficam as "tabelas" do banco de dados, só que escritas como
classes Python normais. Isso se chama ORM (Object-Relational Mapping):
você programa com objetos e o SQLAlchemy, por trás dos panos, converte
tudo isso em comandos SQL para o banco. Ou seja: você NUNCA precisa
escrever SQL na mão.

Exemplo de uso, em qualquer outro arquivo do sistema:

    professor = Usuario(nome="Edson", identificador="0012", tipo="professor")
    professor.definir_senha("senha123")
    db.session.add(professor)
    db.session.commit()

    encontrado = Usuario.query.filter_by(identificador="0012").first()
"""

from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# O "db" é o objeto que representa a conexão com o banco. Ele é criado
# aqui e depois "conectado" ao app Flask de verdade no arquivo principal
# (app.py), usando db.init_app(app).
db = SQLAlchemy()


class Usuario(db.Model):
    """
    Tabela única de login, usada tanto por professores quanto por
    administrativos (você, dona Sandra, Silvana, futuros funcionários).

    O campo `tipo` é o que decide o que a pessoa pode ver e fazer no
    sistema:
        - "professor": só acessa a tela de bater ponto.
        - "admin": acessa bater ponto + todos os menus administrativos.

    Repare que NÃO guardamos CPF aqui -- só o "identificador", que no
    caso do professor é o número de matrícula, e no caso do admin pode
    ser um nome de usuário simples.
    """

    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)

    # Matrícula (professor) ou login (admin). Tem que ser único porque é
    # usado para entrar no sistema.
    identificador = db.Column(db.String(30), unique=True, nullable=False)

    # A senha NUNCA é guardada em texto puro -- só o "hash" dela (uma
    # versão embaralhada, que não dá para reverter). Usamos os métodos
    # abaixo (definir_senha / verificar_senha) para isso.
    senha_hash = db.Column(db.String(255), nullable=False)

    # "professor" ou "admin"
    tipo = db.Column(db.String(20), nullable=False, default="professor")

    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # "Perdão" de atraso: quando True, o próximo ponto atrasado desse
    # usuário NÃO trava, mesmo passando da tolerância. É desativado
    # automaticamente assim que esse próximo ponto é batido (ver a
    # rota de registrar ponto em app.py).
    perdao_atraso_ativo = db.Column(db.Boolean, default=False)

    # Relacionamento: um usuário pode ter vários registros de ponto.
    # Isso permite fazer, por exemplo: usuario.registros_ponto (lista).
    #
    # Precisamos indicar explicitamente qual coluna usar (foreign_keys),
    # porque RegistroPonto tem DUAS colunas que apontam para "usuarios"
    # (usuario_id e ajustado_por_id) -- sem isso, o SQLAlchemy não sabe
    # qual das duas usar para este relacionamento.
    registros_ponto = db.relationship(
        "RegistroPonto",
        foreign_keys="RegistroPonto.usuario_id",
        backref="usuario",
        lazy=True,
    )

    def definir_senha(self, senha_texto_puro):
        """Recebe a senha digitada e guarda só o hash dela."""
        self.senha_hash = generate_password_hash(senha_texto_puro)

    def verificar_senha(self, senha_texto_puro):
        """Confere se a senha digitada bate com o hash guardado."""
        return check_password_hash(self.senha_hash, senha_texto_puro)

    def eh_admin(self):
        return self.tipo == "admin"

    def __repr__(self):
        return f"<Usuario {self.identificador} ({self.tipo})>"


class RegistroPonto(db.Model):
    """
    Cada linha aqui é UM batimento de ponto (entrada, saída pro almoço,
    volta do almoço, ou saída final).
    """

    __tablename__ = "registros_ponto"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)

    # Um dos 4 tipos: "entrada", "saida_almoco", "volta_almoco", "saida"
    tipo_batimento = db.Column(db.String(20), nullable=False)

    horario = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    # Localização enviada pelo celular na hora do batimento.
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    distancia_metros = db.Column(db.Float, nullable=True)  # distância calculada até a escola

    # "normal": batido dentro do horário e do raio, sem problema.
    # "pendente": atrasou mais que a tolerância e precisa de correção da direção.
    # "ajustado": já foi corrigido manualmente pela dona Sandra.
    status = db.Column(db.String(20), default="normal", nullable=False)

    atraso_minutos = db.Column(db.Integer, default=0)

    # Marca se esse batimento específico usou o "perdão" de atraso
    # (autorização prévia da direção, tipo no caso do professor que
    # avisou antes que ia chegar atrasado).
    perdao_utilizado = db.Column(db.Boolean, default=False)

    # Se o ponto foi ajustado manualmente, guardamos quem ajustou e uma
    # observação, para manter um pequeno histórico/auditoria.
    ajustado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    observacao_ajuste = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        return f"<RegistroPonto {self.tipo_batimento} - usuario {self.usuario_id} - {self.horario}>"
