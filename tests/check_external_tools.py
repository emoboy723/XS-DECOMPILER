import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import engine
import external_tools as tools


class External(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.root=Path(self.temp.name)
        self.data=self.root/'data'
        self.old=engine.DATA; engine.DATA=self.data
        self.api=self.root/'api'; (self.api/'binaryninja').mkdir(parents=True)
        (self.api/'binaryninja/__init__.py').write_text('')
        self.fake=self.root/'engine with spaces.exe'; self.fake.write_bytes(b'fixture')
        self.values={**tools.DEFAULTS,'dotpeek':str(self.fake),'binaryninja_gui':str(self.fake),'binaryninja_python':sys.executable,'binaryninja_api':str(self.api),'binaryninja_headless':True}

    def tearDown(self):
        engine.DATA=self.old; self.temp.cleanup()

    def test_settings_roundtrip_and_move(self):
        tools.save(engine.ROOT,self.data,self.values)
        self.assertEqual(tools.load(engine.ROOT,self.data),self.values)
        self.fake.unlink()
        self.assertFalse(tools.availability(engine.ROOT,self.values)['dotpeek'])

    def test_invalid_paths_and_headless_requirements(self):
        with self.assertRaises(ValueError):tools.save(engine.ROOT,self.data,{**tools.DEFAULTS,'dotpeek':'missing.exe'})
        with self.assertRaises(ValueError):tools.save(engine.ROOT,self.data,{**tools.DEFAULTS,'binaryninja_headless':True})

    def test_corrupt_settings(self):
        self.data.mkdir()
        (self.data/'external-tools.json').write_text('{"dotpeek":42}')
        with self.assertRaises(ValueError):tools.load(engine.ROOT,self.data)
        self.assertFalse(engine.engines()['dotpeek'])

    def test_no_headless_by_default(self):
        self.assertFalse(tools.availability(engine.ROOT,{**self.values,'binaryninja_headless':False})['binaryninja'])
        self.assertFalse(tools.discover(self.root)['binaryninja_headless'])

    def test_gui_launch_is_tool_not_sample(self):
        sample=self.root/'sample.dll'; sample.write_bytes(b'not executed')
        with patch.object(tools.subprocess,'Popen') as launch:
            tools.launch(engine.ROOT,self.values,'dotpeek',sample,'Windows .NET')
            self.assertEqual(launch.call_args.args[0],[str(self.fake),str(sample)])
            with self.assertRaises(ValueError):tools.launch(engine.ROOT,self.values,'dotpeek',sample,'Linux ELF')
        with patch.object(tools.subprocess,'Popen') as launch:
            with self.assertRaises(ValueError):tools.launch(engine.ROOT,tools.DEFAULTS,'binaryninja',sample,'Linux ELF')
            launch.assert_not_called()

    def test_selector_compatibility_and_missing(self):
        self.assertEqual(engine.engine_options('ilspy'),('ilspy','dotpeek'))
        self.assertEqual(engine.engine_options('ghidra'),('ghidra','binaryninja'))
        with self.assertRaises(ValueError):engine.create_job(engine.ROOT/'samples/Hello.class',selected_engine='dotpeek')
        with patch.object(engine,'engines',return_value={'binaryninja':False}):
            with self.assertRaises(ValueError):engine.create_job(engine.ROOT/'samples/NativeHost.bin',selected_engine='binaryninja')

    def test_dotpeek_job_does_not_auto_open(self):
        tools.save(engine.ROOT,self.data,self.values)
        job=engine.create_job(engine.ROOT/'samples/Hello.dll',selected_engine='dotpeek')
        with patch.object(engine.subprocess,'Popen') as launch:
            engine.analyze(job); launch.assert_not_called()
        self.assertFalse(job['decompiled'])
        self.assertIn('Export',job['notice'].replace('exportación','Export'))
        self.assertEqual(job['metadata']['engine'],'dotpeek')

    def test_import_copies_and_excludes_binaries(self):
        source=self.root/'export'; source.mkdir()
        (source/'Code.cs').write_text('class Example {}')
        (source/'Example.csproj').write_text('<Project/>')
        (source/'sample.dll').write_bytes(b'original')
        dest=self.root/'results'
        first,count=tools.import_sources(source,dest,'dotpeek')
        second,_=tools.import_sources(source,dest,'dotpeek')
        self.assertNotEqual(first,second); self.assertEqual(count,2)
        self.assertFalse((first/'sample.dll').exists())
        self.assertEqual((source/'Code.cs').read_text(),'class Example {}')
        self.assertIn('not verified',(first/'strata-import.json').read_text())
        with self.assertRaises(ValueError):tools.import_sources(dest,dest,'dotpeek')

    def test_import_empty_fails(self):
        source=self.root/'empty'; source.mkdir()
        with self.assertRaises(ValueError):tools.import_sources(source,self.root/'result','dotpeek')

    def fixture_api(self,fail=False):
        content="""
from types import SimpleNamespace
class View:
    functions=[SimpleNamespace(name='known_multiply',start=4096,hlil=SimpleNamespace(root=SimpleNamespace(lines=['return arg1 * arg2;']))) , SimpleNamespace(name='unknown',start=4100,hlil=None)]
    def __enter__(self):return self
    def __exit__(self,*args):pass
def load(path):return View()
"""
        if fail:content="def load(path):raise RuntimeError('simulated license failure')"
        (self.api/'binaryninja/__init__.py').write_text(content)

    def test_actual_adapter_process_and_dispatch(self):
        self.fixture_api()
        tools.save(engine.ROOT,self.data,self.values)
        job=engine.create_job(engine.ROOT/'samples/NativeHost.bin',selected_engine='binaryninja')
        engine.analyze(job)
        self.assertTrue(job['decompiled'])
        self.assertEqual(job['metadata']['engine'],'binaryninja')
        result=self.data/job['id']/'result/sources'
        self.assertIn('return arg1 * arg2;',(result/'decompiled.c').read_text())
        self.assertEqual(len(json.loads((result/'functions.json').read_text())['unrecovered']),1)

    def test_actual_adapter_failure_no_fake_success(self):
        self.fixture_api(fail=True)
        tools.save(engine.ROOT,self.data,self.values)
        job=engine.create_job(engine.ROOT/'samples/NativeHost.bin',selected_engine='binaryninja')
        engine.analyze(job)
        self.assertFalse(job['decompiled'])
        self.assertIn('API/licencia',job['notice'])
        self.assertIn('simulated license failure',(self.data/job['id']/'result/engine.log').read_text())

    def test_relative_portable_paths(self):
        self.assertEqual(tools.resolve(self.root,'api'),self.api.resolve())


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(External))
    report={'success':result.wasSuccessful(),'tests':result.testsRun,'external_engines_tested':'simulated API and GUI launch; no real dotPeek/Binary Ninja installed'}
    (engine.ROOT/'VALIDACION-MOTORES-EXTERNOS.json').write_text(json.dumps(report,indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
