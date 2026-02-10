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
PRIVATE_KEY = "0x4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d"

# Install specific solc version
SOLC_VERSION = "0.8.0"

def compile_contract():
    # Install specific solc version if needed
    try:
        # Only print if we're actually installing/checking (to stdout for debugging, or keep stderr)
        install_solc(SOLC_VERSION)
    except Exception:
        pass

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

def register_device(device_id, device_type, gateway_id):
    """Register a new device on the blockchain."""
    try:
        with open(CONFIG_FILE_PATH, "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        return {"error": "Contract not deployed"}

    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    contract = w3.eth.contract(address=config["contract_address"], abi=config["abi"])
    
    account = w3.eth.account.from_key(PRIVATE_KEY)
    nonce = w3.eth.get_transaction_count(account.address, 'pending')
    
    tx = contract.functions.registerDevice(
        device_id,
        device_type,
        gateway_id
    ).build_transaction({
        "chainId": CHAIN_ID,
        "gasPrice": w3.eth.gas_price,
        "from": account.address,
        "nonce": nonce
    })
    
    signed_txn = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
    print(f"Device {device_id} registered on Blockchain! Tx: {receipt.transactionHash.hex()}", file=sys.stderr)
    return {"tx_hash": receipt.transactionHash.hex()}

def _resolve_id(device_id):
    """Resolve a suffixed device ID to its registered base identity."""
    if not device_id or "_" not in device_id:
        return device_id
    
    parts = device_id.split("_")
    # For common patterns like esp8266_env_01_d969, take the first 3 segments
    if len(parts) >= 3:
        return "_".join(parts[:3])
    return device_id

def log_event(device_id, score, data_hash, batch_hash="NONE", event_type="SENSOR_DATA", gateway_id="unknown"):
    # Load config
    try:
        with open(CONFIG_FILE_PATH, "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"Contract config not found at {CONFIG_FILE_PATH}. Run deploy() first.", file=sys.stderr)
        return {"error": "Contract not deployed"}

    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    contract = w3.eth.contract(address=config["contract_address"], abi=config["abi"])
    
    account = w3.eth.account.from_key(PRIVATE_KEY)
    
    # Resolve ID to registered base identity
    resolved_id = _resolve_id(device_id)

    max_retries = 3
    for attempt in range(max_retries):
        try:
            # Random jitter to avoid simultaneous nonce requests
            import random
            time.sleep(random.uniform(0.1, 0.8))
            
            nonce = w3.eth.get_transaction_count(account.address, 'pending')
            
            tx = contract.functions.addLog(
                resolved_id,
                gateway_id,
                int(abs(score) * 100),
                data_hash,
                batch_hash,
                event_type
            ).build_transaction({
                "chainId": CHAIN_ID,
                "gasPrice": int(w3.eth.gas_price * 1.1), # Slight boost to avoid replacement issues
                "from": account.address,
                "nonce": nonce
            })
            
            signed_txn = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
            tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
            
            print(f"Event ({event_type}) for {resolved_id} logged to Blockchain! Tx: {receipt.transactionHash.hex()}", file=sys.stderr)
            return {"tx_hash": receipt.transactionHash.hex()}
        except Exception as e:
            if "transaction can't be replaced" in str(e) or "already known" in str(e) or "nonce too low" in str(e):
                if attempt < max_retries - 1:
                    print(f"Nonce collision detected (attempt {attempt+1}/{max_retries}), retrying...", file=sys.stderr)
                    time.sleep(1)
                    continue
            print(f"Blockchain logging failed: {e}", file=sys.stderr)
            return {"error": str(e)}

    return {"error": "Max retries exceeded"}

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
            "gateway_id": log[2],
            "anomaly_score": log[3] / 100.0,  # Unscale
            "data_hash": log[4],
            "batch_hash": log[5],
            "event_type": log[6]
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
                    "gateway_id": log[2],
                    "anomaly_score": log[3] / 100.0,
                    "data_hash": log[4],
                    "batch_hash": log[5],
                    "event_type": log[6]
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
        resolved_id = _resolve_id(device_id)
        _, contract = _get_contract()
        score = contract.functions.deviceTrustScores(resolved_id).call()
        return score if score > 0 else 100  # Default 100 for unregistered devices
    except Exception as e:
        print(f"Error getting trust score: {e}", file=sys.stderr)
        return 100  # Default trust score


# ==================== CONTROL COMMAND FUNCTIONS ====================

def request_control(device_id, user_id, command):
    """
    Request control of a device via blockchain.
    Returns dict with: approved, command_id, trust_score, tx_hash
    """
    try:
        with open(CONFIG_FILE_PATH, "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"Contract config not found. Run deploy() first.", file=sys.stderr)
        return {"approved": False, "error": "Contract not deployed"}

    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    contract = w3.eth.contract(address=config["contract_address"], abi=config["abi"])
    
    account = w3.eth.account.from_key(PRIVATE_KEY)
    nonce = w3.eth.get_transaction_count(account.address)
    
    # Build and send transaction
    tx = contract.functions.requestControl(
        device_id,
        user_id,
        command
    ).build_transaction({
        "chainId": CHAIN_ID,
        "gasPrice": w3.eth.gas_price,
        "from": account.address,
        "nonce": nonce
    })
    
    signed_txn = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    
    # Parse the event to get return values
    # Get the command count to find our command ID
    command_count = contract.functions.getCommandCount().call()
    command_id = command_count - 1
    
    # Get the command details to check if approved
    cmd = contract.functions.getCommand(command_id).call()
    approved = cmd[4]  # approved is at index 4
    trust_score = cmd[6]  # trustAtTime is at index 6
    
    print(f"Control request logged to blockchain. ID: {command_id}, Approved: {approved}, Trust: {trust_score}", file=sys.stderr)
    
    return {
        "approved": approved,
        "command_id": command_id,
        "trust_score": trust_score,
        "tx_hash": receipt.transactionHash.hex()
    }


def confirm_execution(command_id, success):
    """Confirm that a command was executed by the device."""
    try:
        with open(CONFIG_FILE_PATH, "r") as f:
            config = json.load(f)
    except FileNotFoundError:
        print(f"Contract config not found.", file=sys.stderr)
        return False

    w3 = Web3(Web3.HTTPProvider(RPC_URL))
    contract = w3.eth.contract(address=config["contract_address"], abi=config["abi"])
    
    account = w3.eth.account.from_key(PRIVATE_KEY)
    nonce = w3.eth.get_transaction_count(account.address)
    
    tx = contract.functions.confirmExecution(
        command_id,
        success
    ).build_transaction({
        "chainId": CHAIN_ID,
        "gasPrice": w3.eth.gas_price,
        "from": account.address,
        "nonce": nonce
    })
    
    signed_txn = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
    tx_hash = w3.eth.send_raw_transaction(signed_txn.raw_transaction)
    w3.eth.wait_for_transaction_receipt(tx_hash)
    
    print(f"Execution confirmed for command {command_id}: {'Success' if success else 'Failed'}", file=sys.stderr)
    return True


def get_command_history(device_id=None, limit=50):
    """Get command history from blockchain, optionally filtered by device."""
    try:
        _, contract = _get_contract()
        count = contract.functions.getCommandCount().call()
        start = max(0, count - limit)
        
        commands = []
        for i in range(start, count):
            try:
                cmd = contract.functions.getCommand(i).call()
                cmd_dict = {
                    "command_id": i,
                    "timestamp": cmd[0],
                    "device_id": cmd[1],
                    "user_id": cmd[2],
                    "command": cmd[3],
                    "approved": cmd[4],
                    "executed": cmd[5],
                    "trust_at_time": cmd[6]
                }
                # Filter by device if specified
                if device_id is None or cmd[1] == device_id:
                    commands.append(cmd_dict)
            except Exception as e:
                print(f"Error getting command {i}: {e}", file=sys.stderr)
        
        return commands
    except Exception as e:
        print(f"Error getting command history: {e}", file=sys.stderr)
        return []


def get_command_count():
    """Get total number of control commands in blockchain."""
    try:
        _, contract = _get_contract()
        return contract.functions.getCommandCount().call()
    except Exception as e:
        print(f"Error getting command count: {e}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    # Support CLI calls: python deploy_and_interact.py <function_name> <args...>
    if len(sys.argv) > 1:
        func_name = sys.argv[1]
        func_args = sys.argv[2:]
        
        # Map of available functions
        available_funcs = {
            "register_device": register_device,
            "log_event": log_event,
            "get_all_logs": get_all_logs,
            "get_trust_score": get_trust_score,
            "request_control": request_control,
            "confirm_execution": confirm_execution
        }
        
        if func_name in available_funcs:
            # Simple type conversion for numeric args
            processed_args = []
            for arg in func_args:
                try:
                    if '.' in arg: processed_args.append(float(arg))
                    else: processed_args.append(int(arg))
                except ValueError:
                    processed_args.append(arg)
            
            result = available_funcs[func_name](*processed_args)
            print(json.dumps(result))
        else:
            print(json.dumps({"error": f"Unknown function: {func_name}"}))
    else:
        # If run directly without args, default to deployment mode
        if PRIVATE_KEY == "0x0000000000000000000000000000000000000000000000000000000000000000":
            print("PLEASE UPDATE PRIVATE_KEY in the script before running!")
        else:
            deploy()

