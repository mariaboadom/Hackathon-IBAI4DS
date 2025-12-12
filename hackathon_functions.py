from google import genai
from google.genai import types
import os
import dotenv

dotenv.load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

#################################### TASK 0: Complete app placement logic ######################################################

# Define KPI preferences per application category
KPIS_PREFERENCES = {
    "uRLLC": ["latency_ms", "availability_percent", "packet_loss_percent"],

    "eMBB": ["throughput_mbps", "packet_loss_percent", "latency_ms"],

    "mMTC": ["connection_density", "energy_efficiency", "availability_percent"] 
}

# Add +1 if we order to prefer lower values, -1 if we prefer higher values
KPIS_ORDER_OPERAND = {
    "latency_ms": 1,
    "availability_percent": -1,
    "packet_loss_percent": 1,
    "throughput_mbps": -1,
    "connection_density": -1,
    "energy_efficiency": -1
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
    
    # First filter nodes that meet minimum CPU/RAM requirements 
    cpu_cores = apps_data[app_name]["min_requirements"]["cpu_cores"]
    ram_gb = apps_data[app_name]["min_requirements"]["ram_gb"]

    free_nodes = task_select_nodes_with_resources(edge_nodes, cpu_cores, ram_gb, current_node)

    # Remove current node from the list if migrating
    if current_node:
        print("[DEBUG]:Current node:", current_node)
        free_nodes = [node for node in free_nodes if node["node_id"] != current_node]

    if len(free_nodes) == 0:
        return "NO_NODES_AVAILABLE"
    
    # Now, complex selection Criteria: First filter by user KPIs, then sort by app category preferences
    app_category = apps_data[app_name]["category_5G"]
    nodes_valid = free_nodes.copy()
    nodes_filtered = free_nodes.copy()

    # If user provided KPIs, filter nodes first
    if len(kpis_user) > 0:
                print("[DEBUG]: User provided KPIs:", kpis_user)
                for kpi_name, kpi_value in kpis_user.items():
                    if kpi_name in KPIS_PREFERENCES[app_category]:                       
                        for node in nodes_valid:
                            # For latency and packet loss, we remove nodes that exceed the max value
                            if kpi_name in ["latency_ms", "packet_loss_percent"]:
                                if node["server_kpis"][kpi_name] > kpi_value:
                                    if node in nodes_filtered:
                                        # If node was not already removed
                                        nodes_filtered.remove(node)
                                        print(f"[DEBUG]: Node {node['node_id']} removed for not meeting {kpi_name} <= {kpi_value}")
                            else:
                                # For other KPIs, we remove nodes that are below the min value
                                if node["server_kpis"][kpi_name] < kpi_value:
                                    if node in nodes_filtered:
                                        # If node was not already removed
                                        nodes_filtered.remove(node)
                                        print(f"[DEBUG]: Node {node['node_id']} removed for not meeting {kpi_name} >= {kpi_value}")
                if len(nodes_filtered) == 0:
                    return "NO_NODES_AVAILABLE"

    # Now sort the remaining nodes per application category preferences
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
def gemini_api_call(tools_list, prompt):
    '''You need to complete the call to Gemini 2.5 here, using the provided tools and prompt.'''
    
    tools = types.Tool(function_declarations=tools_list)
    config = {
        "tools": [tools],
        "tool_config": {"function_calling_config": {"mode": "any"}},  #yo quitaria esto
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
    You need to call gemini_api_call from here, with the complete_system_prompt and the three functions as tools, and return the response.
    '''
    response = gemini_api_call(
    prompt=complete_system_prompt,
    tools_list=[deploy_app, migrate_app, stop_app],
    )
    return response

################################################################# END TASK 1 ###########################################################################################

################################################ TASK 2: Complete function call processing ################################################

def task_process_function_calls(function, apps_dataset: dict, scenario_nodes: list) -> str:
    '''You need to process each function call here, calling the appropriate function (deploy_app_func, migrate_app_func, stop_app_func) based on the function name, and return the chosen node and state.'''

    if function["function_name"] == "deploy_app":
        app_name = function["args"]["app_name"]
        args = function["args"]

        state, chosen_node = deploy_app_func(app_name, args, apps_dataset, scenario_nodes)

    elif function["function_name"] == "migrate_app":
        args = function["args"]
        app_name = function["args"]["app_name"]
        state, chosen_node = migrate_app_func(app_name, args, apps_dataset, scenario_nodes)

        
    elif function["function_name"] == "stop_app":
        args = function["args"]
        app_name = function["args"]["app_name"] 
        state, chosen_node = stop_app_func(app_name, scenario_nodes)

    else:
        state = "Función no reconocida."

    return state, chosen_node

########################################################### END TASK 2 #############################################################################################

########################################################## TASK 3: Complete app placement logic ##########################################################
def task_select_nodes_with_resources(edge_nodes: list, cpu_cores: int, ram_gb: int, current_node=None) -> list:
    '''You need to implement the logic to filter and return only the nodes that have enough CPU and RAM to host the application.'''
    free_nodes = []
    for node in edge_nodes:        
        if node["server_current_usage"] == {}:
            if node["server_capabilities"]["cpu_cores"] >= cpu_cores and node["server_capabilities"]["ram_gb"] >= ram_gb:
                free_nodes.append(node)
                print(f"[DEBUG]: Node {node['node_id']} is free and meets minimum resource requirements")
            else:
                print(f"[DEBUG]: Node {node['node_id']} is free but does not meet minimum resource requirements")

        elif node["server_capabilities"]["cpu_cores"] - node["server_current_usage"]["cpu_cores"] >= cpu_cores and \
           node["server_capabilities"]["ram_gb"] - node["server_current_usage"]["ram_gb"] >= ram_gb:
            free_nodes.append(node)
            print(f"[DEBUG]: Node {node['node_id']} has load and meets minimum resource requirements")
    
     # The last step is remove current node from the list if we are migrating
    if current_node:
        print("[DEBUG]:Current node:", current_node)
        free_nodes = [node for node in free_nodes if node["node_id"] != current_node]

    return free_nodes
######################################################### END TASK 3 ##################################################################
################################################ TASK 4: Complete context prompt generation functions ################################################

def get_useful_apps_info(apps: dict) -> dict:
    '''
    Transform apps dataset to get only name and description.
    
    :param apps: Apps dataset
    :type apps: dict
    :return: Transformed apps info, with only name and description
    :rtype: dict
    '''
    apps_info = []
    for app_name, app in apps.items():
        app_info = {
            "name": app_name,
            "desc": app["description"],
        }
        apps_info.append(app_info)

    return apps_info

def get_useful_nodes_info(scenario_nodes: list) -> list:
    '''
    Transform nodes dataset to get only node_id and deployed apps.
    
    :param scenario_nodes: List of available edge nodes in the scenario
    :type scenario_nodes: list
    :return: Transformed nodes info, with only node_id and deployed apps
    :rtype: list
    '''
    nodes_info = []
    for node in scenario_nodes:
        node_info = {
            "node_id": node["node_id"],
            "deployed_apps": node["server_current_usage"]["apps"] if node["server_current_usage"] != {} else [],
        }
        nodes_info.append(node_info)
    return nodes_info

def task_generate_context_prompt(apps_dataset: dict, scenarios_dataset: dict, functions: dict, test_index: str) -> str:
    '''
    You need to generate the context prompt for Gemini 2.5 here, using whathever you consider necessary from the apps dataset, scenario nodes and test queries dataset.
    You can create helper functions if needed.    '''

    print(f"Generating context prompt for test: {test_index}...")

    apps_name_description = get_useful_apps_info(apps_dataset)

    scenario_nodes = scenarios_dataset[test_index]
    useful_nodes_info = get_useful_nodes_info(scenario_nodes)

    context_prompt = f"Se pueden desplegar una de estas aplicaciones:"  + str(apps_name_description) 
    
    return context_prompt

########################################################### END TASK 4 #############################################################################################
                