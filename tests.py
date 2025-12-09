import pytest
import os
import dotenv
from hackathon_functions import gemini_api_call
import json
from hackathon_functions import KPIS_PREFERENCES, KPIS_ORDER_OPERAND

def test_gemini_api_key_exists():
    """Verifica que existe .env GEMINI_API_KEY está definida en .env"""    
    if not os.path.isfile(".env"):
        pytest.fail(".env no existe")

    dotenv.load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key is None:
        pytest.fail("GEMINI_API_KEY no está definida en .env")
    if api_key == "":
        pytest.fail("GEMINI_API_KEY está vacía en .env")
        

def test_gemini_call_with_tool():
    """Test que verifica que gemini_call funciona correctamente con las tools definidas, y devuelve una función SIEMPRE"""
    with open("functions.json", "r") as f:
        functions_dataset = json.load(f)

    deploy_app = functions_dataset["deploy_app"]
    migrate_app = functions_dataset["migrate_app"]
    stop_app = functions_dataset["stop_app"]
    
    # Prompt de ejemplo
    test_prompt = "Holaa, que tal?"
    
    # Llamar a la función
    result = gemini_api_call(tools_list=[deploy_app, migrate_app, stop_app], prompt=test_prompt)
    
    # Verificar estructura de la respuesta
    if result["function"] == []:
        pytest.fail("El llm no devolvió una función")

# Cargar datos de test una sola vez
def load_test_data():
    """Carga los archivos JSON de test"""
    try:
        with open("test-queries-with-solutions.json", "r", encoding='utf-8') as f:
            solutions = json.load(f)
        with open("results.json", "r", encoding='utf-8') as f:
            results = json.load(f)
        return solutions, results
    except FileNotFoundError as e:
        pytest.fail(f"No se encontró uno de los archivos JSON: {e}")

# Generar parámetros para cada query individual
def generate_test_params():
    """Genera parámetros para pytest.mark.parametrize"""
    solutions, results = load_test_data()
    params = []
    
    for suite_name, expected_list in solutions.items():
        for i, expected_item in enumerate(expected_list):
            # Crear un ID único para cada test
            test_id = f"{suite_name}_query_{i+1}"
            params.append((suite_name, i, expected_item, test_id))
    
    return params

@pytest.mark.parametrize("suite_name,query_index,expected_item,test_id", generate_test_params(), ids=lambda x: x if isinstance(x, str) else None)
def test_gemini_query(suite_name, query_index, expected_item, test_id):
    """Test individual para cada query de Gemini"""
    
    # Cargar resultados
    _, results = load_test_data()
    
    # Verificar que la suite existe en resultados
    if suite_name not in results:
        pytest.fail(f"Falta la suite '{suite_name}' en results.json")
        
    actual_list = results[suite_name]
    
    # Verificar que existe el resultado para esa posición
    if query_index >= len(actual_list):
        pytest.fail(f"Falta resultado para {suite_name} Número {query_index+1}")
    
    actual_item = actual_list[query_index]

    # 1. Comprobación de integridad de la Query
    if expected_item['query'] != actual_item.get('query'):
        pytest.fail(f"La query no coincide en {suite_name}[Número {query_index+1}]. Revisar orden de tests.")

    # 2. Extraer funciones (ignorando tokens)
    exp_funcs = expected_item.get('expected_result', {}).get('function', [])
    act_funcs = actual_item.get('execution_result', {}).get('function', [])

    # 3. Comprobar número de funciones
    if len(exp_funcs) != len(act_funcs):
        pytest.fail(f"Diferente número de funciones en {suite_name}[Número {query_index+1}]. Esperado: {len(exp_funcs)}, Obtenido: {len(act_funcs)}")

    # 4. Comprobar detalles de cada función (Nombre y Argumentos)
    for ef, af in zip(exp_funcs, act_funcs):
        
        # Nombre de la función
        if ef['function_name'] != af['function_name']:
            pytest.fail(f"Nombre de función incorrecto en {suite_name}[Número {query_index+1}]. Esperado: '{ef['function_name']}', Obtenido: '{af['function_name']}'")
        
        # Argumentos
        if ef['args'] != af['args']:
            pytest.fail(
                f"Argumentos incorrectos en {suite_name}[Número {query_index+1}] - función '{ef['function_name']}'.\n"
                f"Esperado: {ef['args']}\n"
                f"Obtenido: {af['args']}"
            )      
    
    # 5. Extraer nodo elegido y estado esperado         
    expected_chosen_nodes = expected_item.get("chosen_node", [])
    actual_chosen_nodes = actual_item.get("chosen_node", [])
    for j, (exp_node, act_node) in enumerate(zip(expected_chosen_nodes, actual_chosen_nodes)):
        if exp_node != act_node:
            pytest.fail(
                f"Nodo elegido incorrecto en {suite_name}[Número {query_index+1}], función {j+1}.\n"
                f"Esperado: {exp_node}\n"
                f"Obtenido: {act_node}"
            )
    
    expected_state = expected_item.get("state", [])
    actual_state = actual_item.get("state", [])
    for j, (exp_state, act_state) in enumerate(zip(expected_state, actual_state)):
        if exp_state != act_state:
            pytest.fail(
                f"Estado incorrecto en {suite_name}[Número {query_index+1}], función {j+1}.\n"
                f"Esperado: {exp_state}\n"
                f"Obtenido: {act_state}"
            )


if __name__ == "__main__":   pytest.main([__file__])
     
       