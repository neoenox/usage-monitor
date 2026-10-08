import time
import pytest
import monitor as m
import gui


@pytest.mark.parametrize('history', [[(None, 1)], [(time.time()-1000, float('nan')), (time.time(), 10)], [(time.time()-1000, 'bad')], [(True, 1)], [(time.time(), -1)], [None], None])
def test_bad_history_never_raises(history):
    for forecast in (m.quota_forecast, gui.quota_forecast):
        assert '不足' in forecast(20, 300, time.time()+5000, history)


@pytest.mark.parametrize('window', [None, 'bad', True, 0, -1, float('nan'), float('inf')])
def test_invalid_window_unavailable(window):
    assert '不足' in m.quota_forecast(20, window, time.time()+5000)
