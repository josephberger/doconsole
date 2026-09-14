import argparse

from doconsole import resolve_settings


def make_args(token=None, key=None, playbooks=None):
    return argparse.Namespace(token=token, key=key, playbooks=playbooks)


def test_cli_args_take_priority():
    args = make_args(token="cli-token", key="/cli/key", playbooks="/cli/playbooks")
    env = {"DO_API_TOKEN": "env-token", "DOCONSOLE_SSH_KEY": "/env/key", "DOCONSOLE_PLAYBOOKS_DIR": "/env/playbooks"}
    token, ssh_key, playbooks_dir = resolve_settings(args, env=env)
    assert (token, ssh_key, playbooks_dir) == ("cli-token", "/cli/key", "/cli/playbooks")


def test_env_used_when_no_cli_args():
    args = make_args()
    env = {"DO_API_TOKEN": "env-token", "DOCONSOLE_SSH_KEY": "/env/key", "DOCONSOLE_PLAYBOOKS_DIR": "/env/playbooks"}
    token, ssh_key, playbooks_dir = resolve_settings(args, env=env)
    assert (token, ssh_key, playbooks_dir) == ("env-token", "/env/key", "/env/playbooks")


def test_defaults_when_nothing_set():
    args = make_args()
    token, ssh_key, playbooks_dir = resolve_settings(args, env={})
    assert token is None
    assert ssh_key.endswith(".ssh/id_rsa") or ssh_key.endswith(".ssh\\id_rsa")
    assert playbooks_dir.endswith("playbooks")
