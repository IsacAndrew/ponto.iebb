import os
from datetime import datetime, time as dt_time
from flask import Flask, render_template, request, redirect, url_for, session, flash
from functools import wraps

from config import Config, DIAS_SEMANA, CARGOS_SEM_ACESSO_ADMIN, CARGOS_COM_ACESSO_ADMIN, CARGOS_ROTULOS, SERIES_DISPONIVEIS
from models import db, Usuario, RegistroPonto
from utils import esta_dentro_do_raio, calcular_minutos_atraso, calcular_minutos_hora_extra, horario_esperado_do_usuario, agora_brasil

SENHA_TEMPORARIA_PADRAO = "102030"


def criar_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)

    with app.app_context():
        db.create_all()
        criar_admin_inicial_se_necessario()

    return app


def criar_admin_inicial_se_necessario():
    """
    No plano gratuito do Render não tem Shell. O sistema cria o primeiro
    usuário de Suporte sozinho, lendo variáveis de ambiente (ADMIN_NOME,
    ADMIN_LOGIN, ADMIN_SENHA), se ele ainda não existir.
    """
    nome = os.environ.get("ADMIN_NOME")
    login = os.environ.get("ADMIN_LOGIN")
    senha = os.environ.get("ADMIN_SENHA")

    if not (nome and login and senha):
        return

    ja_existe = Usuario.query.filter_by(identificador=login).first()
    if ja_existe:
        return

    novo_admin = Usuario(nome=nome, identificador=login, cargo="suporte", ativo=True, senha_temporaria=False)
    novo_admin.definir_senha(senha)
    db.session.add(novo_admin)
    db.session.commit()


app = criar_app()

ORDEM_BATIDAS = ["entrada", "saida_almoco", "volta_almoco", "saida"]
ROTULOS_BOTAO = {
    "entrada": "Entrada",
    "saida_almoco": "Almoço",
    "volta_almoco": "Retorno do Almoço",
    "saida": "Saída",
}


def calcular_proxima_batida(usuario_id):
    hoje = agora_brasil().date()
    inicio_do_dia = datetime.combine(hoje, dt_time.min)
    fim_do_dia = datetime.combine(hoje, dt_time.max)

    quantidade_hoje = RegistroPonto.query.filter(
        RegistroPonto.usuario_id == usuario_id,
        RegistroPonto.horario >= inicio_do_dia,
        RegistroPonto.horario <= fim_do_dia,
    ).count()

    if quantidade_hoje >= len(ORDEM_BATIDAS):
        return None, quantidade_hoje

    return ORDEM_BATIDAS[quantidade_hoje], quantidade_hoje


