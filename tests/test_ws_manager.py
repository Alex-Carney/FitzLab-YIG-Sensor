import pytest

from app.ws_manager import ConnectionManager


class FakeWS:
    def __init__(self, fail: bool = False):
        self.sent: list = []
        self.fail = fail

    async def send_json(self, data):
        if self.fail:
            raise RuntimeError("fake disconnect")
        self.sent.append(data)


@pytest.mark.asyncio
async def test_connect_disconnect_count():
    mgr = ConnectionManager()
    a = FakeWS()
    b = FakeWS()
    mgr.add(a)
    mgr.add(b)
    assert mgr.count() == 2
    mgr.remove(a)
    assert mgr.count() == 1


@pytest.mark.asyncio
async def test_broadcast_sends_to_all():
    mgr = ConnectionManager()
    a = FakeWS()
    b = FakeWS()
    mgr.add(a)
    mgr.add(b)
    await mgr.broadcast({"type": "trace", "data": {"x": 1}})
    assert a.sent == [{"type": "trace", "data": {"x": 1}}]
    assert b.sent == [{"type": "trace", "data": {"x": 1}}]


@pytest.mark.asyncio
async def test_broadcast_prunes_failed_clients():
    mgr = ConnectionManager()
    good = FakeWS()
    bad = FakeWS(fail=True)
    mgr.add(good)
    mgr.add(bad)
    await mgr.broadcast({"type": "ping"})
    assert good.sent == [{"type": "ping"}]
    assert mgr.count() == 1
