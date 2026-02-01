import os, json, operator
from typing import Annotated, List, Union, TypedDict, Optional

from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, END
from tools import update_routing_tool, fraud_mitigation_tool
from utils import get_active_policies_summary

from dotenv import load_dotenv

load_dotenv()

# Add .strip() to remove any invisible spaces or newlines
api_key = os.getenv("GROQ_API_KEY")
if api_key:
    os.environ["GROQ_API_KEY"] = api_key.strip()

llm = ChatOpenAI(
    model="meta-llama/llama-4-maverick-17b-128e-instruct", 
    api_key=os.getenv("GROQ_API_KEY"),
    base_url="https://api.groq.com/openai/v1", 
    temperature=0.5
)


class PaymentAgentState(TypedDict):
    latest_logs: List[dict]
    metrics: dict
    current_hypothesis: str
    is_anomaly_detected: bool
    next_action: Optional[str]
    decision_args: Optional[str]
    reasoning_log: Annotated[List[str], operator.add]
    
    # ADD THIS: Long-term memory of executed actions
    action_history: Annotated[List[str], operator.add]

# 2. The Checkpointer (The 'Pause' Button Logic)
# MemorySaver allows the graph to 'freeze' and wait for human input
# without losing its place in the loop.
checkpointer = MemorySaver()

# 3. File System Defaults
ROUTING_CONFIG_FILE = "routing_config.json"
DEFAULT_CONFIG = {
    "US": "stripe",
    "UK": "stripe",
    "IN": "stripe",
    "EU": "adyen",
    "global_default": "stripe"
}

# Ensure baseline config exists
if not os.path.exists(ROUTING_CONFIG_FILE):
    with open(ROUTING_CONFIG_FILE, "w") as f:
        json.dump(DEFAULT_CONFIG, f, indent=4)

# 4. Graph Export Helper (For the Mermaid live map in Streamlit)
def get_graph_diagram(compiled_graph):
    """Returns a Mermaid-compatible string to render the graph in UI."""
    return compiled_graph.get_graph().draw_mermaid()

def observer_node(state: PaymentAgentState):
    log_file = "transactions.log"
    recent_txs = []
    
    # Initialize the return dictionary with defaults to prevent KeyErrors
    output = {
        "latest_logs": [],
        "metrics": {"global_success_rate": 1.0, "failure_clusters": {}, "total_count": 0,"security_alerts": {}},
        "reasoning_log": [],
        "current_hypothesis": "Monitoring..."
    }

    if os.path.exists(log_file):
        with open(log_file, "r") as f:
            lines = f.readlines()[-100:]
            for line in lines:
                if not line.strip(): continue # Skip empty lines
                try:
                    # Robust split: Find the first '{' and take everything from there
                    json_start = line.find('{')
                    if json_start != -1:
                        json_str = line[json_start:]
                        recent_txs.append(json.loads(json_str))
                except Exception as e:
                    continue

    if not recent_txs:
        output["reasoning_log"] = ["Observer: No valid JSON transactions found in log yet."]
        return output

    # --- Calculation Logic ---
    total = len(recent_txs)
    successes = len([t for t in recent_txs if t['status'] == 'SUCCESS'])
    
    failure_map = {}
    security_map = {}
    for t in recent_txs:
        status = t.get('status', 'UNK')
        error_code = str(t.get('error_code', '00'))
        
        # 1. Track standard FAILED transactions (Outages/Auth issues)
        if status == 'FAILED':
            key = f"{t.get('region','UNK')}_{t.get('gateway','UNK')}_{error_code}"
            failure_map[key] = failure_map.get(key, 0) + 1
        
        # 2. Track REJECTED transactions (Spam/Carding Attacks)
        elif status == 'REJECTED' or error_code == '429':
            key = f"SPAM_ATTACK_{t.get('region','UNK')}"
            security_map[key] = security_map.get(key, 0) + 1
        

    output["latest_logs"] = recent_txs
    output["metrics"] = {
        "global_success_rate": successes / total,
        "failure_clusters": failure_map,
        "security_alerts": security_map,
        "total_count": total
    }
    log_msg = f"Observer: Parsed {total} txs."
    if security_map:
        log_msg += f" ALERT: Detected {sum(security_map.values())} potential spam attempts."
    output["reasoning_log"] = [f"Observer: Successfully parsed {total} transactions."]
    
    return output

