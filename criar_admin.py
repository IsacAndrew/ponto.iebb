from app import app
from models import db, Usuario


def criar_admin():
    with app.app_context():
        print("=== Criar novo usuário administrativo ===\n")

        nome = input("Nome completo: ").strip()
        identificador = input("Login (ex: sandra, isac, silvana): ").strip()

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

        cargo = input("Cargo (administracao/suporte) [suporte]: ").strip().lower()
        if cargo not in ("administracao", "suporte"):
            cargo = "suporte"

        novo_admin = Usuario(
            nome=nome,
            identificador=identificador,
            cargo=cargo,
            ativo=True,
        )
        novo_admin.definir_senha(senha)

        db.session.add(novo_admin)
        db.session.commit()

        print(f"\nUsuário '{nome}' criado com sucesso!")
        print(f"Login: {identificador} | Cargo: {cargo}")


if __name__ == "__main__":
    criar_admin()
