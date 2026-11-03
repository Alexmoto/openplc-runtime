import copy
import unittest
from unittest.mock import Mock
from targetvisu.tests.test_targetvisu import fixture
from targetvisu.model import Model
from targetvisu.backend import Demo
from targetvisu.service import Engine


def navigation_model():
    original = fixture()
    doc = copy.deepcopy(original.doc)
    screen = copy.deepcopy(doc['screens'][0])
    screen.update(id='Details', name='Details', elements=[])
    doc['screens'].append(screen)
    button = next(e for e in doc['screens'][0]['elements'] if e['kind'] == 'button')
    button['action'] = dict(kind='navigate', target='Details', value=True)
    model = Model(doc, dict(version=2, md5=original.md5, leaves=list(original.leaves.values())))
    return model, button


class NavigationTests(unittest.TestCase):
    def test_navigation_does_not_resolve_screen_as_plc_symbol(self):
        model, button = navigation_model()
        self.assertNotIn('details', model.paths)
        backend = Demo(model)
        backend.write = Mock(wraps=backend.write)
        engine = Engine(model, backend)
        engine.tick()
        self.assertEqual(engine.request(dict(op='action', id=button['id']), 1), dict(ok=True, screen='Details'))
        backend.write.assert_not_called()

    def test_rejects_missing_target_and_non_button(self):
        for change in ('target', 'kind'):
            model, button = navigation_model()
            if change == 'target':
                button['action']['target'] = 'deleted'
            else:
                button['kind'] = 'text'
            with self.assertRaises(ValueError):
                Model(model.doc, dict(version=2, md5=model.md5, leaves=list(model.leaves.values())))

    def test_disabled_hidden_offline_do_not_navigate(self):
        for prop in ('enabled', 'visible', 'offline'):
            model, button = navigation_model()
            engine = Engine(model, Demo(model))
            engine.tick()
            if prop == 'offline':
                engine.error = 'Offline'
            else:
                button['bindings'][prop] = 'Pump1.StartRequest'
                engine.values['pump1.startrequest'] = False
            with self.assertRaises(ValueError):
                engine.request(dict(op='action', id=button['id']), 1)

    def test_navigation_releases_held_button(self):
        model, button = navigation_model()
        held = copy.deepcopy(button)
        held.update(id='held')
        held['action'] = dict(kind='momentary', target='Pump1.StartRequest', value=True)
        model.elements['held'] = held
        engine = Engine(model, Demo(model))
        engine.tick()
        engine.request(dict(op='action', id='held', pressed=True), 1)
        self.assertTrue(engine.leases)
        engine.request(dict(op='action', id=button['id']), 1)
        self.assertFalse(engine.leases)

if __name__ == '__main__':
    unittest.main()