def reasoner_node(state: PaymentAgentState):
    """
    Node 2: The LLM analyzes clusters to form a hypothesis.
    """
    metrics = state.get("metrics", {})
    clusters = metrics.get('failure_clusters', {})
    
    # Construct a clear snapshot for the LLM
    cluster_summary = json.dumps(clusters, indent=2)

    # UPDATE THIS IN REASONER_NODE
    prompt = f"""
    SYSTEM: You are a Payment Operations Diagnostic Engine.
    DATA SNAPSHOT:
    {cluster_summary}
    GLOBAL SUCCESS RATE: {metrics.get('global_success_rate', 0):.2%}
    SECURITY ALERTS: {metrics.get('security_alerts', {})}

    TASK:
    1. Identify if the current failures represent a "Technical Infrastructure Issue" or a "Malicious Traffic Pattern."
    2. Analyze error codes using your knowledge of fintech standards (ISO 8583, HTTP Status Codes).
    3. Determine the "blast radius" (is it one region, one gateway).
    4. Formulate a hypothesis that a Decider can use to pick a tool.

    OUTPUT FORMAT:
    Hypothesis: <Detailed diagnosis of root cause>
    Confidence: <0-100%>
    Anomaly Detected: <Yes/No>
    """

    # Call the LLM
    response = llm.invoke([
        SystemMessage(content="You analyze fintech logs for patterns."),
        HumanMessage(content=prompt)
    ])
    
    # Parse the LLM response (we can use simple string parsing for now)
    content = response.content
    is_anomaly = "Anomaly Detected: Yes" in content
    
    # Extract the hypothesis line for the UI
    hypothesis = "Monitoring..."
    for line in content.split("\n"):
        if line.startswith("Hypothesis:"):
            hypothesis = line.replace("Hypothesis:", "").strip()

    return {
        "current_hypothesis": hypothesis,
        "is_anomaly_detected": is_anomaly,
        "reasoning_log": [f"Reasoner: Analyzed clusters. Hypothesis: {hypothesis}"]
    }


def decider_node(state: PaymentAgentState):
    """Decides to call a tool OR alert the human."""
    hypothesis = state['current_hypothesis']
    history = state.get('action_history', [])
    active_securely = get_active_policies_summary()

    if not state['is_anomaly_detected']:
        return {"next_action": "MONITOR", "reasoning_log": ["Decider: No action needed."]}
    
    valid_regions = ["US", "UK", "IN", "EU"]

    # UPDATE THIS IN DECIDER_NODE
    prompt = f"""
    SYSTEM: You are the Autonomous Payment Ops Decision Maker.
    INPUT HYPOTHESIS: {hypothesis}
    ACTIVE POLICIES: {active_securely}
    PAST ACTIONS: {json.dumps(history[-5:])}

    AVAILABLE TOOLS:
    1. 'update_routing_tool': Best for fixing localized technical failures by moving traffic to a healthy partner.
    2. 'fraud_mitigation_tool': Best for neutralizing malicious traffic patterns or bot attacks at the edge.

    VALID REGIONS: {valid_regions}
    NOTE: Do NOT use 'global_default' as a target_region for fraud_mitigation_tool. 
    Apply blocks to specific affected regions only
    If the region (e.g., US) already has an active 'BLOCK_IP_RANGE', DO NOT call the tool again.
    
    MISSION:
    Choose the tool that best resolves the 'Hypothesis' provided. 
    - If the issue is technical, focus on continuity (Routing).
    - If the issue is malicious, focus on protection (Mitigation).
    - Avoid redundant actions if past actions haven't had time to take effect.

    DECISION:
    Does this situation require an automated intervention? If so, call the most appropriate tool with precise arguments.
    """

    llm_with_tools = llm.bind_tools([update_routing_tool, fraud_mitigation_tool])
    response = llm_with_tools.invoke(prompt)
    
    if response.tool_calls:
        tool_call = response.tool_calls[0]
        return {
            "next_action": tool_call['name'], # This will be 'fraud_mitigation_tool' or 'update_routing_tool'
            "decision_args": json.dumps(tool_call['args']),
            "reasoning_log": [f"Decider: Proposed {tool_call['name']} with {tool_call['args']}"]
        }
    
    return {"next_action": "ALERT_HUMAN", "reasoning_log": ["Decider: Alerting Human (No auto-fix)."]}

def sentry_node(state: PaymentAgentState):
    """
    Pass-through node that only exists to provide an interrupt point 
    for high-risk actions.
    """
    return state

def executor_node(state: PaymentAgentState):
    """Dynamically executes the tool chosen by the Decider."""
    tool_map = {
        "update_routing_tool": update_routing_tool,
        "fraud_mitigation_tool": fraud_mitigation_tool
    }

    # Extract the proposed tool name from the reasoning log or state
    # A cleaner way is to store the tool name in state['next_action']
    proposed_tool = state.get("next_action")
    args = json.loads(state['decision_args'])

    if proposed_tool in tool_map:
        result = tool_map[proposed_tool].invoke(args)
    else:
        # Fallback if the AI hallucinated a tool name
        return {"reasoning_log": [f"Executor Error: Tool '{proposed_tool}' not found."]}

    action_record = f"ACTION: {proposed_tool} | ARGS: {args} | RESULT: {result}"
    
    return {
        "reasoning_log": [f"Executor: {result}"],
        "action_history": [action_record] 
    }

workflow = StateGraph(PaymentAgentState)
workflow.add_node("observer", observer_node)
workflow.add_node("reasoner", reasoner_node)
workflow.add_node("decider", decider_node)
workflow.add_node("executor", executor_node)
workflow.add_node("sentry", sentry_node)

workflow.set_entry_point("observer")
workflow.add_edge("observer", "reasoner")
workflow.add_edge("reasoner", "decider")

def route_decision(state):
    target = state.get("next_action")
    
    if target == "update_routing_tool":
        return "executor"
    
    if target == "fraud_mitigation_tool":
        return "sentry"
    
    return END

workflow.add_conditional_edges(
    "decider",
    route_decision,
    {
        "executor": "executor",
        "sentry": "sentry",
        END: END
    }
)
workflow.add_edge("sentry", "executor")
workflow.add_edge("executor", END)

checkpointer = MemorySaver()
app = workflow.compile(checkpointer=checkpointer, interrupt_before=["sentry"])

