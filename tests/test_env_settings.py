import argparse

from doconsole import resolve_settings


def make_args(token=None, key=None, playbooks=None):
    return argparse.Namespace(token=token, key=key, playbooks=playbooks)


def test_cli_args_take_priority():
    args = make_args(token="cli-token", key="/cli/key", playbooks="/cli/playbooks")
    env = {"DO_API_TOKEN": "env-token", "DOCONSOLE_SSH_KEY": "/env/key", "DOCONSOLE_PLAYBOOKS_DIR": "/env/playbooks"}
    token, ssh_key, playbooks_dir, auto_upload, default_tag = resolve_settings(args, env=env)
    assert (token, ssh_key, playbooks_dir) == ("cli-token", "/cli/key", "/cli/playbooks")
    assert auto_upload is True
    assert default_tag is None


def test_env_used_when_no_cli_args():
    args = make_args()
    env = {"DO_API_TOKEN": "env-token", "DOCONSOLE_SSH_KEY": "/env/key", "DOCONSOLE_PLAYBOOKS_DIR": "/env/playbooks"}
    token, ssh_key, playbooks_dir, auto_upload, default_tag = resolve_settings(args, env=env)
    assert (token, ssh_key, playbooks_dir) == ("env-token", "/env/key", "/env/playbooks")
    assert auto_upload is True
    assert default_tag is None


def test_defaults_when_nothing_set():
    args = make_args()
    token, ssh_key, playbooks_dir, auto_upload, default_tag = resolve_settings(args, env={})
    assert token is None
    assert ssh_key.endswith(".ssh/id_rsa") or ssh_key.endswith(".ssh\\id_rsa")
    assert playbooks_dir.endswith("playbooks")
    assert auto_upload is True
    assert default_tag is None


def test_auto_upload_ssh_key_can_be_disabled():
    args = make_args()
    for falsy in ("false", "0", "no", "off", "False", "OFF"):
        result = resolve_settings(args, env={"DOCONSOLE_AUTO_UPLOAD_SSH_KEY": falsy})
        assert result[3] is False, f"expected {falsy!r} to disable auto-upload"


def test_auto_upload_ssh_key_stays_on_for_truthy_values():
    args = make_args()
    for truthy in ("true", "1", "yes", "on", "True"):
        result = resolve_settings(args, env={"DOCONSOLE_AUTO_UPLOAD_SSH_KEY": truthy})
        assert result[3] is True, f"expected {truthy!r} to keep auto-upload on"


def test_default_tag_picked_up_from_env():
    args = make_args()
    _, _, _, _, default_tag = resolve_settings(args, env={"DOCONSOLE_DEFAULT_TAG": "doconsole"})
    assert default_tag == "doconsole"


def test_default_tag_blank_or_whitespace_is_none():
    args = make_args()
    for blank in ("", "   ", None):
        env = {"DOCONSOLE_DEFAULT_TAG": blank} if blank is not None else {}
        _, _, _, _, default_tag = resolve_settings(args, env=env)
        assert default_tag is None
