"""
app.py
-------
Arquivo principal do sistema. É ele que:
  1. Cria o app Flask
  2. Conecta o banco de dados (models.py)
  3. Define as rotas (URLs) -- por enquanto: login, logout, e bater ponto

Para rodar o sistema (depois de instalar as dependências, ver
requirements.txt que vamos gerar em breve):

    python app.py

E abrir no navegador: http://localhost:5000
"""

import os
from datetime import datetime, time as dt_time
from flask import Flask, render_template, request, redirect, url_for, session, flash
from functools import wraps

from config import Config
from models import db, Usuario, RegistroPonto
from utils import esta_dentro_do_raio, calcular_minutos_atraso


def criar_app():
    """
    Função "fábrica" que monta o app Flask. Fazer assim (em vez de criar
    o app direto no arquivo) é uma boa prática -- facilita testar o
    sistema depois, se você quiser.
    """
    app = Flask(__name__)
    app.config.from_object(Config)

    # Conecta o SQLAlchemy (definido em models.py) a este app específico.
    db.init_app(app)

    # Cria as tabelas no banco automaticamente, caso ainda não existam.
    # (Em produção, depois que o sistema já estiver "no ar" há um tempo,
    # o ideal é usar migrations -- mas pra começar, isso já resolve.)
    with app.app_context():
        db.create_all()
        criar_admin_inicial_se_necessario()

    return app


def criar_admin_inicial_se_necessario():
    """
    No plano gratuito do Render não tem Shell -- ou seja, não dá pra
    rodar "python criar_admin.py" manualmente lá. Para resolver isso,
    o próprio sistema cria o primeiro admin sozinho, assim que sobe,
    lendo o nome/login/senha de variáveis de ambiente.

    Isso só acontece se:
      1. As variáveis ADMIN_NOME, ADMIN_LOGIN e ADMIN_SENHA estiverem
         configuradas (no painel do Render: Environment Variables); e
      2. Ainda não existir ninguém cadastrado com esse login.

    Ou seja: é seguro rodar isso toda vez que o sistema reinicia --
    ele só cria a conta na primeira vez, depois disso não faz nada.
    """
    nome = os.environ.get("ADMIN_NOME")
    login = os.environ.get("ADMIN_LOGIN")
    senha = os.environ.get("ADMIN_SENHA")

    if not (nome and login and senha):
        return  # Variáveis não configuradas -- não faz nada.

    ja_existe = Usuario.query.filter_by(identificador=login).first()
    if ja_existe:
        return  # Já foi criado antes -- não duplica.

    novo_admin = Usuario(nome=nome, identificador=login, tipo="admin", ativo=True)
    novo_admin.definir_senha(senha)
    db.session.add(novo_admin)
    db.session.commit()


app = criar_app()


# ------------------------------------------------------------------
# HORÁRIOS ESPERADOS PARA CADA TIPO DE BATIMENTO
# ------------------------------------------------------------------
# Isso é só um ponto de partida -- ajuste os horários reais da escola
# aqui. Futuramente dá pra mover isso para o banco de dados, caso cada
# professor tenha um horário diferente.
HORARIOS_ESPERADOS = {
    "entrada": dt_time(7, 0),
    "saida_almoco": dt_time(12, 0),
    "volta_almoco": dt_time(13, 0),
    "saida": dt_time(17, 0),
}

# Ordem fixa das batidas do dia, e o texto que aparece no botão único
# para cada uma. "Entrada" é a 1ª, "Saída" é a 4ª -- sempre nessa ordem.
ORDEM_BATIDAS = ["entrada", "saida_almoco", "volta_almoco", "saida"]
ROTULOS_BOTAO = {
    "entrada": "Entrada",
    "saida_almoco": "Almoço",
    "volta_almoco": "Retorno do Almoço",
    "saida": "Saída",
}


def calcular_proxima_batida(usuario_id):
    """
    Conta quantos pontos esse usuário já bateu HOJE e descobre qual é o
    próximo tipo esperado. Retorna (tipo_ou_None, quantidade_hoje).

    Se já bateu os 4 do dia, o tipo volta None (o botão fica desabilitado).
    """
    inicio_do_dia = datetime.combine(datetime.now().date(), dt_time.min)
    fim_do_dia = datetime.combine(datetime.now().date(), dt_time.max)

    quantidade_hoje = RegistroPonto.query.filter(
        RegistroPonto.usuario_id == usuario_id,
        RegistroPonto.horario >= inicio_do_dia,
        RegistroPonto.horario <= fim_do_dia,
    ).count()

    if quantidade_hoje >= len(ORDEM_BATIDAS):
        return None, quantidade_hoje

    return ORDEM_BATIDAS[quantidade_hoje], quantidade_hoje


