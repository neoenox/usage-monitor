from gui import App


class _FakeApp:
    def __init__(self):
        self._tick_job = "stale-job"
        self._last = ({"has_rate": False}, {})
        self.scheduled = 0

    def _schedule_tick(self):
        self.scheduled += 1
        self._tick_job = "tracked-job"


def test_disconnected_tick_uses_single_tracked_scheduler():
    app = _FakeApp()

    App._tick(app)

    assert app.scheduled == 1
    assert app._tick_job == "tracked-job"
