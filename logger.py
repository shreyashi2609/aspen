import time
import random
import json
import logging
import os
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone

# --- CONFIGURATION ---
LOG_FILE = "transactions.log"
CONFIG_FILE = "routing_config.json"
MAX_BYTES = 10 * 1024 * 1024  # Increased to 10MB to handle spam bursts
BACKUP_COUNT = 1

# Setup the Rotating Logger
logger = logging.getLogger("PaymentSimulator")
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(LOG_FILE, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT)
logger.addHandler(handler)

DEFAULT_CONFIG = {
    "US": "stripe", "UK": "stripe", "IN": "stripe", "EU": "adyen", "global_default": "stripe"
}

GATEWAY_PROFILES = {
    "stripe": {"avg_latency": 150},
    "adyen": {"avg_latency": 310}
}

def get_routing_config():
    """Reads the current routing setup. If file doesn't exist, creates it."""
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CONFIG, f)
        return DEFAULT_CONFIG
    with open(CONFIG_FILE, "r") as f:
        return json.load(f)

def generate_transaction(scenario="normal"):

    config = get_routing_config()
    region = random.choice(["US", "UK", "IN", "EU"])
    gateway = config.get(region, config.get("global_default", "stripe"))
    profile = GATEWAY_PROFILES[gateway]
    
    if os.path.exists("security_policy.json"):
        with open("security_policy.json", "r") as f:
            try:
                policies = json.load(f)
                # Ensure we handle both a single dict or a list of dicts
                if isinstance(policies, dict): policies = [policies]
                
                for p in policies:
                    if scenario == "retry_storm" and (p["region"] == region or p["region"] == "global_default"):
                        return None
            except json.JSONDecodeError:
                pass

    status = "SUCCESS"
    error_code = "00"
    latency = profile["avg_latency"] + random.randint(-20, 50)

    # --- SCENARIO LOGIC ---
    if scenario == "retry_storm":
        # Simulate rate-limiting flagging the spammer
        status = "REJECTED"
        error_code = "429"  # Too Many Requests
        latency = 10  # Fast rejection

    elif scenario == "uk_bank_outage" and region == "UK" and gateway == "stripe":
        if random.random() > 0.3:
            status = "FAILED"
            error_code = "91"

    elif scenario == "adyen_latency_spike" and gateway == "adyen":
        status = "SUCCESS"
        latency = random.randint(5000, 9000)

    elif scenario == "india_auth_bug" and region == "IN" and gateway == "stripe":
        status = "FAILED"
        error_code = "401"

    return {
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "transaction_id": f"tx_{random.getrandbits(24)}",
        "gateway": gateway,
        "region": region,
        "status": status,
        "error_code": error_code,
        "latency_ms": latency,
        "amount": round(random.uniform(1.0, 10.0), 2) # Spam usually uses small amounts
    }

def main():
    print(f"📡 Simulator started. Scenarios: UK_OUTAGE, ADYEN_LATENCY, INDIA_AUTH, RETRY_STORM")
    scenarios = ["normal", "uk_bank_outage", "adyen_latency_spike", "india_auth_bug", "retry_storm"]

    try:
        while True:
            # Picking scenarios. Weighting RETRY_STORM at 0.1 for a quick burst
            current_mode = random.choices(
                scenarios, 
                weights=[0.4, 0.3, 0.1, 0.1, 0.1],
                k=1
            )[0]

            # SPECIAL HANDLING FOR SPAM: Generate 50 transactions at once if storm hits
            burst_size = 50 if current_mode == "retry_storm" else 1
            
            for _ in range(burst_size):
                tx = generate_transaction(scenario=current_mode)
                if tx is None:
                    # Optional: Print a 'Blocked' message so you see the tool working!
                    print("\033[94m[SECURITY] Blocked incoming spam attempt...\033[0m")
                    continue
                logger.info(json.dumps(tx))

                # Visual Feedback
                color = "\033[95m" if tx["status"] == "REJECTED" else "\033[92m" # Magenta for Spam
                if tx["status"] == "FAILED": color = "\033[91m"
                if tx["latency_ms"] > 1000: color = "\033[93m"
                print(f"{color}[{current_mode.upper()}] {tx['region']} | {tx['gateway']} | {tx['status']} | {tx['latency_ms']}ms\033[0m")
            
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nSimulation stopped.")

if __name__ == "__main__":
    main()
