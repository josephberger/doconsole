import json
import os

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".doconsole")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
HISTORY_PATH = os.path.join(CONFIG_DIR, "history")
PROFILES_DIR = os.path.join(CONFIG_DIR, "profiles")

DEFAULTS = {
    "region": "nyc1",
    "size": "s-1vcpu-1gb",
    "image": "ubuntu-24-04-x64",
    "vpc_id": None,
    "ssh_key": None,
    "playbooks_dir": None,
    "attach_ssh_firewall": True,
    "token": None,
}


def _config_path(profile=None):
    if profile:
        return os.path.join(PROFILES_DIR, f"{profile}.json")
    return CONFIG_PATH


def load_config(profile=None):
    config = dict(DEFAULTS)
    try:
        with open(_config_path(profile), "r") as f:
            data = json.load(f)
        config.update({k: v for k, v in data.items() if k in DEFAULTS})
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return config


def save_config(config, profile=None):
    path = _config_path(profile)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {k: config.get(k) for k in DEFAULTS}
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
