from google import genai
import os
import dotenv
# Add any other imports you need here

dotenv.load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

#################################### TASK 0: Complete app placement logic ######################################################

# Define KPI preferences per application category
KPIS_PREFERENCES = {
    "uRLLC": [],
    "eMBB": [],
    "mMTC": []
}

# Add +1 if prefer lower values ////// -1 if prefer higher values
KPIS_ORDER_OPERAND = {
    "latency_ms": 0,
    "availability_percent": 0,
    "packet_loss_percent": 0,
    "throughput_mbps": 0,
    "connection_density": 0,
    "energy_efficiency": 0
}

############################################################ END TASK 0 #############################################################

def deploy_app_func(app_name: str, args: dict, apps_dataset: dict, scenario_nodes: list) -> str:
    '''
    This function implements the logic to deploy an application on an edge node based on user-defined KPIs and application requirements.
    
    :param app_name: Name of the application to be deployed
    :type app_name: str
    :param args: User-defined KPIs for deployment
    :type args: dict
    :param apps_dataset: Dataset containing application requirements
    :type apps_dataset: dict
    :param scenario_nodes: List of available edge nodes in the scenario
    :type scenario_nodes: list
    :return: Deployment result message
    :rtype: str
    '''
    kpis_user = {arg: float(args[arg]) for arg in args if arg != "app_name"}

    chosen_node = logic_app_placement(app_name, apps_dataset, scenario_nodes, kpis_user, current_node=None)

    if chosen_node == "NO_NODES_AVAILABLE":
        return f"No hay nodos edge disponibles para desplegar la aplicación {app_name} con los requisitos especificados.", chosen_node           

    return f"La aplicación {app_name} será desplegada en el nodo edge {chosen_node}.",chosen_node   

def migrate_app_func(app_name: str, args: dict, apps_dataset: dict, scenario_nodes: list) -> str:
    '''
    This function implements the logic to migrate an application to a different edge node based on user-defined KPIs and application requirements.
    
    :param app_name: Name of the application to be migrated
    :type app_name: str
    :param args: User-defined KPIs for migration
    :type args: dict
    :param apps_dataset: Dataset containing application requirements
    :type apps_dataset: dict
    :param scenario_nodes: List of available edge nodes in the scenario
    :type scenario_nodes: list
    :return: Migration result message
    :rtype: str
    '''
    kpis_user = {arg: float(args[arg]) for arg in args if arg != "app_name"}

    current_node = None
    for node in scenario_nodes:
        if node["server_current_usage"] != {} and app_name in node["server_current_usage"]["apps"]:
            current_node = node["node_id"]
            break

    chosen_node = logic_app_placement(app_name, apps_dataset, scenario_nodes, kpis_user, current_node)

    if chosen_node == "NO_NODES_AVAILABLE":
        return f"No hay nodos edge disponibles para migrar la aplicación {app_name} con los requisitos especificados.", chosen_node

    return f"La aplicación {app_name} será migrada del nodo {current_node} al nodo edge {chosen_node}.", chosen_node

def stop_app_func(app_name: str, scenario_nodes: list) -> str:
    '''
    This function implements the logic to stop an application running on an edge node.
    
    :param app_name: Name of the application to be stopped
    :type app_name: str
    :return: Stop result message
    :rtype: str
    '''
    current_node = None
    for node in scenario_nodes:
        if node["server_current_usage"] != {} and app_name in node["server_current_usage"]["apps"]:
            current_node = node["node_id"]
            break
    
    return f"La aplicación {app_name} será detenida del nodo {current_node}.", "N/A"