def login_obrigatorio(funcao):
    @wraps(funcao)
    def rota_protegida(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Você precisa entrar no sistema primeiro.")
            return redirect(url_for("login"))

        usuario = Usuario.query.get(session["usuario_id"])
        if usuario and usuario.senha_temporaria and funcao.__name__ != "trocar_senha":
            return redirect(url_for("trocar_senha"))

        return funcao(*args, **kwargs)

    return rota_protegida


def admin_obrigatorio(funcao):
    @wraps(funcao)
    def rota_protegida(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect(url_for("login"))
        usuario = Usuario.query.get(session["usuario_id"])
        if not usuario or not usuario.eh_admin():
            flash("Você não tem permissão para acessar essa área.")
            return redirect(url_for("bater_ponto"))
        if usuario.senha_temporaria:
            return redirect(url_for("trocar_senha"))
        return funcao(*args, **kwargs)

    return rota_protegida


@app.route("/")
def raiz():
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identificador = request.form.get("identificador", "").strip()
        senha = request.form.get("senha", "")

        usuario = Usuario.query.filter_by(identificador=identificador).first()

        if usuario and usuario.verificar_senha(senha) and usuario.ativo:
            session["usuario_id"] = usuario.id
            session["cargo_usuario"] = usuario.cargo
            return redirect(url_for("bater_ponto"))

        flash("Matrícula/login ou senha incorretos.")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/trocar-senha", methods=["GET", "POST"])
@login_obrigatorio
def trocar_senha():
    usuario = Usuario.query.get(session["usuario_id"])

    if request.method == "POST":
        nova_senha = request.form.get("senha", "")
        confirmar_senha = request.form.get("confirmar_senha", "")

        if len(nova_senha) < 4:
            flash("A nova senha precisa ter pelo menos 4 caracteres.")
            return redirect(url_for("trocar_senha"))
        if nova_senha != confirmar_senha:
            flash("As senhas não coincidem.")
            return redirect(url_for("trocar_senha"))
        if nova_senha == SENHA_TEMPORARIA_PADRAO:
            flash("Escolha uma senha diferente da temporária.")
            return redirect(url_for("trocar_senha"))

        usuario.definir_senha(nova_senha)
        usuario.senha_temporaria = False
        db.session.commit()

        flash("Senha atualizada com sucesso.")
        return redirect(url_for("bater_ponto"))

    return render_template("trocar_senha.html", usuario=usuario)


@app.route("/ponto", methods=["GET"])
@login_obrigatorio
def bater_ponto():
    usuario = Usuario.query.get(session["usuario_id"])
    proximo_tipo, batidas_hoje = calcular_proxima_batida(usuario.id)

    return render_template(
        "bater_ponto.html",
        usuario=usuario,
        escola_latitude=Config.ESCOLA_LATITUDE,
        escola_longitude=Config.ESCOLA_LONGITUDE,
        raio_tolerancia_metros=Config.RAIO_TOLERANCIA_METROS,
        proximo_tipo=proximo_tipo,
        proximo_rotulo=ROTULOS_BOTAO.get(proximo_tipo, "Até o próximo dia"),
        batidas_hoje=batidas_hoje,
    )


@app.route("/ponto/registrar", methods=["POST"])
@login_obrigatorio
def registrar_ponto():
    usuario = Usuario.query.get(session["usuario_id"])

    tipo_batimento, batidas_hoje = calcular_proxima_batida(usuario.id)
    latitude = request.form.get("latitude", type=float)
    longitude = request.form.get("longitude", type=float)

    if tipo_batimento is None:
        return {"status": "erro", "mensagem": "Você já bateu todos os pontos de hoje."}, 400

    agora = agora_brasil()

    if latitude is None or longitude is None:
        return {"status": "sem_localizacao", "mensagem": "Ative a localização do seu celular para bater o ponto."}, 400

    dentro_do_raio, distancia = esta_dentro_do_raio(
        latitude, longitude,
        Config.ESCOLA_LATITUDE, Config.ESCOLA_LONGITUDE,
        Config.RAIO_TOLERANCIA_METROS,
    )

    if not dentro_do_raio:
        return {"status": "fora_do_raio", "distancia": distancia}

    minutos_atraso = 0
    minutos_hora_extra = 0
    status = "normal"

    horario_esperado = horario_esperado_do_usuario(usuario, tipo_batimento)

    if horario_esperado and tipo_batimento != "saida":
        horario_esperado_hoje = datetime.combine(agora.date(), horario_esperado)
        minutos_atraso = calcular_minutos_atraso(horario_esperado_hoje, agora)
        if minutos_atraso > Config.TOLERANCIA_ATRASO_MINUTOS:
            status = "pendente"

    if horario_esperado and tipo_batimento == "saida":
        horario_esperado_hoje = datetime.combine(agora.date(), horario_esperado)
        minutos_hora_extra = calcular_minutos_hora_extra(horario_esperado_hoje, agora)

    novo_registro = RegistroPonto(
        usuario_id=usuario.id,
        tipo_batimento=tipo_batimento,
        horario=agora,
        latitude=latitude,
        longitude=longitude,
        distancia_metros=distancia,
        status=status,
        atraso_minutos=minutos_atraso,
        hora_extra_minutos=minutos_hora_extra,
        hora_extra_autorizada=False,
    )
    db.session.add(novo_registro)
    db.session.commit()

    proximo_tipo, batidas_hoje = calcular_proxima_batida(usuario.id)
    resposta_extra = {
        "proximo_tipo": proximo_tipo,
        "proximo_rotulo": ROTULOS_BOTAO.get(proximo_tipo, "Até o próximo dia"),
        "dia_completo": proximo_tipo is None,
    }

    if status == "pendente":
        return {
            "status": "pendente",
            "mensagem": "Ponto registrado, mas você está atrasado. Procure a direção para regularizar.",
            **resposta_extra,
        }

    return {"status": "ok", "mensagem": "Ponto registrado com sucesso!", **resposta_extra}


# ------------------------------------------------------------------
# PAINEL ADMIN - HORÁRIOS
# ------------------------------------------------------------------
@app.route("/admin")
@admin_obrigatorio
def admin_index():
    return redirect(url_for("admin_horarios"))


@app.route("/admin/horarios")
@admin_obrigatorio
def admin_horarios():
    usuario = Usuario.query.get(session["usuario_id"])

    filtro_nome = request.args.get("nome", "").strip()
    filtro_data_inicio = request.args.get("data_inicio", "").strip()
    filtro_data_fim = request.args.get("data_fim", "").strip()

    consulta = RegistroPonto.query.join(
        Usuario, RegistroPonto.usuario_id == Usuario.id
    ).order_by(RegistroPonto.horario.desc())

    if filtro_nome:
        consulta = consulta.filter(Usuario.nome.ilike(f"%{filtro_nome}%"))
    if filtro_data_inicio:
        consulta = consulta.filter(
            RegistroPonto.horario >= datetime.strptime(filtro_data_inicio, "%Y-%m-%d")
        )
    if filtro_data_fim:
        data_fim_completa = datetime.strptime(filtro_data_fim, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        consulta = consulta.filter(RegistroPonto.horario <= data_fim_completa)

    registros = consulta.limit(500).all()

    agrupado = {}
    for registro in registros:
        data_exibicao = registro.horario.strftime("%d/%m/%Y")
        data_url = registro.horario.strftime("%d-%m-%Y")
        chave = (registro.usuario_id, data_exibicao)

        if registro.editado_por_id:
            editor = Usuario.query.get(registro.editado_por_id)
            registro.nome_editor = editor.nome if editor else None
        else:
            registro.nome_editor = None

        if chave not in agrupado:
            agrupado[chave] = {
                "usuario_id": registro.usuario_id,
                "nome_professor": registro.usuario.nome,
                "data": data_exibicao,
                "data_url": data_url,
                "batimentos": {},
            }
        agrupado[chave]["batimentos"][registro.tipo_batimento] = registro

    linhas = sorted(agrupado.values(), key=lambda linha: linha["data"], reverse=True)

    return render_template(
        "painel_horarios.html",
        usuario=usuario,
        linhas=linhas,
        filtro_nome=filtro_nome,
        filtro_data_inicio=filtro_data_inicio,
        filtro_data_fim=filtro_data_fim,
    )


@app.route("/admin/horarios/editar/<int:usuario_id>/<data>", methods=["GET", "POST"])
@admin_obrigatorio
def admin_editar_ponto(usuario_id, data):
    """
    Corrige os horários batidos por alguém num dia. Permite trocar o
    horário, trocar a DATA (move os registros para outro dia), excluir
    um batimento específico, e autorizar a hora extra da saída.
    """
    usuario_admin = Usuario.query.get(session["usuario_id"])
    pessoa = Usuario.query.get_or_404(usuario_id)

    data_convertida = datetime.strptime(data, "%d-%m-%Y").date()
    data_exibicao = data_convertida.strftime("%d/%m/%Y")
    inicio_do_dia = datetime.combine(data_convertida, dt_time.min)
    fim_do_dia = datetime.combine(data_convertida, dt_time.max)

    registros_do_dia = RegistroPonto.query.filter(
        RegistroPonto.usuario_id == usuario_id,
        RegistroPonto.horario >= inicio_do_dia,
        RegistroPonto.horario <= fim_do_dia,
    ).all()
    registros_por_tipo = {r.tipo_batimento: r for r in registros_do_dia}

    if request.method == "POST":
        nova_data_texto = request.form.get("nova_data", "").strip()
        data_alvo = datetime.strptime(nova_data_texto, "%Y-%m-%d").date() if nova_data_texto else data_convertida

        for tipo in ORDEM_BATIDAS:
            registro_existente = registros_por_tipo.get(tipo)

            if request.form.get(f"excluir_{tipo}") == "on":
                if registro_existente:
                    db.session.delete(registro_existente)
                continue

            novo_horario_texto = request.form.get(f"horario_{tipo}", "").strip()
            if not novo_horario_texto:
                continue

            hora, minuto = map(int, novo_horario_texto.split(":"))
            novo_datetime = datetime.combine(data_alvo, dt_time(hora, minuto))

            if registro_existente:
                registro_existente.horario = novo_datetime
                registro_existente.status = "ajustado"
            else:
                registro_existente = RegistroPonto(
                    usuario_id=usuario_id,
                    tipo_batimento=tipo,
                    horario=novo_datetime,
                    status="ajustado",
                )
                db.session.add(registro_existente)

            if tipo == "saida":
                registro_existente.hora_extra_autorizada = request.form.get("autorizar_hora_extra") == "on"

            registro_existente.editado_por_id = usuario_admin.id
            registro_existente.editado_em = agora_brasil()
            registro_existente.observacao_ajuste = request.form.get("observacao", "").strip()

        db.session.commit()
        flash(f"Horários de {pessoa.nome} atualizados.")
        return redirect(url_for("admin_horarios"))

    from flask import render_template_string

    template_edicao = """
    {% extends "base_admin.html" %}
    {% block titulo %}Editar Ponto{% endblock %}
    {% block conteudo %}
        <h2>Editar horários - {{ pessoa.nome }} ({{ data_exibicao }})</h2>
        <form method="POST" style="background:white; padding:20px; border-radius:12px; max-width:420px;">
            <label style="display:block; margin-bottom:4px; font-size:13px;">Data</label>
            <input type="date" name="nova_data" value="{{ data_convertida }}"
                   style="width:100%; padding:10px; margin-bottom:16px; border:1px solid #d1d5db; border-radius:8px;">

            {% for tipo, rotulo in [("entrada", "Entrada"), ("saida_almoco", "Saída Almoço"),
                                     ("volta_almoco", "Volta Almoço"), ("saida", "Saída")] %}
                <label style="display:block; margin-bottom:4px; font-size:13px;">{{ rotulo }}</label>
                <div style="display:flex; gap:10px; align-items:center; margin-bottom:6px;">
                    <input type="time" name="horario_{{ tipo }}"
                           value="{{ registros_por_tipo[tipo].horario.strftime('%H:%M') if tipo in registros_por_tipo else '' }}"
                           style="flex:1; padding:10px; border:1px solid #d1d5db; border-radius:8px;">
                    {% if tipo in registros_por_tipo %}
                    <label style="font-size:12px; color:#dc2626; display:flex; align-items:center; gap:4px;">
                        <input type="checkbox" name="excluir_{{ tipo }}"> Excluir
                    </label>
                    {% endif %}
                </div>
                {% if tipo == "saida" %}
                <label style="font-size:13px; display:flex; align-items:center; gap:6px; margin-bottom:14px;">
                    <input type="checkbox" name="autorizar_hora_extra"
                           {{ "checked" if registros_por_tipo.get("saida") and registros_por_tipo["saida"].hora_extra_autorizada else "" }}>
                    Autorizar hora extra dessa saída
                </label>
                {% else %}
                <div style="margin-bottom:8px;"></div>
                {% endif %}
            {% endfor %}

            <label style="display:block; margin-bottom:4px; font-size:13px;">Observação (opcional)</label>
            <input type="text" name="observacao" placeholder="Ex: esqueceu de bater, corrigido manualmente"
                   style="width:100%; padding:10px; margin-bottom:16px; border:1px solid #d1d5db; border-radius:8px;">

            <button type="submit" style="width:100%; padding:12px; background:#2563eb; color:white; border:none; border-radius:8px; cursor:pointer; font-weight:bold;">
                Salvar
            </button>
        </form>
    {% endblock %}
    """
    return render_template_string(
        template_edicao,
        usuario=usuario_admin,
        pessoa=pessoa,
        data_exibicao=data_exibicao,
        data_convertida=data_convertida,
        registros_por_tipo=registros_por_tipo,
    )


# ------------------------------------------------------------------
# PAINEL ADMIN - PROFESSORES / SECRETÁRIA
# ------------------------------------------------------------------
@app.route("/admin/professores")
@admin_obrigatorio
def admin_professores():
    usuario = Usuario.query.get(session["usuario_id"])
    professores = Usuario.query.filter(
        Usuario.cargo.in_(CARGOS_SEM_ACESSO_ADMIN)
    ).order_by(Usuario.nome).all()
    return render_template(
        "painel_professores.html",
        usuario=usuario,
        professores=professores,
        cargos_rotulos=CARGOS_ROTULOS,
        dias_semana=DIAS_SEMANA,
        series_disponiveis=SERIES_DISPONIVEIS,
    )


@app.route("/admin/professores/adicionar", methods=["POST"])
@admin_obrigatorio
def admin_adicionar_professor():
    nome = request.form.get("nome", "").strip()
    matricula = request.form.get("matricula", "").strip()
    cargo = request.form.get("cargo", "professor").strip()

    if cargo not in CARGOS_SEM_ACESSO_ADMIN:
        cargo = "professor"

    if not nome or not matricula:
        flash("Preencha nome e matrícula.")
        return redirect(url_for("admin_professores"))

    ja_existe = Usuario.query.filter_by(identificador=matricula).first()
    if ja_existe:
        flash(f"Já existe um usuário com a matrícula '{matricula}'.")
        return redirect(url_for("admin_professores"))

    novo = Usuario(nome=nome, identificador=matricula, cargo=cargo, ativo=True, senha_temporaria=True)
    novo.definir_senha(SENHA_TEMPORARIA_PADRAO)
    db.session.add(novo)
    db.session.commit()

    flash(f"Professor cadastrado com sucesso. Matrícula: {matricula}")
    return redirect(url_for("admin_professores"))


@app.route("/admin/professores/<int:usuario_id>/remover", methods=["POST"])
@admin_obrigatorio
def admin_remover_professor(usuario_id):
    professor = Usuario.query.get_or_404(usuario_id)
    nome = professor.nome

    RegistroPonto.query.filter_by(usuario_id=professor.id).delete()
    db.session.delete(professor)
    db.session.commit()

    flash(f"'{nome}' e seu histórico de pontos foram removidos.")
    return redirect(url_for("admin_professores"))


@app.route("/admin/professores/<int:usuario_id>/editar", methods=["GET", "POST"])
@admin_obrigatorio
def admin_editar_professor(usuario_id):
    usuario_admin = Usuario.query.get(session["usuario_id"])
    pessoa = Usuario.query.get_or_404(usuario_id)

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        cargo = request.form.get("cargo", "").strip()
        if nome:
            pessoa.nome = nome
        if cargo in CARGOS_SEM_ACESSO_ADMIN:
            pessoa.cargo = cargo

        for campo in ["horario_entrada", "horario_saida_almoco", "horario_volta_almoco", "horario_saida"]:
            valor = request.form.get(campo, "").strip()
            if valor:
                hora, minuto = map(int, valor.split(":"))
                setattr(pessoa, campo, dt_time(hora, minuto))

        dias = request.form.getlist("dias_semana")
        pessoa.dias_semana = ",".join(dias)

        if pessoa.cargo == "professor":
            series = request.form.getlist("series")
            pessoa.series = ",".join(series)
        else:
            pessoa.series = None

        nova_senha = request.form.get("senha", "").strip()
        if nova_senha:
            if len(nova_senha) < 4:
                flash("A nova senha precisa ter pelo menos 4 caracteres.")
                return redirect(url_for("admin_editar_professor", usuario_id=usuario_id))
            pessoa.definir_senha(nova_senha)
            pessoa.senha_temporaria = True

        db.session.commit()
        flash(f"Dados de '{pessoa.nome}' atualizados.")
        return redirect(url_for("admin_professores"))

    return render_template(
        "editar_professor.html",
        usuario=usuario_admin,
        pessoa=pessoa,
        cargos_rotulos={c: CARGOS_ROTULOS[c] for c in CARGOS_SEM_ACESSO_ADMIN},
        dias_semana=DIAS_SEMANA,
        series_disponiveis=SERIES_DISPONIVEIS,
    )


# ------------------------------------------------------------------
# PAINEL ADMIN - USUÁRIOS (Administração / Suporte)
# ------------------------------------------------------------------
@app.route("/admin/usuarios")
@admin_obrigatorio
def admin_usuarios():
    usuario = Usuario.query.get(session["usuario_id"])
    admins = Usuario.query.filter(
        Usuario.cargo.in_(CARGOS_COM_ACESSO_ADMIN)
    ).order_by(Usuario.nome).all()
    return render_template("painel_usuarios.html", usuario=usuario, admins=admins, cargos_rotulos=CARGOS_ROTULOS)


@app.route("/admin/usuarios/adicionar", methods=["POST"])
@admin_obrigatorio
def admin_adicionar_usuario():
    nome = request.form.get("nome", "").strip()
    identificador = request.form.get("identificador", "").strip()
    cargo = request.form.get("cargo", "suporte").strip()

    if cargo not in CARGOS_COM_ACESSO_ADMIN:
        cargo = "suporte"

    if not nome or not identificador:
        flash("Preencha nome e login.")
        return redirect(url_for("admin_usuarios"))

    ja_existe = Usuario.query.filter_by(identificador=identificador).first()
    if ja_existe:
        flash(f"Já existe um usuário com o login '{identificador}'.")
        return redirect(url_for("admin_usuarios"))

    novo = Usuario(nome=nome, identificador=identificador, cargo=cargo, ativo=True, senha_temporaria=True)
    novo.definir_senha(SENHA_TEMPORARIA_PADRAO)
    db.session.add(novo)
    db.session.commit()

    flash(f"Usuário '{nome}' adicionado com sucesso.")
    return redirect(url_for("admin_usuarios"))


@app.route("/admin/usuarios/<int:usuario_id>/excluir", methods=["POST"])
@admin_obrigatorio
def admin_remover_usuario(usuario_id):
    alvo = Usuario.query.get_or_404(usuario_id)

    if alvo.id == session["usuario_id"]:
        flash("Você não pode excluir a sua própria conta por aqui.")
        return redirect(url_for("admin_usuarios"))

    nome = alvo.nome
    db.session.delete(alvo)
    db.session.commit()
    flash(f"Usuário '{nome}' excluído.")
    return redirect(url_for("admin_usuarios"))


@app.route("/admin/usuarios/<int:usuario_id>/editar", methods=["GET", "POST"])
@admin_obrigatorio
def admin_editar_usuario(usuario_id):
    from flask import render_template_string

    solicitante = Usuario.query.get(session["usuario_id"])
    alvo = Usuario.query.get_or_404(usuario_id)

    if request.method == "POST":
        novo_nome = request.form.get("nome", "").strip()
        novo_login = request.form.get("identificador", "").strip()
        nova_senha = request.form.get("senha", "").strip()
        novo_cargo = request.form.get("cargo", "").strip()

        if novo_login and novo_login != alvo.identificador:
            conflito = Usuario.query.filter_by(identificador=novo_login).first()
            if conflito:
                flash(f"Já existe um usuário com o login '{novo_login}'.")
                return redirect(url_for("admin_editar_usuario", usuario_id=usuario_id))
            alvo.identificador = novo_login

        if novo_nome:
            alvo.nome = novo_nome

        if novo_cargo in CARGOS_COM_ACESSO_ADMIN:
            alvo.cargo = novo_cargo

        if nova_senha:
            if len(nova_senha) < 4:
                flash("A nova senha precisa ter pelo menos 4 caracteres.")
                return redirect(url_for("admin_editar_usuario", usuario_id=usuario_id))
            alvo.definir_senha(nova_senha)
            alvo.senha_temporaria = True

        db.session.commit()
        flash(f"Dados de '{alvo.nome}' atualizados.")
        return redirect(url_for("admin_usuarios"))

    template_edicao = """
    {% extends "base_admin.html" %}
    {% block titulo %}Editar Usuário{% endblock %}
    {% block ativo_usuarios %}ativo{% endblock %}
    {% block conteudo %}
        <h2>Editar - {{ alvo.nome }}</h2>
        <form method="POST" style="background:white; padding:20px; border-radius:12px; max-width:400px;">
            <label style="display:block; font-size:13px; margin-bottom:4px;">Nome</label>
            <input type="text" name="nome" value="{{ alvo.nome }}" style="width:100%; padding:10px; margin-bottom:14px; border:1px solid #d1d5db; border-radius:8px; font-size:15px;">

            <label style="display:block; font-size:13px; margin-bottom:4px;">Login</label>
            <input type="text" name="identificador" value="{{ alvo.identificador }}" style="width:100%; padding:10px; margin-bottom:14px; border:1px solid #d1d5db; border-radius:8px; font-size:15px;">

            <label style="display:block; font-size:13px; margin-bottom:4px;">Cargo</label>
            <select name="cargo" style="width:100%; padding:10px; margin-bottom:14px; border:1px solid #d1d5db; border-radius:8px; font-size:15px;">
                <option value="administracao" {{ "selected" if alvo.cargo == "administracao" else "" }}>Administração</option>
                <option value="suporte" {{ "selected" if alvo.cargo == "suporte" else "" }}>Suporte</option>
            </select>

            <label style="display:block; font-size:13px; margin-bottom:4px;">Nova senha (deixe em branco para não alterar)</label>
            <input type="password" name="senha" minlength="4" style="width:100%; padding:10px; margin-bottom:18px; border:1px solid #d1d5db; border-radius:8px; font-size:15px;">

            <button type="submit" style="width:100%; padding:12px; background:#2563eb; color:white; border:none; border-radius:8px; cursor:pointer; font-size:15px; font-weight:bold;">
                Salvar
            </button>
        </form>
    {% endblock %}
    """
    return render_template_string(template_edicao, usuario=solicitante, alvo=alvo)


# ------------------------------------------------------------------
# PAINEL ADMIN - EXPORTAR EXCEL
# ------------------------------------------------------------------
@app.route("/admin/excel")
@admin_obrigatorio
def admin_excel():
    usuario = Usuario.query.get(session["usuario_id"])
    todas_pessoas = Usuario.query.order_by(Usuario.nome).all()
    return render_template("painel_excel.html", usuario=usuario, todas_pessoas=todas_pessoas)


def calcular_horas_trabalhadas_minutos(batimentos):
    entrada = batimentos.get("entrada")
    saida_almoco = batimentos.get("saida_almoco")
    volta_almoco = batimentos.get("volta_almoco")
    saida = batimentos.get("saida")

    if not entrada or not saida:
        return None

    total = (saida.horario - entrada.horario).total_seconds() / 60
    if saida_almoco and volta_almoco:
        total -= (volta_almoco.horario - saida_almoco.horario).total_seconds() / 60

    return max(0, round(total))


def formatar_minutos_como_horas(minutos):
    if minutos is None:
        return ""
    horas = minutos // 60
    resto = minutos % 60
    return f"{horas}h{resto:02d}"


@app.route("/admin/excel/gerar", methods=["POST"])
@admin_obrigatorio
def admin_gerar_excel():
    from io import BytesIO
    from openpyxl import Workbook
    from flask import send_file

    usuario_id_filtro = request.form.get("usuario_id", type=int)
    data_inicio = request.form.get("data_inicio", "").strip()
    data_fim = request.form.get("data_fim", "").strip()
    colunas = request.form.getlist("colunas")
    if not colunas:
        colunas = ["nome", "data", "horarios", "horas_totais"]

    consulta = RegistroPonto.query.join(
        Usuario, RegistroPonto.usuario_id == Usuario.id
    ).order_by(Usuario.nome, RegistroPonto.horario)

    if usuario_id_filtro:
        consulta = consulta.filter(RegistroPonto.usuario_id == usuario_id_filtro)
    if data_inicio:
        consulta = consulta.filter(
            RegistroPonto.horario >= datetime.strptime(data_inicio, "%Y-%m-%d")
        )
    if data_fim:
        data_fim_completa = datetime.strptime(data_fim, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        consulta = consulta.filter(RegistroPonto.horario <= data_fim_completa)

    registros = consulta.all()

    agrupado = {}
    for registro in registros:
        chave = (registro.usuario.nome, registro.horario.strftime("%d/%m/%Y"))
        if chave not in agrupado:
            agrupado[chave] = {}
        agrupado[chave][registro.tipo_batimento] = registro

    workbook = Workbook()
    planilha = workbook.active
    planilha.title = "Ponto"

    cabecalho = []
    if "nome" in colunas:
        cabecalho.append("Professor")
    if "data" in colunas:
        cabecalho.append("Data")
    if "horarios" in colunas:
        cabecalho += ["Entrada", "Saída Almoço", "Volta Almoço", "Saída"]
    if "horas_totais" in colunas:
        cabecalho.append("Horas Totais")
    if "horas_extras_autorizadas" in colunas:
        cabecalho.append("Horas Extras Autorizadas")
    if "horas_extras_nao_autorizadas" in colunas:
        cabecalho.append("Horas Extras Não Autorizadas")
    planilha.append(cabecalho)

    for (nome_pessoa, data_str), batimentos in sorted(agrupado.items()):
        linha = []
        if "nome" in colunas:
            linha.append(nome_pessoa)
        if "data" in colunas:
            linha.append(data_str)
        if "horarios" in colunas:
            for tipo in ORDEM_BATIDAS:
                registro = batimentos.get(tipo)
                if registro:
                    texto = registro.horario.strftime("%H:%M")
                    if registro.status == "pendente":
                        texto += " (atrasado)"
                    elif registro.status == "ajustado":
                        texto += " (ajustado)"
                else:
                    texto = ""
                linha.append(texto)
        if "horas_totais" in colunas:
            minutos = calcular_horas_trabalhadas_minutos(batimentos)
            linha.append(formatar_minutos_como_horas(minutos))
        if "horas_extras_autorizadas" in colunas:
            saida = batimentos.get("saida")
            minutos = saida.hora_extra_minutos if (saida and saida.hora_extra_autorizada) else 0
            linha.append(formatar_minutos_como_horas(minutos) if minutos else "")
        if "horas_extras_nao_autorizadas" in colunas:
            saida = batimentos.get("saida")
            minutos = saida.hora_extra_minutos if (saida and not saida.hora_extra_autorizada) else 0
            linha.append(formatar_minutos_como_horas(minutos) if minutos else "")

        planilha.append(linha)

    for indice in range(1, len(cabecalho) + 1):
        letra_coluna = planilha.cell(row=1, column=indice).column_letter
        planilha.column_dimensions[letra_coluna].width = 20

    arquivo_em_memoria = BytesIO()
    workbook.save(arquivo_em_memoria)
    arquivo_em_memoria.seek(0)

    nome_arquivo = f"ponto_{agora_brasil().strftime('%Y%m%d_%H%M')}.xlsx"

    return send_file(
        arquivo_em_memoria,
        as_attachment=True,
        download_name=nome_arquivo,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


if __name__ == "__main__":
    modo_debug = os.environ.get("DEBUG", "").strip().lower() == "true"
    app.run(debug=modo_debug)
