import unittest
from unittest.mock import Mock, patch
from targetvisu.autostart import Supervisor

class AutoTests(unittest.TestCase):
    @patch('targetvisu.autostart.Runtime')
    @patch('targetvisu.autostart.load_project')
    @patch('targetvisu.autostart.fingerprint', return_value=b'one')
    @patch('targetvisu.autostart.subprocess.Popen')
    def test_run_stop_upload(self, spawn, fingerprint, load, runtime):
        spawn.side_effect = lambda *a, **kw: Mock(poll=Mock(return_value=None))
        s = Supervisor('/project', '/core', '/broker')
        s.tick()
        self.assertEqual(spawn.call_count, 2)
        children = list(s.children)
        s.tick()
        self.assertEqual(spawn.call_count, 2)
        fingerprint.return_value = b'two'
        s.retry_at = 0
        s.tick()
        self.assertEqual(spawn.call_count, 4)
        for child in children: child.terminate.assert_called_once()
        runtime.return_value.handshake.side_effect = ConnectionError('STOP')
        s.tick()
        self.assertEqual(s.children, [])
        runtime.return_value.handshake.side_effect = None
        s.retry_at = 0
        s.tick()
        self.assertEqual(spawn.call_count, 6)
        s.stop()

    @patch('targetvisu.autostart.fingerprint', side_effect=FileNotFoundError())
    @patch('targetvisu.autostart.subprocess.Popen')
    def test_missing_project_waits(self, spawn, fingerprint):
        s = Supervisor('/project', '/core', '/broker')
        s.tick()
        spawn.assert_not_called()
