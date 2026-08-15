from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class Usuario(db.Model):
    __tablename__ = "usuarios"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False)
    identificador = db.Column(db.String(30), unique=True, nullable=False)
    senha_hash = db.Column(db.String(255), nullable=False)
    senha_temporaria = db.Column(db.Boolean, default=True, nullable=False)
    cargo = db.Column(db.String(20), nullable=False, default="professor")
    ativo = db.Column(db.Boolean, default=True)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    # ------------------------------------------------------------
    # JORNADA INDIVIDUAL
    # ------------------------------------------------------------
    horario_entrada = db.Column(db.Time, nullable=True)
    horario_saida_almoco = db.Column(db.Time, nullable=True)
    horario_volta_almoco = db.Column(db.Time, nullable=True)
    horario_saida = db.Column(db.Time, nullable=True)
    dias_semana = db.Column(db.String(50), nullable=True, default="seg,ter,qua,qui,sex")
    series = db.Column(db.String(255), nullable=True)

    registros_ponto = db.relationship(
        "RegistroPonto",
        foreign_keys="RegistroPonto.usuario_id",
        backref="usuario",
        lazy=True,
    )

    def definir_senha(self, senha_texto_puro):
        self.senha_hash = generate_password_hash(senha_texto_puro)

    def verificar_senha(self, senha_texto_puro):
        return check_password_hash(self.senha_hash, senha_texto_puro)

    def eh_admin(self):
        """Administração e Suporte acessam o Painel Admin."""
        return self.cargo in ("administracao", "suporte")

    def dias_semana_lista(self):
        """Retorna os dias trabalhados como lista, ex: ['seg', 'qua', 'sex']."""
        if not self.dias_semana:
            return []
        return [d.strip() for d in self.dias_semana.split(",") if d.strip()]

    def series_lista(self):
        """Retorna as séries lecionadas como lista."""
        if not self.series:
            return []
        return [s.strip() for s in self.series.split(",") if s.strip()]

    def __repr__(self):
        return f"<Usuario {self.identificador} ({self.cargo})>"


class RegistroPonto(db.Model):
    __tablename__ = "registros_ponto"

    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False)
    tipo_batimento = db.Column(db.String(20), nullable=False)
    horario = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    distancia_metros = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(20), default="normal", nullable=False)
    atraso_minutos = db.Column(db.Integer, default=0)
    
    # ------------------------------------------------------------
    # HORA EXTRA
    # ------------------------------------------------------------
    hora_extra_minutos = db.Column(db.Integer, default=0)
    hora_extra_autorizada = db.Column(db.Boolean, default=False)
    # ------------------------------------------------------------
    # AUDITORIA (última edição)
    # ------------------------------------------------------------
    editado_por_id = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=True)
    editado_em = db.Column(db.DateTime, nullable=True)
    observacao_ajuste = db.Column(db.String(255), nullable=True)

    def __repr__(self):
        return f"<RegistroPonto {self.tipo_batimento} - usuario {self.usuario_id} - {self.horario}>"
