import json
import os
import time

tokens_count_total = 0

def append_to_results_file(query:str, response: str, test_i: str, state: str, chosen_node: str="N/A"):
    '''
    Function to append results to a JSON file.
    
    :param query: The user query
    :type query: str
    :param response: The model response, with function calls
    :type response: str
    :param test_i: Test identifier
    :type test_i: str
    :param state: The result state after executing the function
    :type state: str
    :param chosen_node: The node chosen for the app placement
    :type chosen_node: str
    '''
    if "results.json" not in os.listdir():
        with open("results.json", "w") as f:
            json.dump({test_i: []}, f, indent=4)
    
    if os.path.getsize("results.json") == 0:
        with open("results.json", "w") as f:
            json.dump({test_i: []}, f, indent=4)

    with open("results.json", "r") as f:
        results_data = json.load(f)

        if test_i not in results_data:
            results_data[test_i] = []

    results_data[test_i].append({"query": query, "execution_result": {"function": response["function"]}, "chosen_node": chosen_node, "state": state})

    with open("results.json", "w") as f:
        json.dump(results_data, f, indent=4, ensure_ascii=False)

if __name__ == "__main__":    

    # See if we can import all the functions and variables from hackathon_functions.py
    try:
        from hackathon_functions import KPIS_PREFERENCES, KPIS_ORDER_OPERAND
    except ImportError:
        print("Error importing from hackathon_functions.py. Please ensure the file exists and contains the required variables.")
        exit(1)
        
    print("Imported KPIS_PREFERENCES and KPIS_ORDER_OPERAND from hackathon_functions.py successfully.")

    # Try to import functions from file
    try:
        with open("functions.json", "r") as f:
            functions = json.load(f)
        deploy_app = functions["deploy_app"]
        migrate_app = functions["migrate_app"]
        stop_app = functions["stop_app"]

    except FileNotFoundError:
        print("functions.json file not found. Please ensure it exists in the current directory.")
        exit(1)
    except KeyError as e:
        print(f"Key {e} not found in functions.json. Please ensure the file has the correct structure.")
        exit(1)
    print("Imported functions from functions.json successfully.") 

    # Import the other functions from this file
    try:
        from hackathon_functions import task_call_gemini, task_generate_context_prompt, task_process_function_calls, task_select_nodes_with_resources
    except ImportError:
        print("Error importing functions from hackathon_functions.py. Please ensure the file exists and contains the required functions.")
        exit(1)
    print("Imported functions from hackathon_functions.py successfully.")

    #------------------------------------------ NOW WE START THE TESTS ---------------------------------------------#
    # Delete previous results file if exists
    if "results.json" in os.listdir():
        os.remove("results.json")

    # Load scenarios, apps and functions datasets
    with open("apps.json", "r") as f:
        apps_dataset = json.load(f)

    with open("scenarios.json", "r") as f:
        scenarios_dataset = json.load(f)

    with open("test-queries-with-solutions.json", "r") as f:
        test_queries_dataset = json.load(f)

    #------------------------------- MAIN LOOP: EXECUTE TESTS --------------------------------#
    
    for test_i in test_queries_dataset.keys():    
        print(f"------------------------------- TEST: {test_i} -------------------------------\n")
        queries = [item["query"] for item in test_queries_dataset[test_i]]

        ###################################### TASK: GENERATE CONTEXT PROMPT ################################################
        context_prompt = task_generate_context_prompt(apps_dataset, scenarios_dataset, functions, test_i)
        ####################################### END TASK: GENERATE CONTEXT PROMPT ################################################
        
        #---------------------------- QUERIES LOOP: PROCESS EACH USER QUERY ------------------#
        for query in queries:
            complete_system_prompt = [
                {
                    "role": "model",
                    "parts": [
                        {
                        "text": context_prompt
                        }
                    ]
                },
            ]

            complete_system_prompt.append(
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": query
                        }
                    ]
                }
            )

            ############################################### TASK:CALL GEMINI WITH TOOLS ################################################
            response = task_call_gemini(
                complete_system_prompt=complete_system_prompt,
                deploy_app=deploy_app,
                migrate_app=migrate_app,
                stop_app=stop_app,
            )
            ###################################################### END TASK CALL GEMINI WITH TOOLS ################################################

            print(f"--- Query: {query} ---")
            print(f"Respuesta del modelo: {response} \n")
        
            # In case there is more than one function call in the response, we process them all
            states = []
            chosen_nodes = []

            ################################## TASK:PROCESS FUNCTION CALLS ################################################

            for function in response["function"]:
                state, chosen_node = task_process_function_calls(function, apps_dataset, scenarios_dataset[test_i])
            
            ################################## END TASK PROCESS FUNCTION CALLS ################################################
            
                # Append individual function result
                print(f"Resultado de la función: {state} \n")
                states.append(state)
                chosen_nodes.append(chosen_node)

            # Append results to file to analyze later
            append_to_results_file(query, response, test_i, states, chosen_nodes)
            tokens_count_total += response["prompt_tokens"] + response["completion_tokens"]

            # Sleep between queries to avoid rate limits
            time.sleep(1)

    print("-------------------------------------------------\n")
    print("TOTAL TOKENS USED SO FAR:", tokens_count_total)

