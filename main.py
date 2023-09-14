import os
import requests
from elasticsearch import Elasticsearch, client
from flask import Flask, render_template, request, send_file, redirect, url_for, make_response, jsonify
import json
from werkzeug.utils import secure_filename
import csv
import re
from markupsafe import Markup
from elasticsearch_dsl import Search, Q, Index

from filters import env

app = Flask(__name__, static_folder='static')
app.template_folder = os.path.dirname(os.path.abspath(__file__))
app.config['UPLOAD_FOLDER'] = 'temp'

# URL do Elasticsearch
elasticsearch_url = 'http://localhost:9200'
index_name = 'meu_indice'


@app.route("/ajuda")
def ajuda():
    return render_template('templates/ajuda.html')

@app.route("/acessibilidade")
def acessibilidade():
    return render_template('templates/acessibilidade.html')

@app.route('/', methods=['GET', 'POST'])
def index():
    # Obtém o valor do cookie 'checkbox_state' se existir
    checkbox_state_cookie = request.cookies.get('checkbox_state')

    if request.method == 'POST':
        search_query = request.form['search_query']
        processo_ids = request.form.getlist('processo_ids')
        checkbox_state = request.form.getlist('checkbox_state')

        # Extrair a classe selecionada do formulário
        selected_classe = request.form.get('classe_select')

        # Chamar a função perform_search com a classe selecionada
        search_results = perform_search(search_query, search_fields=['numero_processo', 'nome_classe'],
                                        selected_classe=selected_classe)

        # Cria um novo cookie 'checkbox_state' com o valor atualizado
        response = make_response(redirect(url_for('search_results', search_query=search_query, processo_ids=processo_ids)))
        response.set_cookie('checkbox_state', ','.join(checkbox_state))

        return response

    else:
        selected_classe = None

    search_query = request.args.get('search_query')

    unique_classes = get_unique_classes()
    if search_query:
        # Obtém o estado das checkboxes a partir do cookie
        checkbox_state = checkbox_state_cookie.split(',') if checkbox_state_cookie else []

        search_results = perform_search(search_query, search_fields=['numero_processo', 'nome_classe', 'binario.modeloDocumento'], selected_classe=selected_classe)
        checkbox_state = checkbox_state_cookie.split(',') if checkbox_state_cookie else []

        return render_template('templates/index.html', search_query=search_query, search_results=search_results,
                               checkbox_state=checkbox_state, unique_classes=unique_classes, selected_classe=selected_classe)

    return render_template('templates/index.html')

@app.route('/search_results', methods=['GET'])
def search_results():
    search_query = request.args.get('search_query')
    processo_ids = request.args.getlist('processo_ids')  # Obtém a lista de IDs dos processos marcados
    selected_classe = request.args.get('selected_classe', None)

    if search_query:
        search_results = perform_search(search_query, search_fields=['numero_processo', 'nome_classe', 'binario.modeloDocumento'], selected_classe=selected_classe)
        checkbox_state = request.cookies.get('checkbox_state').split(',')
        total_results = len(search_results)
        # Extrair os numero_processo e nome_classes dos resultados da pesquisa
        processo_ids = [result.get('numero_processo', '') for result in search_results]
        nome_classes = [result.get('nome_classe', '') for result in search_results]



        return render_template('templates/index.html', search_query=search_query, search_results=search_results,
                               checkbox_state=checkbox_state, total_results=total_results, selected_classe=selected_classe,
                               processo_ids=processo_ids, nome_classes=nome_classes, filters=env.filters)

    return render_template('templates/index.html')

@app.route('/save_results', methods=['POST'])
def save_results():
    search_query = request.form['search_query']
    processo_ids = request.form.getlist('processo_ids')
    fields_to_export = request.form.get('fields_to_export').split(',')

    # Obter os dados dos processos correspondentes aos IDs marcados
    processo_data = []
    for processo_id in processo_ids:
        result = get_process_data_by_id(processo_id, search_fields=fields_to_export)
        if result:
            processo_data.append(result)

    # Salvar os dados no CSV
    save_to_csv(processo_data, fields_to_export, filename='search_results.csv')

    return send_file('search_results.csv', as_attachment=True)

