"""Model contracts with local simulated providers, and trusted JS fixtures only."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import zipfile
import ai_core as core
import deobfuscator
import engine


class Server:
    def __init__(self, mode='ok', provider='compatible'):
        self.mode, self.provider, self.received = mode, provider, []
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass
            def do_POST(self):
                body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                owner.received.append((self.path,body,self.headers.get('Authorization')))
                if owner.mode=='disconnect':
                    self.connection.close(); return
                if owner.mode=='slow':time.sleep(1)
                status=int(owner.mode) if owner.mode in ('401','403','429','500') else 200
                content=json.dumps({'summary':'Análisis de prueba','evidence':['fixture.js:1'],'uncertainties':[],
                                    'proposals':[{'file':'fixture.js','code':'const x = "ab";','reason':'Concatenación'}]})
                if owner.provider=='ollama':
                    response={'message':{'content':content},'done':True,'done_reason':'stop','prompt_eval_count':10,'eval_count':8}
                else:
                    response={'choices':[{'message':{'content':content},'finish_reason':'stop'}],
                              'usage':{'prompt_tokens':10,'completion_tokens':8,'total_tokens':18,'secret':'fixture-key'}}
                if owner.mode=='truncated':response['choices'][0]['finish_reason']='length'
                raw=b'not-json' if owner.mode=='invalid' else json.dumps(response).encode()
                try:
                    self.send_response(status); self.send_header('Content-Type','application/json')
                    self.send_header('Content-Length',str(len(raw))); self.end_headers(); self.wfile.write(raw)
                except (ConnectionError,OSError):pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.daemon_threads=True
        threading.Thread(target=self.server.serve_forever,daemon=True).start()
        self.connection={'name':'fixture','provider':provider,'url':f'http://127.0.0.1:{self.server.server_port}'+('/v1' if provider=='compatible' else ''),'model':'fixture-model'}
    def __enter__(self):return self
    def __exit__(self,*_args):self.server.shutdown(); self.server.server_close()


class AIIntegration(unittest.TestCase):
    def setUp(self):
        temp_root=engine.ROOT/'data'/'test-temp'
        temp_root.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=temp_root)
        self.folder=Path(self.temp.name)
        self.files=[{'name':'fixture.js','code':'const x = "a" + "b";'}]
        self.agent={'name':'Analista','role':'analista','instructions':'Explica el código','connection':'fixture'}
    def tearDown(self):self.temp.cleanup()

    def test_dpapi_settings_roundtrip_and_delete(self):
        settings=core.Settings(self.folder)
        conn=settings.set_connection({'name':'local','provider':'ollama','url':'http://localhost:11434','model':'fixture'},'not-a-real-api-key')
        raw=settings.path.read_text()
        self.assertNotIn('not-a-real-api-key',raw)
        loaded=core.Settings(self.folder)
        self.assertEqual(loaded.key(conn['id']),'not-a-real-api-key')
        loaded.set_connection(conn,None)
        self.assertEqual(loaded.key(conn['id']),'not-a-real-api-key')
        loaded.set_connection(conn,'')
        self.assertEqual(loaded.key(conn['id']),'')
        loaded.remove('connections',conn['id'])
        self.assertEqual(core.Settings(self.folder).values['connections'],[])

    def test_foreign_or_corrupt_dpapi_key_requires_reentry(self):
        ciphertext=core.protect('known-fixture')
        # Damaged DPAPI data exercises the same failure path as an unavailable user/machine key.
        damaged=ciphertext[:-8]+'AAAAAAAA'
        with self.assertRaises(ValueError):core.protect(damaged,True)
        settings=core.Settings(self.folder)
        connection=settings.set_connection({'name':'x','provider':'ollama','url':'http://localhost:11434','model':'x'},'fixture')
        with patch.object(core,'protect',side_effect=ValueError('Introdúcela de nuevo.')):
            with self.assertRaisesRegex(ValueError,'nuevo'):settings.key(connection['id'])

    def test_agent_configuration_and_connection_references(self):
        settings=core.Settings(self.folder)
        conn=settings.set_connection({'name':'one','provider':'compatible','url':'https://example.com/v1','model':'x'},'')
        agent=settings.set_agent(dict(self.agent,connection=conn['id']))
        self.assertEqual(core.Settings(self.folder).values['agents'][0],agent)
        with self.assertRaises(ValueError):settings.remove('connections',conn['id'])
        settings.remove('agents',agent['id']); settings.remove('connections',conn['id'])

    def test_url_validation(self):
        for url in ('http://example.com/v1','https://name:secret@example.com','https://example.com/?key=hidden','file:///tmp/test'):
            with self.assertRaises(ValueError):core.endpoint({'url':url,'model':'x','provider':'compatible'})
        for url in ('http://localhost:11434','http://127.0.0.1:11434','http://[::1]:11434'):
            _parts,path=core.endpoint({'url':url,'model':'x','provider':'ollama'})
            self.assertEqual(path,'/api/chat')

    def test_compatible_exact_payload_and_usage(self):
        messages=core.messages_for(self.agent,self.files,[])
        with Server() as server:
            output=core.request(server.connection,'fixture-key',messages,threading.Event())
            path,body,auth=server.received[0]
            self.assertEqual(path,'/v1/chat/completions')
            self.assertEqual(body['messages'],messages)
            self.assertEqual(auth,'Bearer fixture-key')
            self.assertNotIn('tools',body)
            self.assertEqual(output['usage'],{'prompt_tokens':10,'completion_tokens':8,'total_tokens':18})
            self.assertEqual(core.interpret(output['content'],self.files)['proposals'][0]['file'],'fixture.js')

    def test_ollama_contract(self):
        with Server(provider='ollama') as server:
            output=core.request(server.connection,'',core.messages_for(self.agent,self.files,[]),threading.Event())
            path,body,auth=server.received[0]
            self.assertEqual(path,'/api/chat'); self.assertFalse(body['stream']); self.assertEqual(body['format'],'json')
            self.assertIsNone(auth); self.assertEqual(output['usage']['eval_count'],8)

    def test_http_errors_disconnect_invalid_and_truncation(self):
        for mode in ('401','403','429','500','disconnect','invalid','truncated'):
            with self.subTest(mode=mode),Server(mode) as server:
                with self.assertRaises(core.ModelError):core.request(server.connection,'fixture-key',[],threading.Event())
                self.assertEqual(len(server.received),1)  # No automatic retries or extra calls.

    def test_cancellation_before_send_and_during_response(self):
        cancelled=threading.Event(); cancelled.set()
        with Server() as server:
            with self.assertRaises(core.Cancelled):core.request(server.connection,'',[],cancelled)
            self.assertEqual(server.received,[])
        with Server('slow') as server:
            cancel=threading.Event()
            threading.Timer(.15,cancel.set).start()
            start=time.monotonic()
            with self.assertRaises(core.Cancelled):core.request(server.connection,'',[],cancel)
            self.assertLess(time.monotonic()-start,.8)

    def test_timeout(self):
        with Server('slow') as server:
            with self.assertRaisesRegex(core.ModelError,'espera'):core.request(server.connection,'',[],threading.Event(),timeout=.2)

    def test_selection_previous_results_and_limits(self):
        messages=core.messages_for(self.agent,self.files,[{'agent':'prev','content':'known result'}])
        data=json.loads(messages[1]['content'])
        self.assertEqual(data['files'],self.files)
        self.assertEqual(data['previous_results'][0]['content'],'known result')
        with self.assertRaises(ValueError):core.Session(self.folder,[{'name':'a.js','code':'x'*48001}],[self.agent])
        with self.assertRaises(ValueError):core.Session(self.folder,self.files,[self.agent]*4)

    def test_copies_history_export_and_redaction(self):
        session=core.Session(self.folder,self.files,[self.agent])
        proposal=core.interpret(json.dumps({'summary':'x','proposals':[{'file':'fixture.js','code':'const x="ab";','reason':'simple'}]}),self.files)['proposals'][0]
        original=list(session.value['files'])
        dest=session.accept(proposal)
        self.assertEqual(session.value['files'],original)
        self.assertEqual(dest.read_text(),'const x="ab";')
        self.assertEqual(core.Session.load(session.folder/'session.json').value['accepted'],session.value['accepted'])
        archive=self.folder/'export.zip'; session.export(archive)
        with zipfile.ZipFile(archive) as exported:
            self.assertEqual(set(exported.namelist()),{'session.json','accepted/copia-1.js'})
            self.assertFalse(any('settings' in name for name in exported.namelist()))
        self.assertNotIn('fixture-key',core.redact('echo fixture-key',['fixture-key']))
        proposal['original_sha256']='wrong'
        with self.assertRaises(ValueError):session.accept(proposal)

    def test_invalid_proposals_and_nonstructured_response(self):
        for file in ('../secrets','C:/secrets','other.js'):
            result=core.interpret(json.dumps({'proposals':[{'file':file,'code':'x'}]}),self.files)
            self.assertEqual(result['proposals'],[])
        self.assertEqual(core.interpret('ordinary text',self.files)['proposals'],[])


class Deobfuscation(unittest.TestCase):
    def test_strings_unicode_escapes_and_integers(self):
        code=r'''const a = '\x68\u0069' + '世界'; const b = 2 * 3 + 4; const c = "a\n" + "b";'''
        result=deobfuscator.deobfuscate(code)
        self.assertIn('"hi\\u4e16\\u754c"',result['code'])
        self.assertIn('const b = 10;',result['code'])
        self.assertIn('"a\\nb"',result['code'])
        self.assertGreater(len(result['transformations']),2)

    def test_effects_dynamic_code_comments_and_unsafe_numbers_skipped(self):
        code='const a = f() + 2; const b = "x" + value; const c=9007199254740991+1; const d=2/*keep*/+3; eval(payload);'
        self.assertEqual(deobfuscator.deobfuscate(code)['code'],code)

    def test_directives_and_legacy_escapes_preserved(self):
        for code in (r'''"use\x20strict"; x=1;''', '''"use" + " strict"; x=1;''', r'''const x='\123';''',r'''const x='\uD800';'''):
            self.assertEqual(deobfuscator.deobfuscate(code)['code'],code)

    def test_incomplete_and_empty_input(self):
        self.assertEqual(deobfuscator.deobfuscate('const x = (')['code'],'const x = (')
        self.assertEqual(deobfuscator.deobfuscate('')['code'],'')

    def test_repeated_passes_stable(self):
        first=deobfuscator.deobfuscate('const v = "a" + "b" + "c"; const n=2+3+4;')['code']
        self.assertEqual(first,deobfuscator.deobfuscate(first)['code'])

    @unittest.skipUnless(shutil.which('node'),'Node no disponible para equivalencia de fixtures controlados')
    def test_trusted_fixture_equivalence(self):
        fixtures=[r'''const a='\x61'+'b'; const n=2*3+4; console.log(JSON.stringify([a,n]));''',
                  '''"use"+" strict"; x=1; console.log(x);''',
                  r'''const a='\x00'+'世界'; console.log(JSON.stringify(a));''']
        for original in fixtures:
            revised=deobfuscator.deobfuscate(original)['code']
            before=subprocess.run([shutil.which('node'),'-e',original],capture_output=True,timeout=10)
            after=subprocess.run([shutil.which('node'),'-e',revised],capture_output=True,timeout=10)
            self.assertEqual((before.returncode,before.stdout),(after.returncode,after.stdout))


def run(destination=None):
    stream=io.StringIO()
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromTestCase(cls) for cls in (AIIntegration,Deobfuscation))
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    report={'success':result.wasSuccessful(),'tests':result.testsRun,'skipped':len(result.skipped),'details':stream.getvalue(),
            'limitations':['Traslado real a otro usuario/PC no disponible: se probaron datos DPAPI dañados y el fallo simulado de descifrado.',
                            'APIs verificadas con servidores locales simulados; no se usaron claves ni proveedores de pago.']}
    path=Path(destination) if destination else engine.ROOT/'VALIDACION-IA.json'
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if not result.wasSuccessful():raise SystemExit(1)
    return report


if __name__=='__main__':
    print(json.dumps(run(),ensure_ascii=False,indent=2))
