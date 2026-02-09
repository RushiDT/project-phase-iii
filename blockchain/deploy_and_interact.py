import os
import json
import time
import sys
from web3 import Web3
from solcx import compile_standard, install_solc

# Get the directory of the current script
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOL_FILE_PATH = os.path.join(BASE_DIR, "DeviceLog.sol")
CONFIG_FILE_PATH = os.path.join(BASE_DIR, "contract_config.json")

# Configuration (UPDATE THESE FROM GANACHE)
RPC_URL = "http://127.0.0.1:7545"
CHAIN_ID = 1337
# INSTRUCTIONS:
# 1. Open Ganache.
# 2. Look at the first account (Index 0).
# 3. Click the "Show Keys" icon (Key symbol) on the right side of that row.
# 4. Copy the "Private Key". It should look like "0x8f2..."
# 5. Paste it below inside the quotes.
PRIVATE_KEY = "0x3c8111d584d421b276e8d16dc4d4af3b1ae0ab64ff90a303c6beaa2ac325c70f"

# Install specific solc version
SOLC_VERSION = "0.8.0"
try:
    print(f"Ensuring Solidity compiler version {SOLC_VERSION} is installed...", file=sys.stderr)
    install_solc(SOLC_VERSION)
except Exception as e:
    print(f"Note: Could not explicitly install solc {SOLC_VERSION}. If it's already installed, this is fine. Error: {e}", file=sys.stderr)

def compile_contract():
    if not os.path.exists(SOL_FILE_PATH):
        raise FileNotFoundError(f"Missing Solidity file at: {SOL_FILE_PATH}")
        
    with open(SOL_FILE_PATH, "r") as f:
        source = f.read()

    compiled_sol = compile_standard(
        {
            "language": "Solidity",
            "sources": {"DeviceLog.sol": {"content": source}},
            "settings": {
                "outputSelection": {
                    "*": {
                        "*": ["abi", "metadata", "evm.bytecode", "evm.sourceMap"]
                    }
                }
            },
        },
        solc_version=SOLC_VERSION,
    )
    return compiled_sol

def deploy():
    print("Compiling contract...")
    compiled_sol = compile_contract()
    
    bytecode = compiled_sol["contracts"]["DeviceLog.sol"]["DeviceLog"]["evm"]["bytecode"]["object"]
    abi = compiled_sol["contracts"]["DeviceLog.sol"]["DeviceLog"]["abi"]

    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    if not w3.is_connected():
        print("Failed to connect to Ganache.", file=sys.stderr)
        return None, None

    print(f"Connected to Ganache. Deploying from {w3.eth.account.from_key(PRIVATE_KEY).address}...", file=sys.stderr)

    # Create contract
    DeviceLog = w3.eth.contract(abi=abi, bytecode=bytecode)
    
    # Build transaction
    nonce = w3.eth.get_transaction_count(w3.eth.account.from_key(PRIVATE_KEY).address)
    transaction = DeviceLog.constructor().build_transaction({
        "chainId": CHAIN_ID,
        "gasPrice": w3.eth.gas_price,
        "from": w3.eth.account.from_key(PRIVATE_KEY).address,
        "nonce": nonce
    })

    # Sign and Send
    signed_txn = w3.eth.account.sign_transaction(transaction, private_key=PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
    
    print("Waiting for deployment...")
    tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
    print(f"Contract Deployed at: {tx_receipt.contractAddress}")
    
    # Save address and ABI for other services to use
    config = {
        "contract_address": tx_receipt.contractAddress,
        "abi": abi
    }
    with open(CONFIG_FILE_PATH, "w") as f:
        json.dump(config, f, indent=2)
        
    return w3, tx_receipt.contractAddress

def log_anomaly(device_id, score, data_hash, batch_hash="NONE", event_type="ANOMALY"):
    # Load config
    try:
        with open(CONFIG_FILE_PATH, "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"Contract config not found at {CONFIG_FILE_PATH}. Run deploy() first.")
        return

    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    contract = w3.eth.contract(address=config["contract_address"], abi=config["abi"])
    
    nonce = w3.eth.get_transaction_count(w3.eth.account.from_key(PRIVATE_KEY).address)
    
    tx = contract.functions.addLog(
        device_id,
        int(score * 100),
        data_hash,
        batch_hash,
        event_type
    ).build_transaction({
        "chainId": CHAIN_ID,
        "gasPrice": w3.eth.gas_price,
        "from": w3.eth.account.from_key(PRIVATE_KEY).address,
        "nonce": nonce
    })
    
    signed_txn = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
    print(f"Anomaly logged to Blockchain! Tx: {receipt.transactionHash.hex()}", file=sys.stderr)

def _get_contract():
    """Helper to get contract instance."""
    try:
        with open(CONFIG_FILE_PATH, "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Contract config not found at {CONFIG_FILE_PATH}")
    
    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    contract = w3.eth.contract(address=config["contract_address"], abi=config["abi"])
    return w3, contract

def get_log_count():
    """Get total number of logs in blockchain."""
    try:
        _, contract = _get_contract()
        count = contract.functions.getLogCount().call()
        return count
    except Exception as e:
        print(f"Error getting log count: {e}", file=sys.stderr)
        return 0

def get_log(index):
    """Get a specific log by index."""
    try:
        _, contract = _get_contract()
        log = contract.functions.getLog(index).call()
        return {
            "timestamp": log[0],
            "device_id": log[1],
            "anomaly_score": log[2] / 100.0,  # Unscale
            "data_hash": log[3],
            "batch_hash": log[4],
            "event_type": log[5]
        }
    except Exception as e:
        print(f"Error getting log {index}: {e}", file=sys.stderr)
        return None

def get_all_logs(limit=100):
    """Get all logs from blockchain (up to limit) efficiently."""
    try:
        w3, contract = _get_contract()
        count = contract.functions.getLogCount().call()
        start = max(0, count - limit)
        
        logs = []
        for i in range(start, count):
            try:
                log = contract.functions.getLog(i).call()
                logs.append({
                    "timestamp": log[0],
                    "device_id": log[1],
                    "anomaly_score": log[2] / 100.0,
                    "data_hash": log[3],
                    "batch_hash": log[4],
                    "event_type": log[5]
                })
            except Exception as e:
                print(f"Error getting log {i}: {e}", file=sys.stderr)
        
        return logs
    except Exception as e:
        print(f"Error getting all logs: {e}", file=sys.stderr)
        return []

def get_trust_score(device_id):
    """Get trust score for a device from blockchain."""
    try:
        _, contract = _get_contract()
        score = contract.functions.deviceTrustScores(device_id).call()
        return score
    except Exception as e:
        print(f"Error getting trust score: {e}", file=sys.stderr)
        return 100  # Default trust score

if __name__ == "__main__":
    # If run directly, assume deployment mode
    if PRIVATE_KEY == "0x0000000000000000000000000000000000000000000000000000000000000000":
        print("PLEASE UPDATE PRIVATE_KEY in the script before running!")
    else:
        deploy()

