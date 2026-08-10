"""
criar_admin.py
---------------
Script separado, que você roda UMA VEZ (ou sempre que precisar criar um
novo admin manualmente), para cadastrar o primeiro usuário administrativo
do sistema. Sem isso, ninguém consegue logar, porque o banco começa vazio.

Como usar:

    python criar_admin.py

O script vai perguntar o nome, o login e a senha, direto no terminal.
"""

from app import app
from models import db, Usuario


def criar_admin():
    # Precisamos estar "dentro do contexto" do app Flask para mexer no
    # banco por fora de uma rota normal (isso é uma exigência do
    # Flask-SQLAlchemy, não é nada complicado, só uma formalidade).
    with app.app_context():
        print("=== Criar novo usuário administrativo ===\n")

        nome = input("Nome completo: ").strip()
        identificador = input("Login (ex: sandra, isac, silvana): ").strip()

        # Confere se já existe alguém com esse login, pra não duplicar.
        ja_existe = Usuario.query.filter_by(identificador=identificador).first()
        if ja_existe:
            print(f"\nJá existe um usuário com o login '{identificador}'. Cancelando.")
            return

        senha = input("Senha: ").strip()
        confirmar_senha = input("Confirme a senha: ").strip()

        if senha != confirmar_senha:
            print("\nAs senhas não coincidem. Cancelando.")
            return

        if len(senha) < 4:
            print("\nA senha precisa ter pelo menos 4 caracteres. Cancelando.")
            return

        novo_admin = Usuario(
            nome=nome,
            identificador=identificador,
            tipo="admin",
            ativo=True,
        )
        novo_admin.definir_senha(senha)

        db.session.add(novo_admin)
        db.session.commit()

        print(f"\nUsuário administrativo '{nome}' criado com sucesso!")
        print(f"Login: {identificador}")


if __name__ == "__main__":
    criar_admin()
