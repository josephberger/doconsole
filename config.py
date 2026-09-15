import json
import os

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".doconsole")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
HISTORY_PATH = os.path.join(CONFIG_DIR, "history")

DEFAULTS = {
    "region": "nyc1",
    "size": "s-1vcpu-1gb",
    "image": "ubuntu-24-04-x64",
    "vpc_id": None,
    "ssh_key": None,
    "playbooks_dir": None,
    "attach_ssh_firewall": True,
}


def load_config():
    config = dict(DEFAULTS)
    try:
        with open(CONFIG_PATH, "r") as f:
            data = json.load(f)
        config.update({k: v for k, v in data.items() if k in DEFAULTS})
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return config


def save_config(config):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    data = {k: config.get(k) for k in DEFAULTS}
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)