# ------------------------------------------------------------------
# DECORADOR: exige login
# ------------------------------------------------------------------
def login_obrigatorio(funcao):
    """
    "Decorador" -- uma função que embrulha outra função. Colocamos
    @login_obrigatorio em cima de uma rota para garantir que só quem
    está logado consegue acessar ela.
    """

    @wraps(funcao)
    def rota_protegida(*args, **kwargs):
        if "usuario_id" not in session:
            flash("Você precisa entrar no sistema primeiro.")
            return redirect(url_for("login"))
        return funcao(*args, **kwargs)

    return rota_protegida


def admin_obrigatorio(funcao):
    """Igual ao de cima, mas também exige que o usuário seja admin."""

    @wraps(funcao)
    def rota_protegida(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect(url_for("login"))
        usuario = Usuario.query.get(session["usuario_id"])
        if not usuario or not usuario.eh_admin():
            flash("Você não tem permissão para acessar essa área.")
            return redirect(url_for("bater_ponto"))
        return funcao(*args, **kwargs)

    return rota_protegida


# ------------------------------------------------------------------
# ROTA: LOGIN
# ------------------------------------------------------------------
@app.route("/")
def raiz():
    # A URL principal (ex: https://ponto-iebb.onrender.com/) não tinha
    # nenhuma rota associada -- por isso dava 404. Agora ela só
    # redireciona para o login.
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        identificador = request.form.get("identificador", "").strip()
        senha = request.form.get("senha", "")

        usuario = Usuario.query.filter_by(identificador=identificador).first()

        if usuario and usuario.verificar_senha(senha) and usuario.ativo:
            # Guarda o id do usuário na sessão -- é assim que o sistema
            # "lembra" que você está logado nas próximas páginas.
            session["usuario_id"] = usuario.id
            session["tipo_usuario"] = usuario.tipo
            return redirect(url_for("bater_ponto"))

        flash("Matrícula/login ou senha incorretos.")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ------------------------------------------------------------------
# ROTA: BATER PONTO (tela principal, para professor e admin)
# ------------------------------------------------------------------
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
    """
    Recebe o tipo de batimento + latitude/longitude (mandados pelo
    JavaScript da página) e decide se o ponto é válido, se está fora do
    raio, ou se está atrasado.

    Responde em JSON (a tela usa "fetch", não um formulário tradicional),
    para o JavaScript poder abrir o modal com o mapa sem recarregar a
    página quando o professor estiver fora do raio.
    """
    usuario = Usuario.query.get(session["usuario_id"])

    # O tipo de batimento agora é decidido pelo SERVIDOR (com base em
    # quantas batidas o usuário já fez hoje), não mais enviado pelo
    # cliente -- assim não tem como alguém adulterar o campo e registrar
    # um tipo fora de ordem. O botão único no HTML só manda a localização.
    tipo_batimento, batidas_hoje = calcular_proxima_batida(usuario.id)
    latitude = request.form.get("latitude", type=float)
    longitude = request.form.get("longitude", type=float)

    if tipo_batimento is None:
        return {"status": "erro", "mensagem": "Você já bateu todos os pontos de hoje."}, 400

    agora = datetime.now()

    # --- Validação de GPS ---
    dentro_do_raio = True
    distancia = None
    if latitude is not None and longitude is not None:
        dentro_do_raio, distancia = esta_dentro_do_raio(
            latitude, longitude,
            Config.ESCOLA_LATITUDE, Config.ESCOLA_LONGITUDE,
            Config.RAIO_TOLERANCIA_METROS,
        )

    if not dentro_do_raio:
        # Não salva o ponto -- devolve a distância para o front-end
        # desenhar o mapa (mostrando o círculo da escola e onde o
        # professor está).
        return {"status": "fora_do_raio", "distancia": distancia}

    # --- Validação de atraso (não se aplica à saída final) ---
    minutos_atraso = 0
    status = "normal"
    usou_perdao = False

    if tipo_batimento != "saida":
        horario_esperado_hoje = datetime.combine(agora.date(), HORARIOS_ESPERADOS[tipo_batimento])
        minutos_atraso = calcular_minutos_atraso(horario_esperado_hoje, agora)

        if minutos_atraso > Config.TOLERANCIA_ATRASO_MINUTOS:
            if usuario.perdao_atraso_ativo:
                # A direção já autorizou esse atraso previamente -- não
                # trava o ponto, e "gasta" o perdão (só vale uma vez).
                usou_perdao = True
                usuario.perdao_atraso_ativo = False
            else:
                status = "pendente"

    novo_registro = RegistroPonto(
        usuario_id=usuario.id,
        tipo_batimento=tipo_batimento,
        horario=agora,
        latitude=latitude,
        longitude=longitude,
        distancia_metros=distancia,
        status=status,
        atraso_minutos=minutos_atraso,
        perdao_utilizado=usou_perdao,
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
# ROTAS: PAINEL ADMIN - HORÁRIOS
# ------------------------------------------------------------------
@app.route("/admin")
@admin_obrigatorio
def admin_index():
    return redirect(url_for("admin_horarios"))


@app.route("/admin/horarios")
@admin_obrigatorio
def admin_horarios():
    """
    Monta a tabela "batalha naval": uma linha por (professor, data),
    com os 4 tipos de batimento nas colunas.
    """
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
        # Soma quase um dia inteiro para incluir todos os horários do
        # próprio dia final selecionado.
        data_fim_completa = datetime.strptime(filtro_data_fim, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        consulta = consulta.filter(RegistroPonto.horario <= data_fim_completa)

    # Limite de segurança para não travar a tela em bancos muito grandes.
    registros = consulta.limit(500).all()

    # Agrupa os registros por (usuario_id, data) para montar as linhas
    # da tabela cruzada.
    agrupado = {}
    for registro in registros:
        data_exibicao = registro.horario.strftime("%d/%m/%Y")
        data_url = registro.horario.strftime("%d-%m-%Y")
        chave = (registro.usuario_id, data_exibicao)

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

    todos_professores = Usuario.query.order_by(Usuario.nome).all()

    return render_template(
        "painel_horarios.html",
        usuario=usuario,
        linhas=linhas,
        todos_professores=todos_professores,
        filtro_nome=filtro_nome,
        filtro_data_inicio=filtro_data_inicio,
        filtro_data_fim=filtro_data_fim,
    )


@app.route("/admin/horarios/perdao", methods=["POST"])
@admin_obrigatorio
def admin_conceder_perdao():
    usuario_alvo = Usuario.query.get(request.form.get("usuario_id", type=int))

    if usuario_alvo:
        usuario_alvo.perdao_atraso_ativo = True
        db.session.commit()
        flash(f"Perdão de atraso concedido para {usuario_alvo.nome}. Vale para o próximo ponto batido.")
    else:
        flash("Professor não encontrado.")

    return redirect(url_for("admin_horarios"))


@app.route("/admin/horarios/editar/<int:usuario_id>/<data>", methods=["GET", "POST"])
@admin_obrigatorio
def admin_editar_ponto(usuario_id, data):
    """
    Tela simples para corrigir manualmente os horários batidos por um
    professor em um dia específico. `data` chega no formato DD-MM-AAAA
    (hífen, e não barra -- barra na URL confundiria o Flask, que usa "/"
    para separar partes da rota).
    """
    usuario_admin = Usuario.query.get(session["usuario_id"])
    professor = Usuario.query.get_or_404(usuario_id)

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
        for tipo in ["entrada", "saida_almoco", "volta_almoco", "saida"]:
            novo_horario_texto = request.form.get(f"horario_{tipo}", "").strip()
            if not novo_horario_texto:
                continue

            hora, minuto = map(int, novo_horario_texto.split(":"))
            novo_datetime = datetime.combine(data_convertida, dt_time(hora, minuto))

            registro_existente = registros_por_tipo.get(tipo)
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

            registro_existente.ajustado_por_id = usuario_admin.id
            registro_existente.observacao_ajuste = request.form.get("observacao", "").strip()

        db.session.commit()
        flash(f"Horários de {professor.nome} em {data_exibicao} atualizados.")
        return redirect(url_for("admin_horarios"))

    # Formulário simples de edição -- gerado direto aqui (render_template_string)
    # para não precisar de mais um arquivo de template só para essa telinha.
    from flask import render_template_string

    template_edicao = """
    {% extends "base_admin.html" %}
    {% block titulo %}Editar Ponto{% endblock %}
    {% block conteudo %}
        <h2>Editar horários - {{ professor.nome }} ({{ data_exibicao }})</h2>
        <form method="POST" style="background:white; padding:20px; border-radius:8px; max-width:400px;">
            {% for tipo, rotulo in [("entrada", "Entrada"), ("saida_almoco", "Saída Almoço"),
                                     ("volta_almoco", "Volta Almoço"), ("saida", "Saída")] %}
                <label style="display:block; margin-bottom:4px; font-size:13px;">{{ rotulo }}</label>
                <input type="time" name="horario_{{ tipo }}"
                       value="{{ registros_por_tipo[tipo].horario.strftime('%H:%M') if tipo in registros_por_tipo else '' }}"
                       style="width:100%; padding:8px; margin-bottom:14px;">
            {% endfor %}
            <label style="display:block; margin-bottom:4px; font-size:13px;">Observação (opcional)</label>
            <input type="text" name="observacao" placeholder="Ex: esqueceu de bater, corrigido manualmente"
                   style="width:100%; padding:8px; margin-bottom:16px;">
            <button type="submit" style="padding:10px 20px; background:#2563eb; color:white; border:none; border-radius:4px; cursor:pointer;">
                Salvar
            </button>
        </form>
    {% endblock %}
    """
    return render_template_string(
        template_edicao,
        usuario=usuario_admin,
        professor=professor,
        data_exibicao=data_exibicao,
        registros_por_tipo=registros_por_tipo,
    )


# ------------------------------------------------------------------
# ROTAS: PAINEL ADMIN - PROFESSORES (cadastro por matrícula)
# ------------------------------------------------------------------
@app.route("/admin/professores")
@admin_obrigatorio
def admin_professores():
    usuario = Usuario.query.get(session["usuario_id"])
    professores = Usuario.query.filter_by(tipo="professor").order_by(Usuario.nome).all()
    return render_template("painel_professores.html", usuario=usuario, professores=professores)


@app.route("/admin/professores/adicionar", methods=["POST"])
@admin_obrigatorio
def admin_adicionar_professor():
    nome = request.form.get("nome", "").strip()
    matricula = request.form.get("matricula", "").strip()
    senha = request.form.get("senha", "")

    if not nome or not matricula or len(senha) < 4:
        flash("Preencha nome, matrícula e uma senha de pelo menos 4 caracteres.")
        return redirect(url_for("admin_professores"))

    ja_existe = Usuario.query.filter_by(identificador=matricula).first()
    if ja_existe:
        flash(f"Já existe um usuário com a matrícula '{matricula}'.")
        return redirect(url_for("admin_professores"))

    novo_professor = Usuario(nome=nome, identificador=matricula, tipo="professor", ativo=True)
    novo_professor.definir_senha(senha)
    db.session.add(novo_professor)
    db.session.commit()

    flash(f"Professor '{nome}' cadastrado com sucesso (matrícula {matricula}).")
    return redirect(url_for("admin_professores"))


@app.route("/admin/professores/<int:usuario_id>/alternar", methods=["POST"])
@admin_obrigatorio
def admin_alternar_professor(usuario_id):
    """Ativa/desativa um professor (desativado não consegue mais logar, mas mantém o histórico de pontos)."""
    professor = Usuario.query.get_or_404(usuario_id)
    professor.ativo = not professor.ativo
    db.session.commit()
    flash(f"Professor '{professor.nome}' {'reativado' if professor.ativo else 'desativado'}.")
    return redirect(url_for("admin_professores"))


@app.route("/admin/professores/<int:usuario_id>/remover", methods=["POST"])
@admin_obrigatorio
def admin_remover_professor(usuario_id):
    """
    Remove o cadastro do professor. Atenção: isso também apaga o
    histórico de pontos dele (por causa da ligação entre as tabelas).
    Se quiser manter o histórico só desative o professor em vez de
    removê-lo.
    """
    professor = Usuario.query.get_or_404(usuario_id)
    nome = professor.nome

    # Remove primeiro os registros de ponto ligados a esse professor,
    # para não deixar "lixo" no banco (linhas apontando para um usuário
    # que não existe mais).
    RegistroPonto.query.filter_by(usuario_id=professor.id).delete()
    db.session.delete(professor)
    db.session.commit()

    flash(f"Professor '{nome}' e seu histórico de pontos foram removidos.")
    return redirect(url_for("admin_professores"))


# ------------------------------------------------------------------
# ROTAS: PAINEL ADMIN - USUÁRIOS (CRUD de contas administrativas)
# ------------------------------------------------------------------
# Qualquer admin pode adicionar, editar, trocar o cargo ou excluir
# QUALQUER outro admin livremente -- não existe mais um sistema de
# autorização por código aqui (foi removido a pedido).
@app.route("/admin/usuarios")
@admin_obrigatorio
def admin_usuarios():
    usuario = Usuario.query.get(session["usuario_id"])
    admins = Usuario.query.filter_by(tipo="admin").order_by(Usuario.nome).all()
    return render_template("painel_usuarios.html", usuario=usuario, admins=admins)


@app.route("/admin/usuarios/adicionar", methods=["POST"])
@admin_obrigatorio
def admin_adicionar_usuario():
    nome = request.form.get("nome", "").strip()
    identificador = request.form.get("identificador", "").strip()
    senha = request.form.get("senha", "")

    if not nome or not identificador or len(senha) < 4:
        flash("Preencha nome, login e uma senha de pelo menos 4 caracteres.")
        return redirect(url_for("admin_usuarios"))

    ja_existe = Usuario.query.filter_by(identificador=identificador).first()
    if ja_existe:
        flash(f"Já existe um usuário com o login '{identificador}'.")
        return redirect(url_for("admin_usuarios"))

    novo = Usuario(nome=nome, identificador=identificador, tipo="admin", ativo=True)
    novo.definir_senha(senha)
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
    """
    Edita nome, login, senha e cargo (professor/administrativo) de um
    usuário administrativo. Qualquer admin pode editar qualquer outro,
    sem restrição.
    """
    from flask import render_template_string

    solicitante = Usuario.query.get(session["usuario_id"])
    alvo = Usuario.query.get_or_404(usuario_id)

    if request.method == "POST":
        novo_nome = request.form.get("nome", "").strip()
        novo_login = request.form.get("identificador", "").strip()
        nova_senha = request.form.get("senha", "").strip()
        novo_cargo = request.form.get("tipo", "").strip()

        if novo_login and novo_login != alvo.identificador:
            conflito = Usuario.query.filter_by(identificador=novo_login).first()
            if conflito:
                flash(f"Já existe um usuário com o login '{novo_login}'.")
                return redirect(url_for("admin_editar_usuario", usuario_id=usuario_id))
            alvo.identificador = novo_login

        if novo_nome:
            alvo.nome = novo_nome

        if novo_cargo in ("admin", "professor"):
            alvo.tipo = novo_cargo

        if nova_senha:
            if len(nova_senha) < 4:
                flash("A nova senha precisa ter pelo menos 4 caracteres.")
                return redirect(url_for("admin_editar_usuario", usuario_id=usuario_id))
            alvo.definir_senha(nova_senha)

        db.session.commit()
        flash(f"Dados de '{alvo.nome}' atualizados.")
        return redirect(url_for("admin_usuarios"))

    # Formulário simples, embutido aqui mesmo (mesma ideia usada na
    # edição de ponto, para não precisar de mais um arquivo de template).
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
            <select name="tipo" style="width:100%; padding:10px; margin-bottom:14px; border:1px solid #d1d5db; border-radius:8px; font-size:15px;">
                <option value="admin" {{ "selected" if alvo.tipo == "admin" else "" }}>Administrativo</option>
                <option value="professor" {{ "selected" if alvo.tipo == "professor" else "" }}>Professor</option>
            </select>

            <label style="display:block; font-size:13px; margin-bottom:4px;">Nova senha (deixe em branco para não alterar)</label>
            <input type="password" name="senha" minlength="4" style="width:100%; padding:10px; margin-bottom:18px; border:1px solid #d1d5db; border-radius:8px; font-size:15px;">

            <button type="submit" style="width:100%; padding:12px; background:#2563eb; color:white; border:none; border-radius:8px; cursor:pointer; font-size:15px; font-weight:bold;">
                Salvar
            </button>
        </form>
    {% endblock %}
    """
    return render_template_string(
        template_edicao,
        usuario=solicitante,
        alvo=alvo,
    )


@app.route("/admin/excel")
@admin_obrigatorio
def admin_excel():
    usuario = Usuario.query.get(session["usuario_id"])
    return render_template("painel_excel.html", usuario=usuario)


@app.route("/admin/excel/real")
@admin_obrigatorio
def admin_excel_real():
    usuario = Usuario.query.get(session["usuario_id"])
    todos_professores = Usuario.query.order_by(Usuario.nome).all()
    return render_template("painel_excel_real.html", usuario=usuario, todos_professores=todos_professores)


@app.route("/admin/excel/gerar", methods=["POST"])
@admin_obrigatorio
def admin_gerar_excel():
    """
    Monta a planilha com openpyxl a partir dos filtros escolhidos, e
    devolve o arquivo pronto para download (o navegador baixa
    automaticamente, sem precisar salvar nada no servidor).
    """
    from io import BytesIO
    from openpyxl import Workbook
    from flask import send_file

    usuario_id_filtro = request.form.get("usuario_id", type=int)
    tipo_filtro = request.form.get("tipo_batimento", "").strip()
    data_inicio = request.form.get("data_inicio", "").strip()
    data_fim = request.form.get("data_fim", "").strip()

    consulta = RegistroPonto.query.join(
        Usuario, RegistroPonto.usuario_id == Usuario.id
    ).order_by(Usuario.nome, RegistroPonto.horario)

    if usuario_id_filtro:
        consulta = consulta.filter(RegistroPonto.usuario_id == usuario_id_filtro)
    if tipo_filtro:
        consulta = consulta.filter(RegistroPonto.tipo_batimento == tipo_filtro)
    if data_inicio:
        consulta = consulta.filter(
            RegistroPonto.horario >= datetime.strptime(data_inicio, "%Y-%m-%d")
        )
    if data_fim:
        data_fim_completa = datetime.strptime(data_fim, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
        consulta = consulta.filter(RegistroPonto.horario <= data_fim_completa)

    registros = consulta.all()

    # Monta a tabela cruzada em memória: (professor, data) -> {tipo: horario}
    agrupado = {}
    for registro in registros:
        chave = (registro.usuario.nome, registro.horario.strftime("%d/%m/%Y"))
        if chave not in agrupado:
            agrupado[chave] = {}
        agrupado[chave][registro.tipo_batimento] = registro

    # --- Monta a planilha ---
    workbook = Workbook()
    planilha = workbook.active
    planilha.title = "Ponto"

    rotulos_colunas = ["Professor", "Data", "Entrada", "Saída Almoço", "Volta Almoço", "Saída"]
    planilha.append(rotulos_colunas)

    for (nome_professor, data_str), batimentos in sorted(agrupado.items()):
        linha = [nome_professor, data_str]
        for tipo in ["entrada", "saida_almoco", "volta_almoco", "saida"]:
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
        planilha.append(linha)

    # Ajusta a largura das colunas para ficar legível (não precisa ser
    # bonito, mas larguras muito apertadas cortam o texto na hora de abrir).
    larguras = [22, 12, 16, 16, 16, 16]
    for indice, largura in enumerate(larguras, start=1):
        letra_coluna = planilha.cell(row=1, column=indice).column_letter
        planilha.column_dimensions[letra_coluna].width = largura

    # Salva em memória (não precisa criar um arquivo físico no servidor).
    arquivo_em_memoria = BytesIO()
    workbook.save(arquivo_em_memoria)
    arquivo_em_memoria.seek(0)

    nome_arquivo = f"ponto_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx"

    return send_file(
        arquivo_em_memoria,
        as_attachment=True,
        download_name=nome_arquivo,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    # debug=True facilita muito enquanto você está desenvolvendo (mostra
    # erros detalhados na tela, recarrega sozinho quando salva o arquivo).
    # Lembre de mudar para debug=False quando for para a VPS de verdade.
    app.run(debug=True)