def logic_app_placement(app_name: str, apps_data: dict, edge_nodes: list, kpis_user: dict={}, current_node: str=None) -> str:
    '''
    Logic to select the best edge node for deploying/migrating an application based on its requirements and user-defined KPIs.
    
    :param app_name: Name of the application to be deployed/migrated
    :type app_name: str
    :param apps_data: Dataset containing application requirements
    :type apps_data: dict
    :param edge_nodes: List of available edge nodes in the scenario
    :type edge_nodes: list
    :param kpis_user: User-defined KPIs for deployment/migration
    :type kpis_user: dict
    :param current_node: Current node where the application is deployed (if migrating)
    :type current_node: str
    :return: Selected edge node ID or error message
    :rtype: str
    '''

    if app_name not in apps_data:
        return "Aplicación no encontrada en el dataset."
    
    cpu_cores = apps_data[app_name]["min_requirements"]["cpu_cores"]
    ram_gb = apps_data[app_name]["min_requirements"]["ram_gb"]    

    free_nodes = task_select_nodes_with_resources(edge_nodes, cpu_cores, ram_gb, current_node)    

    if len(free_nodes) == 0:
        return "NO_NODES_AVAILABLE"
    
    app_category = apps_data[app_name]["category_5G"]
    nodes_valid = free_nodes.copy()
    nodes_filtered = free_nodes.copy()

    if len(kpis_user) > 0:
                print("[DEBUG]: User provided KPIs:", kpis_user)
                for kpi_name, kpi_value in kpis_user.items():
                    if kpi_name in KPIS_PREFERENCES[app_category]:                       
                        for node in nodes_valid:
                            if kpi_name in ["latency_ms", "packet_loss_percent"]:
                                if node["server_kpis"][kpi_name] > kpi_value:
                                    if node in nodes_filtered:
                                        nodes_filtered.remove(node)
                                        print(f"[DEBUG]: Node {node['node_id']} removed for not meeting {kpi_name} <= {kpi_value}")
                            else:
                                if node["server_kpis"][kpi_name] < kpi_value:
                                    if node in nodes_filtered:
                                        nodes_filtered.remove(node)
                                        print(f"[DEBUG]: Node {node['node_id']} removed for not meeting {kpi_name} >= {kpi_value}")
                if len(nodes_filtered) == 0:
                    return "NO_NODES_AVAILABLE"

    print(f"[DEBUG]: Nodes valid after filtering: {[node['node_id'] for node in nodes_filtered]}")
    if app_category == "uRLLC":
            print("[DEBUG]: App category uRLLC")          
            nodes_filtered.sort(key=lambda x: (
            KPIS_ORDER_OPERAND[KPIS_PREFERENCES[app_category][0]] * x["server_kpis"][KPIS_PREFERENCES[app_category][0]],  
            KPIS_ORDER_OPERAND[KPIS_PREFERENCES[app_category][1]] * x["server_kpis"][KPIS_PREFERENCES[app_category][1]],  
            KPIS_ORDER_OPERAND[KPIS_PREFERENCES[app_category][2]] * x["server_kpis"][KPIS_PREFERENCES[app_category][2]]))  

    elif app_category == "eMBB":
            print("[DEBUG]: App category eMBB")           
            nodes_filtered.sort(key=lambda x: (
                KPIS_ORDER_OPERAND[KPIS_PREFERENCES[app_category][0]] * x["server_kpis"][KPIS_PREFERENCES[app_category][0]],  
                KPIS_ORDER_OPERAND[KPIS_PREFERENCES[app_category][1]] * x["server_kpis"][KPIS_PREFERENCES[app_category][1]],  
                KPIS_ORDER_OPERAND[KPIS_PREFERENCES[app_category][2]] * x["server_kpis"][KPIS_PREFERENCES[app_category][2]]))  
        
    elif app_category == "mMTC":
            print("[DEBUG]: App category mMTC")
            nodes_filtered.sort(key=lambda x: (
                KPIS_ORDER_OPERAND[KPIS_PREFERENCES[app_category][0]] * x["server_kpis"][KPIS_PREFERENCES[app_category][0]],  
                KPIS_ORDER_OPERAND[KPIS_PREFERENCES[app_category][1]] * x["server_kpis"][KPIS_PREFERENCES[app_category][1]],  
                KPIS_ORDER_OPERAND[KPIS_PREFERENCES[app_category][2]] * x["server_kpis"][KPIS_PREFERENCES[app_category][2]]))  
 
    else :
        return "Categoría de aplicación no reconocida."

    return nodes_filtered[0]["node_id"] if nodes_filtered else "NO_NODES_AVAILABLE"

################################################ TASK 1: Complete Gemini 2.5 call functions ################################################
def gemini_call(tools_list, prompt) -> dict:
    '''You need to complete the call to Gemini 2.5 here, using the provided tools and prompt.'''

    # You need to create Tool object from the provided tools list
    tools =

    # Create config with tools and ensure that the model ALWAYS calls functions when needed
    config = {
        "tools": tools,
        "tool_config": {},  
    }

    response = client.models.generate_content(
        model="gemini-2.5-flash-lite",
        contents=prompt,
        config=config,
    )

    # Extract function calls from response
    function_calls = []
    if response.candidates:
        for candidate in response.candidates:
            if candidate.content and candidate.content.parts:
                for part in candidate.content.parts:
                    if part.function_call:
                        function_calls.append({
                            "function_name": part.function_call.name,
                            "args": dict(part.function_call.args) if part.function_call.args else {}
                        })
    
    # Extract token usage
    prompt_tokens = 0
    output_tokens = 0
    if response.usage_metadata:
        prompt_tokens = response.usage_metadata.prompt_token_count
        output_tokens = response.usage_metadata.candidates_token_count
    
    # Return structured result
    result = {
        "function": function_calls,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": output_tokens,
    }
    
    return result


def task_call_gemini(complete_system_prompt, deploy_app, migrate_app, stop_app):
    '''
    You need to call gemini_call from here, with the complete_system_prompt and the three functions as tools, and return the response.
    '''
    # Invoke gemini_call HERE with the appropriate parameters
    response = 
    return response

################################################################# END TASK 1 ###########################################################################################

