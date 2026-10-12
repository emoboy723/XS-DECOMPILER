import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import engine
import external_tools as tools


class Combined(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        self.root=Path(self.temp.name); self.old=engine.DATA; engine.DATA=self.root/'data'
        self.old_jobs=dict(engine.JOBS); engine.JOBS.clear()
        api=self.root/'api'; (api/'binaryninja').mkdir(parents=True)
        (api/'binaryninja/__init__.py').write_text("""
from types import SimpleNamespace
class View:
    functions=[SimpleNamespace(name='fixture',start=4096,hlil=SimpleNamespace(root=SimpleNamespace(lines=['return 4;'])))]
    def __enter__(self):return self
    def __exit__(self,*args):pass
def load(path):return View()
""")
        gui=self.root/'dotpeek.exe'; gui.write_bytes(b'fixture')
        tools.save(engine.ROOT,engine.DATA,{**tools.DEFAULTS,'dotpeek':str(gui),'binaryninja_python':sys.executable,'binaryninja_api':str(api),'binaryninja_headless':True})
        self.execute=engine.execute_tool
        # Exercise coordination with a simulated Ghidra installation even in CI.
        self.ghidra_patch=patch.object(engine,'ghidra_home',return_value=self.root/'ghidra')
        self.ghidra_patch.start()
        self.java_patch=patch.object(engine,'java_path',return_value=str(self.root/'jdk/bin/java.exe'))
        self.java_patch.start()
        original_engines=engine.engines
        self.engines_patch=patch.object(engine,'engines',side_effect=lambda: {**original_engines(),'ghidra':True})
        self.engines_patch.start()

    def tearDown(self):
        self.engines_patch.stop(); self.ghidra_patch.stop(); self.java_patch.stop()
        engine.STOP_REQUESTED.clear()
        engine.DATA=self.old; engine.JOBS.clear(); engine.JOBS.update(self.old_jobs); self.temp.cleanup()

    def dispatch(self,args,output,timeout=300,env=None):
        if args[0]=='powershell.exe':
            Path(env['STRATA_SOURCE']).write_text('/* Ghidra fixture */\nreturn 3;')
            output.write_text('simulated Ghidra result')
            return 0
        return self.execute(args,output,timeout,env)

    def native(self):
        job=engine.create_job(engine.ROOT/'samples/NativeHost.bin',selected_engine='combined')
        with patch.object(engine,'execute_tool',side_effect=self.dispatch):engine.analyze(job)
        return job

    def test_two_motors_one_job_no_ranking(self):
        job=self.native()
        self.assertEqual(len(engine.JOBS),1)
        self.assertEqual([r['engine'] for r in job['motor_runs']],['ghidra','binaryninja'])
        self.assertTrue(all(r['status']=='código recuperado' for r in job['motor_runs']))
        result=engine.DATA/job['id']/'result'
        self.assertIn('return 3;',(result/'motors/ghidra/sources/decompiled.c').read_text())
        self.assertIn('return 4;',(result/'motors/binaryninja/sources/decompiled.c').read_text())
        self.assertNotIn('preferred',json.loads((result/'combined.json').read_text()))

    def test_one_motor_error_other_continues(self):
        def broken(args,output,timeout=300,env=None):
            if args[0]=='powershell.exe':raise RuntimeError('fixture failure')
            return self.execute(args,output,timeout,env)
        job=engine.create_job(engine.ROOT/'samples/NativeHost.bin',selected_engine='combined')
        with patch.object(engine,'execute_tool',side_effect=broken):engine.analyze(job)
        self.assertEqual(job['motor_runs'][0]['status'],'error')
        self.assertEqual(job['motor_runs'][1]['status'],'código recuperado')
        self.assertTrue(job['decompiled'])

    @unittest.skipUnless((engine.ROOT/"tools/ilspy/ilspycmd.exe").is_file(), "ILSpy integration requires the full portable tools")
    def test_dotnet_real_ilspy_manual_dotpeek(self):
        job=engine.create_job(engine.ROOT/'samples/Hello.dll',selected_engine='combined')
        engine.analyze(job)
        self.assertEqual([r['engine'] for r in job['motor_runs']],['ilspy','dotpeek'])
        self.assertEqual(job['motor_runs'][1]['status'],'exportación manual pendiente')
        files=list((engine.DATA/job['id']/'result/motors/ilspy/sources').rglob('*.cs'))
        self.assertTrue(any('Multiply' in p.read_text(encoding='utf-8-sig') for p in files))

    def test_unavailable_does_not_block(self):
        job=engine.create_job(engine.ROOT/'samples/Hello.dll',selected_engine='combined')
        job.pop('external_tools')
        with patch.object(engine,'engines',return_value={}),patch.object(engine.subprocess,'Popen') as launch:
            engine.analyze(job); launch.assert_not_called()
        self.assertTrue(all(r['status']=='sin configurar' for r in job['motor_runs']))
        self.assertFalse(job['decompiled'])

    def test_unknown_format_has_shared_inspection(self):
        sample=self.root/'unknown.txt'; sample.write_text('Harmless fixture')
        job=engine.create_job(sample,selected_engine='combined'); engine.analyze(job)
        self.assertEqual(job['motor_runs'],[])
        self.assertTrue((engine.DATA/job['id']/'result/combined-summary.txt').is_file())

    def test_export_contains_every_contribution(self):
        job=self.native(); zip_path=self.root/'all.zip'; engine.export_results(job,zip_path)
        with zipfile.ZipFile(zip_path) as z:
            self.assertIn('combined.json',z.namelist())
            self.assertIn('motors/ghidra/sources/decompiled.c',z.namelist())
            self.assertIn('motors/binaryninja/sources/decompiled.c',z.namelist())
            self.assertFalse(any(name.startswith('input/') for name in z.namelist()))

    def test_import_joins_shared_index_without_overwriting(self):
        job=self.native(); out=engine.DATA/job['id']/'result'
        original=(out/'motors/ghidra/sources/decompiled.c').read_bytes()
        source=self.root/'export'; source.mkdir(); (source/'manual.c').write_text('return 5;')
        target,count=tools.import_sources(source,out,'binaryninja')
        job['imports']=[{'tool':'binaryninja','path':target.relative_to(out).as_posix(),'files':count}]
        engine.write_combined_summary(job)
        report=json.loads((out/'report.json').read_text())
        self.assertEqual(len(report['motor_runs']),2); self.assertEqual(len(report['imports']),1)
        self.assertEqual((out/'motors/ghidra/sources/decompiled.c').read_bytes(),original)

    def test_normal_prepared_once_never_auto_executes_sample(self):
        job=engine.create_job(engine.ROOT/'samples/NativeHost.bin',mode='normal',selected_engine='combined')
        with patch.object(engine,'execute_tool',side_effect=self.dispatch),patch.object(engine,'prepare_execution',return_value={'ready':False}) as prepare:
            engine.analyze(job)
        prepare.assert_called_once()

    def test_stop_request_prevents_next_motor(self):
        calls=[]
        def stopping(args,output,timeout=300,env=None):
            calls.append(args)
            engine.STOP_REQUESTED.set()
            return self.dispatch(args,output,timeout,env)
        job=engine.create_job(engine.ROOT/'samples/NativeHost.bin',selected_engine='combined')
        with patch.object(engine,'execute_tool',side_effect=stopping):engine.analyze(job)
        self.assertEqual(len(calls),1)
        self.assertEqual(job['motor_runs'][1]['status'],'detenido')


if __name__=='__main__':
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Combined))
    (engine.ROOT/'VALIDACION-COMBINADO.json').write_text(json.dumps({'success':result.wasSuccessful(),'tests':result.testsRun,'engines':'ILSpy real; Ghidra and Binary Ninja simulated for combined dispatch tests'},indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
