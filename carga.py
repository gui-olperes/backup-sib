import json
import requests

def bulk_index_documents(index, file_path):
    # Configurações do Elasticsearch
    url = 'http://localhost:9200'
    headers = {'Content-Type': 'application/json'}

    # Carrega o arquivo JSON
    with open(file_path, 'r', encoding='utf-8') as file:
        data = json.load(file)

    # Prepara a carga em lote
    bulk_data = ''
    for item in data:
        index_data = {
            'index': {
                '_index': index
            }
        }
        bulk_data += json.dumps(index_data) + '\n' + json.dumps(item) + '\n'

    # Faz a requisição de carga em lote
    try:
        response = requests.post(f'{url}/_bulk', headers=headers, data=bulk_data)
        response.raise_for_status()
        results = response.json()
        return results
    except requests.exceptions.RequestException as e:
        print(f'Erro ao fazer a requisição: {e}')
        return None

# Exemplo de uso
index = 'meu_indice'
file_path = 'carga-teste.json'

result = bulk_index_documents(index, file_path)
if result:
    # Processa os resultados
    print(result)
else:
    print('Erro na requisição de carga em lote.')
