from __future__ import annotations

import pytest
from meshcore import EventType
from meshcore.events import Event

from meshcorectl.connect import MeshCoreConnection
from tests.fakes.meshcore_double import FakeCommandHandler, FakeMeshCore


async def test_unscripted_call_raises_assertion_error():
    fake = FakeCommandHandler()
    with pytest.raises(AssertionError, match="no scripted result"):
        await fake.get_contacts()


async def test_scripted_single_result_without_repeat_raises_on_second_call():
    fake = FakeCommandHandler()
    fake.script("get_contacts", Event(EventType.CONTACTS, {"a": 1}))
    first = await fake.get_contacts()
    assert first.payload == {"a": 1}
    with pytest.raises(AssertionError):
        await fake.get_contacts()


async def test_scripted_result_with_repeat_returns_forever():
    fake = FakeCommandHandler()
    fake.script("get_contacts", Event(EventType.CONTACTS, {"a": 1}), repeat=True)
    for _ in range(3):
        result = await fake.get_contacts()
        assert result.payload == {"a": 1}


async def test_scripted_sequence_consumed_in_order():
    fake = FakeCommandHandler()
    fake.script(
        "get_msg",
        Event(EventType.CONTACT_MSG_RECV, {"text": "first"}),
        Event(EventType.CONTACT_MSG_RECV, {"text": "second"}),
    )
    first = await fake.get_msg()
    second = await fake.get_msg()
    assert first.payload["text"] == "first"
    assert second.payload["text"] == "second"


async def test_scripted_exception_is_raised():
    fake = FakeCommandHandler()
    fake.script("send_msg", TimeoutError("no ack"))
    with pytest.raises(TimeoutError, match="no ack"):
        await fake.send_msg("alice", "hi")


async def test_calls_are_recorded_with_args_and_kwargs():
    fake = FakeCommandHandler()
    fake.script("send_msg", Event(EventType.MSG_SENT, {}))
    await fake.send_msg("alice", msg="hi")
    assert fake.calls == [("send_msg", ("alice",), {"msg": "hi"})]
    assert fake.call_count("send_msg") == 1
    assert fake.call_count("get_contacts") == 0


def test_fake_mesh_core_has_sensible_defaults():
    fake = FakeMeshCore()
    assert fake.self_info["name"] == "test-node"
    assert isinstance(fake.commands, FakeCommandHandler)


def test_fake_mesh_core_records_subscriptions():
    fake = FakeMeshCore()

    def handler(event):
        pass

    fake.subscribe(EventType.ADVERTISEMENT, handler)
    assert fake.subscriptions == [(EventType.ADVERTISEMENT, handler)]


async def test_fake_mesh_core_disconnect_sets_flag():
    fake = FakeMeshCore()
    assert fake.disconnected is False
    await fake.disconnect()
    assert fake.disconnected is True


def test_fake_mesh_core_satisfies_the_connection_protocol():
    fake = FakeMeshCore()
    assert isinstance(fake, MeshCoreConnection)
