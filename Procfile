# Procfile
# ---------
# Esse arquivo diz para o Render (ou qualquer serviço parecido, tipo
# Heroku) COMO iniciar a aplicação. Sem ele, o Render não sabe rodar
# um projeto Flask corretamente.
#
# "web" é o tipo de processo (um serviço que recebe requisições HTTP).
# "gunicorn app:app" significa: use o gunicorn para rodar o objeto
# chamado "app" que está dentro do arquivo "app.py".
#
# Isso substitui o "python app.py" que usamos só para testar local -- o
# gunicorn é feito para aguentar tráfego de verdade, em produção.

web: gunicorn app:app