################################################ TASK 2: Complete function call processing ################################################

def task_process_function_calls(function, apps_dataset: dict, scenario_nodes: list) -> str:
    '''You need to process each function call here, calling the appropriate function (deploy_app_func, migrate_app_func, stop_app_func) based on the function name, and return the chosen node and state.'''

    # Hint: you need to call the deploy_app_func, migrate_app_func and stop_app_func functions defined above, depending on the case.

    return state, chosen_node

########################################################### END TASK 2 #############################################################################################

########################################################## TASK 3: Complete app placement logic ##########################################################
def task_select_nodes_with_resources(edge_nodes: list, cpu_cores: int, ram_gb: int, current_node=None) -> list:
    '''You need to implement the logic to filter and return only the nodes that have enough CPU and RAM to host the application.'''

    # You need to add HERE the logic to choose just the nodes that have enough CPU and RAM to host the application, it does not matter if the app is already deployed in any node, we consider this node too if it has enough resources. We will remove the current node later if migrating.

    

    # The last step is remove current node from the list if we are migrating
    if current_node:
        print("[DEBUG]:Current node:", current_node)
        free_nodes = [node for node in free_nodes if node["node_id"] != current_node]

    return free_nodes
######################################################### END TASK 3 ##################################################################
################################################ TASK 4: Complete context prompt generation functions ################################################


# You can add HERE whatever helper functions you consider necessary

def task_generate_context_prompt(apps_dataset: dict, scenarios_dataset: dict, test_queries_dataset: dict, functions: dict, test_index: str) -> str:
    '''
    You need to generate the context prompt for Gemini 2.5 here, using whathever you consider necessary from the apps dataset, scenario nodes and test queries dataset.
    You can create helper functions if needed. Consider that this function will be called every time we execute a test, so the test_index parameter indicates which test we are executing.
    '''

    # Hint: You may reduce the initial prompt size by summarizing the datasets if needed, or selecting only the most relevant information to include in the prompt. You may also consider creating helper functions to format the datasets

    print(f"Generating context prompt for test: {test_index}...")

    # Yoy can add HERE whatever code you consider necessary to generate the context prompt

    context_prompt = "Eres un asistente para gestionar aplicaciones en una red de nodos edge. En tu base de datos tienes informacion de los siguientes nodos edge en diferentes escenarios: " + str(scenarios_dataset) + "\n\n En las cuales se pueden desplegar este tipo de aplicaciones siguientes aplicaciones: " + str(apps_dataset) + "Las reglas a seguir para desplegar o migrar un app en orden son: \n1. La app se debe desplegar en un nodo edge que tenga suficiente capacidad de CPU y memoria para soportar la app.\n2. En caso de haber dos nodos que soportan la app se seguiran las siguientes reglas segun su tipo de app:\n.1.Para las aplicaciones eMBB, típicamente orientadas a realidad aumentada o virtual, streaming de video de alta resolución y gaming, los KPIs se priorizan de la siguiente manera: en primer lugar, el throughput, dado que estas aplicaciones requieren grandes volúmenes de datos de manera sostenida; en segundo lugar, la capacidad de cómputo del servidor, necesaria para soportar renderizado y procesamiento intensivo; en tercer lugar, la latencia, seguida por el jitter; en quinto lugar, la confiabilidad y disponibilidad del servicio; en sexto lugar, la escalabilidad y capacidad de conexiones simultáneas; en séptimo lugar, la tasa de error (PER/BER); y finalmente, en octavo lugar, la eficiencia energética.\n2.Para las aplicaciones eMBB, típicamente orientadas a realidad aumentada o virtual, streaming de video de alta resolución y gaming, los KPIs se priorizan de la siguiente manera: en primer lugar, el throughput, dado que estas aplicaciones requieren grandes volúmenes de datos de manera sostenida; en segundo lugar, la capacidad de cómputo del servidor, necesaria para soportar renderizado y procesamiento intensivo; en tercer lugar, la latencia, seguida por el jitter; en quinto lugar, la confiabilidad y disponibilidad del servicio; en sexto lugar, la escalabilidad y capacidad de conexiones simultáneas; en séptimo lugar, la tasa de error (PER/BER); y finalmente, en octavo lugar, la eficiencia energética.\n3.Para las aplicaciones mMTC, orientadas a IoT masivo, smart cities o telemetría industrial, la prioridad de los KPIs es la siguiente: en primer lugar, la escalabilidad y número de conexiones simultáneas; en segundo lugar, la eficiencia energética de los dispositivos y la red; en tercer lugar, la confiabilidad y disponibilidad; en cuarto lugar, la tasa de error (PER/BER); en quinto lugar, la latencia; en sexto lugar, el jitter; en séptimo lugar, el throughput; y finalmente, en octavo lugar, la capacidad de cómputo del servidor."
    
    return context_prompt

########################################################### END TASK 4 #############################################################################################
                