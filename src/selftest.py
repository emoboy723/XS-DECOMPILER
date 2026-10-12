"""Integration tests for the shipped desktop and its bundled engines."""
import hashlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch, MagicMock
import zipfile
import engine


class Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.old_data = engine.DATA
        engine.DATA = Path(cls.temp.name) / 'data'
        engine.DATA.mkdir()

    @classmethod
    def tearDownClass(cls):
        engine.DATA = cls.old_data
        cls.temp.cleanup()

    def analyze(self, filename):
        job = engine.create_job(engine.ROOT/'samples'/filename)
        with patch.object(engine,'prepare_execution',side_effect=AssertionError('Seguro no prepara ejecución')):
            engine.analyze(job)
        self.assertEqual(job['status'],'completed',job['logs'])
        return job

    def test_java(self):
        job = self.analyze('Hello.class')
        self.assertEqual(job['metadata']['format'],'Java')
        files=list((engine.DATA/job['id']/'result').rglob('*.java'))
        self.assertTrue(any('multiply' in f.read_text() for f in files))

    def test_android_dex(self):
        job = self.analyze('classes.dex')
        self.assertEqual(job['metadata']['format'],'Android DEX')
        files=list((engine.DATA/job['id']/'result').rglob('*.java'))
        self.assertTrue(any('multiply' in f.read_text() for f in files))

    def test_dotnet_and_zip(self):
        job = self.analyze('Hello.dll')
        files=list((engine.DATA/job['id']/'result').rglob('*.cs'))
        self.assertTrue(any('Multiply' in f.read_text(encoding='utf-8-sig') for f in files))
        destination=Path(self.temp.name)/'results.zip'
        engine.export_results(job,destination)
        with zipfile.ZipFile(destination) as archive:
            self.assertIn('report.json',archive.namelist())
            self.assertTrue(any(n.endswith('.cs') for n in archive.namelist()))
            self.assertFalse(any(n.endswith('.dll') for n in archive.namelist()))

    def test_native_pe(self):
        job = self.analyze('NativeHost.bin')
        self.assertEqual(job['metadata']['engine'],'ghidra')
        output=engine.DATA/job['id']/'result/sources/decompiled.c'
        self.assertGreater(output.stat().st_size,1000)
        self.assertIn('Ghidra recovered pseudocode',output.read_text())

    def test_path_boundary_and_unknown_format(self):
        path=Path(self.temp.name)/'sample.txt'
        path.write_text('Known fixture, not executable.')
        job=engine.create_job(path)
        engine.analyze(job)
        self.assertEqual(job['status'],'partial')
        self.assertFalse(job['decompiled'])
        with self.assertRaises(ValueError):engine.safe_result(job,'../job.json')

    def pc_job(self):
        fixture=Path(self.temp.name)/'known-fixture.exe'
        shutil.copyfile(engine.ROOT/'samples/Hello.dll',fixture)
        job=engine.create_job(fixture,'normal','pc')
        job['metadata']={'format':'Windows .NET','sha256':hashlib.sha256(fixture.read_bytes()).hexdigest()}
        job['normal']=engine.prepare_execution(job,fixture)
        return job,fixture

    def test_pc_confirmation_and_launch_arguments(self):
        job,fixture=self.pc_job()
        with patch.object(engine.subprocess,'Popen') as launch:
            with self.assertRaises(ValueError):engine.launch(job,False)
            launch.assert_not_called()
        with patch.object(engine.subprocess,'Popen',return_value=MagicMock(pid=1234)) as launch,patch.object(engine.threading,'Thread'):
            self.assertEqual(engine.launch(job,True),1234)
            launch.assert_called_once_with([str(fixture)],cwd=fixture.parent)

    def test_changed_pc_file_blocked(self):
        job,fixture=self.pc_job()
        fixture.write_bytes(b'changed after analysis')
        with patch.object(engine.subprocess,'Popen') as launch:
            with self.assertRaises(ValueError):engine.launch(job,True)
            launch.assert_not_called()

    def test_sandbox_unavailable_and_restricted_config(self):
        job,fixture=self.pc_job()
        job['target']='vm'
        with patch.object(engine,'engines',return_value={'sandbox':False}),patch.object(engine.subprocess,'Popen') as launch:
            normal=engine.prepare_execution(job,fixture)
            self.assertFalse(normal['ready'])
            launch.assert_not_called()
        with patch.object(engine,'engines',return_value={'sandbox':True}),patch.object(engine.subprocess,'Popen') as launch:
            normal=engine.prepare_execution(job,fixture)
            self.assertTrue(normal['ready'])
            launch.assert_not_called()
        config=(engine.DATA/job['id']/'analysis.wsb').read_text()
        for item in ('<Networking>Disable</Networking>','<ReadOnly>true</ReadOnly>','<ClipboardRedirection>Disable</ClipboardRedirection>'):
            self.assertIn(item,config)

    def test_external_vm_export_does_not_execute(self):
        job,fixture=self.pc_job()
        job.update(target='vm',vm_kind='external')
        job['normal']=engine.prepare_execution(job,fixture)
        destination=Path(self.temp.name)/'vm.zip'
        with patch.object(engine.subprocess,'Popen') as launch:
            engine.export_vm(job,destination)
            launch.assert_not_called()
        with zipfile.ZipFile(destination) as archive:
            self.assertIn('sample.exe',archive.namelist())
            self.assertIn('Abrir-en-VM.ps1',archive.namelist())
            self.assertEqual(archive.read('sha256.txt').decode(),job['metadata']['sha256'])


def run(destination=None):
    stream=io.StringIO()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Integration))
    report={'success':result.wasSuccessful(),'tests':result.testsRun,'engines':engine.engines(),'details':stream.getvalue()}
    path=Path(destination) if destination else engine.ROOT/'VALIDACION.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if not result.wasSuccessful():raise SystemExit(1)
    return report


if __name__=='__main__':
    print(json.dumps(run(),ensure_ascii=False,indent=2))
