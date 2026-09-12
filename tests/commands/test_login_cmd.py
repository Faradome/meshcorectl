from __future__ import annotations

from meshcore import EventType
from meshcore.events import Event

from meshcorectl.cli import cli
from tests.conftest import invoke

CONTACTS_PAYLOAD = {
    "AA": {"adv_name": "rep1", "public_key": "AA", "type": 2, "out_path_len": 0, "lastmod": 1},
    "BB": {"adv_name": "rep2", "public_key": "BB", "type": 2, "out_path_len": 0, "lastmod": 2},
}


def script_contacts(fake_connection):
    fake_connection.commands.script("get_contacts", Event(EventType.CONTACTS, CONTACTS_PAYLOAD))


# --- login ------------------------------------------------------------------


def test_login_success_with_password_flag(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    fake_connection.commands.script("send_login_sync", Event(EventType.LOGIN_SUCCESS, {}))
    result = invoke(runner, configured_store, "login", "rep1", "--password", "secret")
    assert result.exit_code == 0, result.output
    assert "login ok" in result.output


def test_login_failure_message(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    fake_connection.commands.script("send_login_sync", Event(EventType.LOGIN_FAILED, {}))
    result = invoke(runner, configured_store, "login", "rep1", "--password", "wrong")
    assert result.exit_code == 0
    assert "login failed" in result.output


def test_login_timeout_errors(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    fake_connection.commands.script("send_login_sync", None)
    result = invoke(runner, configured_store, "login", "rep1", "--password", "secret")
    assert result.exit_code != 0
    assert "timed out" in result.output


def test_login_prompts_for_password_when_not_given(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    fake_connection.commands.script("send_login_sync", Event(EventType.LOGIN_SUCCESS, {}))
    result = runner.invoke(
        cli,
        ["--config", str(configured_store.path), "login", "rep1"],
        input="secret\n",
    )
    assert result.exit_code == 0, result.output
    assert "login ok" in result.output


def test_login_password_stdin(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    fake_connection.commands.script("send_login_sync", Event(EventType.LOGIN_SUCCESS, {}))
    result = runner.invoke(
        cli,
        ["--config", str(configured_store.path), "login", "rep1", "--password-stdin"],
        input="secret\n",
    )
    assert result.exit_code == 0, result.output
    assert "login ok" in result.output


def test_login_rejects_both_password_flags(runner, configured_store, fake_connection):
    result = invoke(
        runner,
        configured_store,
        "login",
        "rep1",
        "--password",
        "x",
        "--password-stdin",
    )
    assert result.exit_code != 0
    assert "pass only one of" in result.output


def test_login_requires_name_or_selector(runner, configured_store, fake_connection):
    result = invoke(runner, configured_store, "login", "--password", "x")
    assert result.exit_code != 0
    assert "pass exactly one of" in result.output


def test_login_unknown_contact_errors(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    result = invoke(runner, configured_store, "login", "nope", "--password", "x")
    assert result.exit_code != 0
    assert "no contact matching" in result.output


def test_login_by_selector(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    fake_connection.commands.script(
        "send_login_sync", Event(EventType.LOGIN_SUCCESS, {}), repeat=True
    )
    result = invoke(runner, configured_store, "login", "-l", "t=2", "--password", "x")
    assert result.exit_code == 0, result.output
    assert "rep1" in result.output and "rep2" in result.output


def test_login_bad_selector_errors(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    result = invoke(runner, configured_store, "login", "-l", "bogus", "--password", "x")
    assert result.exit_code != 0


def test_login_selector_matches_none(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    result = invoke(runner, configured_store, "login", "-l", "t=1", "--password", "x")
    assert result.exit_code == 0
    assert "No contacts matched" in result.output


def test_login_dry_run_skips_password_prompt_entirely(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    # No --password given and no input= piped in: if this tried to prompt,
    # it would hang or raise inside CliRunner (no stdin available).
    result = invoke(runner, configured_store, "login", "rep1", "--dry-run")
    assert result.exit_code == 0, result.output
    assert "would log into" in result.output
    assert fake_connection.commands.call_count("send_login_sync") == 0


# --- logout -----------------------------------------------------------------


def test_logout(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    fake_connection.commands.script("send_logout", Event(EventType.OK, {}))
    result = invoke(runner, configured_store, "logout", "rep1")
    assert result.exit_code == 0, result.output
    assert "logged out" in result.output


def test_logout_unknown_contact_errors(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    result = invoke(runner, configured_store, "logout", "nope")
    assert result.exit_code != 0
    assert "no contact matching" in result.output


def test_logout_error(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    fake_connection.commands.script("send_logout", Event(EventType.ERROR, {"reason": "nope"}))
    result = invoke(runner, configured_store, "logout", "rep1")
    assert result.exit_code != 0
    assert "nope" in result.output


def test_logout_dry_run(runner, configured_store, fake_connection):
    script_contacts(fake_connection)
    result = invoke(runner, configured_store, "logout", "rep1", "--dry-run")
    assert result.exit_code == 0, result.output
    assert "would log out" in result.output
    assert fake_connection.commands.call_count("send_logout") == 0
