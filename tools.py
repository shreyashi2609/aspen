import json, os, random
from datetime import datetime
from langchain_core.tools import tool

@tool
def update_routing_tool(region: str, gateway: str):
    """
    Reroutes payment traffic for a specific region to a target gateway.
    Args:
        region: The geographical region (e.g., 'UK', 'US', 'EU', 'IN', 'global_default').
        gateway: The provider to use (e.g., 'stripe', 'adyen').
    """

    config_file = "routing_config.json"
    
    # 1. Read existing
    with open(config_file, "r") as f:
        config = json.load(f)
    
    # 2. Update
    if region == "global_default":
        config["global_default"] = gateway
    else:
        config[region] = gateway
        
    # 3. Save
    with open(config_file, "w") as f:
        json.dump(config, f, indent=4)
        
    return f"ACTION SUCCESS: {region} is now routed to {gateway}."

@tool
def fraud_mitigation_tool(action_type: str, target_region: str):
    """
    Triggers technical security interventions to protect the payment flow.
    
    Args:
        action_type: The specific security measure to deploy. 
                     Options: 
                     - 'BLOCK_IP_RANGE': Use for high-velocity bot/spam attacks (429 errors).
        target_region: The geographical region to protect (US, UK, IN, EU).
    """
    policy_file = "security_policy.json"
    
    # 1. Load existing policies or start with an empty list
    if os.path.exists(policy_file):
        with open(policy_file, "r") as f:
            try:
                policies = json.load(f)
                if not isinstance(policies, list): policies = []
            except:
                policies = []
    else:
        policies = []

    # 2. Create the new policy entry
    new_policy = {
        "id": f"rule_{random.getrandbits(16)}",
        "action": action_type,
        "region": target_region,
        "active": True,
        "timestamp": datetime.now().isoformat()
    }
    
    # 3. Add to the stack
    policies.append(new_policy)
    
    # 4. Save the full list
    with open(policy_file, "w") as f:
        json.dump(policies, f, indent=4)
        
    return f"SECURITY STACK UPDATED: Added {action_type} for {target_region}. Total active rules: {len(policies)}"