@app.route('/download_csv', methods=['POST'])
def download_csv():
    search_query = request.form['search_query']
    processo_ids = request.form.get('processo_ids').split(',')
    fields_to_export = request.form.get('fields_to_export').split(',')

    processo_data = []  # Adicione aqui os dados do processo corretos para exportação

    # Se nenhum campo for selecionado, exporte todos os campos disponíveis por padrão
    if not fields_to_export:
        fields_to_export = ['numero_processo', 'nome_classe', 'binario.modeloDocumento']

    # Se nenhum processo for selecionado, retorne uma mensagem de erro
    if not processo_ids:
        return "Nenhum processo selecionado."

    # Obter os dados dos processos selecionados
    processo_data = []
    for processo_id in processo_ids:
        result = get_process_data_by_id(processo_id)
        if result:
            processo_data.append(result)

    # Salvar os dados no arquivo CSV
    save_to_csv(processo_data, fields_to_export, filename='relatorio_exportacao.csv')

    return send_file('relatorio_exportacao.csv', as_attachment=True)

def save_to_csv(processo_data, fields_to_export, filename):
    with open(filename, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=fields_to_export)
        writer.writeheader()
        for data in processo_data:
            row = {field: data.get(field, '') for field in fields_to_export}
            writer.writerow(row)

def get_process_data_by_id(processo_id, search_fields=None):
    # Função auxiliar para obter os dados de um processo específico pelo seu ID
    if not search_fields:
        search_fields = ['numero_processo', 'nome_classe']

    search_results = perform_search(processo_id, search_fields=search_fields)
    if search_results:
        return search_results[0]
    return None

@app.route('/get_unique_classes', methods=['GET'])
def get_unique_classes():
    # Crie uma conexão com o Elasticsearch
    es = Elasticsearch(elasticsearch_url)

    # Defina uma consulta que busca todas as classes únicas no índice
    query = {
        "size": 0,
        "aggs": {
            "unique_classes": {
                "terms": {
                    "field": "nome_classe.keyword",
                    "size": 1000  # Ajuste o tamanho conforme necessário
                }
            }
        }
    }

    try:
        # Execute a consulta no Elasticsearch
        result = es.search(index=index_name, body=query)

        # Extraia as classes únicas do resultado
        unique_classes = [bucket["key"] for bucket in result["aggregations"]["unique_classes"]["buckets"]]
        return unique_classes

    except Exception as e:
        # Lida com erros de conexão ou consulta
        print(f"Erro ao obter classes únicas: {str(e)}")
        return []


def perform_search(query, search_fields=None, selected_classe=None):
    # Adicione logs para verificar se a classe selecionada está sendo passada corretamente
    print(f"Selected Classe: {selected_classe}")

    url = f'{elasticsearch_url}/{index_name}/_search?size=1000'
    headers = {'Content-Type': 'application/json'}

    if search_fields is None:
        search_fields = ['numero_processo', 'nome_classe']

    query = query.replace('NÃO:', 'NÃO: ').replace('E:', 'E: ').replace('OU:', 'OU: ')
    terms = query.split()

    s = Search(using=headers, index=index_name)

    must_queries = []
    must_not_queries = [Q("term", sigiloso=True)]
    should_queries = []

    current_operator = 'E'

    for term in terms:
        if term == 'NÃO:':
            current_operator = 'NÃO'
        elif term == 'E:':
            current_operator = 'E'
        elif term == 'OU:':
            current_operator = 'OU'
        else:
            field_queries = [Q('match', **{field: term}) | Q('wildcard', **{field: f'*{term}*'}) for field in search_fields]
            if current_operator == 'E':
                must_queries.append(Q('bool', should=field_queries))
            elif current_operator == 'OU':
                should_queries.append(Q('bool', should=field_queries))
            elif current_operator == 'NÃO':
                must_not_queries.append(Q('bool', should=field_queries))
            # Adicione a condição de filtro para a classe selecionada, se houver

    if selected_classe:
        must_queries.append(Q("term", nome_classe=selected_classe))

    query = Q('bool', must=must_queries, must_not=must_not_queries, should=should_queries)

    s = s.query(query)
    query_json = s.to_dict()
    query_json_str = json.dumps(query_json)

    response = requests.post(url, headers=headers, data=query_json_str)
    results = response.json()
    hits = results.get('hits', {}).get('hits', [])
    search_results = [hit['_source'] for hit in hits]

    return search_results



def replace_case_insensitive(value, search, result):
    search_terms = search.split()
    regex_pattern = r'(?i)\b(' + '|'.join(map(re.escape, search_terms)) + r')\b'
    return re.sub(regex_pattern, lambda match: Markup('<mark class="highlight">' + match.group(0) + '</mark>'), str(value))

app.jinja_env.filters['replace_case_insensitive'] = replace_case_insensitive

if __name__ == '__main__':
    if not os.path.exists(app.config['UPLOAD_FOLDER']):
        os.makedirs(app.config['UPLOAD_FOLDER'])

    app.run(debug=True, host='0.0.0.0', port=5000)
