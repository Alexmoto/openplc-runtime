import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from targetvisu.model import load_json
from targetvisu.project import load_project

class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'conf').mkdir()
        source = Path(__file__).parents[1]
        self.doc = load_json(source / 'example.targetvisu.json')
        self.debug = load_json(source / 'example.debug-map.json')
        data = (json.dumps(self.doc) + '\n').encode()
        (self.root / 'conf/targetvisu.json').write_bytes(data)
        (self.root / 'debug-map.json').write_text(json.dumps(self.debug))
        self.manifest = dict(version=1, target='native-x11', programMd5=self.debug['md5'],
                             documentMd5=hashlib.md5(data).hexdigest(), writableSymbols=[
                                 l['path'] for l in self.debug['leaves']])
        self.save()
    def save(self):
        (self.root / 'conf/targetvisu-project.json').write_text(json.dumps(self.manifest))
    def test_load(self):
        self.assertEqual(load_project(self.root).md5, self.debug['md5'])
    def test_document_changed(self):
        with (self.root / 'conf/targetvisu.json').open('ab') as f: f.write(b' ')
        with self.assertRaisesRegex(ValueError, 'Document / manifest'): load_project(self.root)
    def test_program_changed(self):
        self.manifest['programMd5'] = 'f' * 32; self.save()
        with self.assertRaisesRegex(ValueError, 'compiled program'): load_project(self.root)
    def test_missing_permissions(self):
        del self.manifest['writableSymbols']; self.save()
        with self.assertRaisesRegex(ValueError, 'permissions'): load_project(self.root)
    def test_denied_actions(self):
        self.manifest['writableSymbols'] = []; self.save()
        with self.assertRaisesRegex(ValueError, 'read-only'): load_project(self.root)
    def test_unknown_permission(self):
        self.manifest['writableSymbols'].append('unknown'); self.save()
        with self.assertRaisesRegex(ValueError, 'Unknown symbol'): load_project(self.root)
    def test_duplicate_permission(self):
        self.manifest['writableSymbols'].append(self.manifest['writableSymbols'][0].upper()); self.save()
        with self.assertRaisesRegex(ValueError, 'Duplicate'): load_project(self.root)
