import json, os

def get_active_policies_summary():
    policy_file = "security_policy.json"
    if not os.path.exists(policy_file):
        return "No active security policies."
    
    with open(policy_file, "r") as f:
        try:
            policies = json.load(f)
            if not policies: return "No active security policies."
            summary = [f"- {p['action']} in {p['region']} (Started: {p['timestamp']})" for p in policies]
            return "\n".join(summary)
        except:
            return "Error reading security policies."
