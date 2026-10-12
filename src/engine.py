"""Strata desktop engine. No HTTP listener or browser is used."""
from datetime import datetime, timezone, timedelta
import hashlib
import io
import json
import math
import os
from pathlib import Path
import queue
import re
import shutil
import struct
import subprocess
import sys
import threading
import time
import uuid
import zipfile
from xml.sax.saxutils import escape
import external_tools

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]
DATA = ROOT / 'data'
JOBS = {}
LOCK = threading.RLock()
TASKS = queue.Queue(maxsize=8)
MAX_UPLOAD = 100 * 1024 * 1024
TOOL_PROCESSES = set()
STOP_REQUESTED = threading.Event()


def java_path():
    bundled = list((ROOT / 'runtime').glob('jdk*/bin/java.exe'))
    if bundled:
        return str(bundled[0])
    home = os.environ.get('JAVA_HOME', '')
    if home and (Path(home) / 'bin/java.exe').is_file():
        return str(Path(home) / 'bin/java.exe')
    # Prefer a JDK over the Windows Java 8 shim.
    candidates = sorted(Path('C:/Program Files/Java').glob('jdk-*/bin/java.exe'), reverse=True)
    return str(candidates[0]) if candidates else shutil.which('java')


def ghidra_home():
    bundled = list((ROOT / 'tools').glob('ghidra*_PUBLIC'))
    if bundled:
        return bundled[0]
    return Path(os.environ['GHIDRA_HOME']) if os.environ.get('GHIDRA_HOME') else None


def tool_environment(folder):
    env = os.environ.copy()
    env['DOTNET_ROOT'] = str(ROOT / 'runtime/dotnet')
    env['DOTNET_MULTILEVEL_LOOKUP'] = '0'
    env['DOTNET_CLI_TELEMETRY_OPTOUT'] = '1'
    if java_path():
        env['JAVA_HOME'] = str(Path(java_path()).parents[1])
    for kind in ('CONFIG', 'CACHE', 'TMP'):
        location = folder / ('jadx-' + kind.lower())
        location.mkdir(exist_ok=True)
        env[f'JADX_{kind}_DIR'] = str(location)
    return env


def engines():
    jars = list((ROOT / 'tools/jadx/lib').glob('jadx-*-all.jar'))
    ilspy = ROOT / 'tools/ilspy/ilspycmd.exe'
    ghidra = ghidra_home()
    headless = ghidra / 'support/analyzeHeadless.bat' if ghidra else None
    sandbox = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'System32/WindowsSandbox.exe'
    available={'jadx': bool(jars and java_path()), 'ilspy': ilspy.is_file(),
               'ghidra': bool(headless and headless.is_file() and java_path()), 'sandbox': sandbox.is_file()}
    try:available.update(external_tools.availability(ROOT,external_tools.load(ROOT,DATA)))
    except ValueError:available.update(dotpeek=False,binaryninja=False,binaryninja_gui=False)
    return available


def engine_options(default):
    return {'jadx':('jadx',),'ilspy':('ilspy','dotpeek'),'ghidra':('ghidra','binaryninja')}.get(default,())


def classify(data):
    if data[:4] == b'\xca\xfe\xba\xbe':
        return 'Java', 'jadx'
    if data[:4] == b'dex\n':
        return 'Android DEX', 'jadx'
    if data[:2] == b'PK':
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = z.namelist()
                if any(re.fullmatch(r'classes\d*\.dex', n) for n in names):
                    return 'Android APK', 'jadx'
                if any(n.endswith('.class') for n in names):
                    return 'Java JAR', 'jadx'
        except zipfile.BadZipFile:
            pass
        return 'Archivo ZIP', None
    if data[:2] == b'MZ':
        try:
            pe = struct.unpack_from('<I', data, 0x3c)[0]
            if data[pe:pe+4] != b'PE\0\0':
                return 'DOS', None
            optional = pe + 24
            magic = struct.unpack_from('<H', data, optional)[0]
            directory = optional + (112 if magic == 0x20b else 96)
            count = struct.unpack_from('<I', data, directory - 4)[0]
            cli, size = struct.unpack_from('<II', data, directory + 14 * 8) if count > 14 else (0, 0)
            return ('Windows .NET', 'ilspy') if cli and size else ('Windows PE nativo', 'ghidra')
        except struct.error:
            return 'PE incompleto', None
    if data[:4] == b'\x7fELF':
        return 'Linux ELF', 'ghidra'
    if data[:4] in (b'\xcf\xfa\xed\xfe', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf', b'\xfe\xed\xfa\xce'):
        return 'Mach-O', 'ghidra'
    return 'Formato no reconocido', None


def save(job):
    with LOCK:
        (DATA / job['id'] / 'job.json').write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding='utf-8')


def update(job, **fields):
    with LOCK:
        job.update(fields)
        save(job)


def log(job, message):
    with LOCK:
        job['logs'].append({'time': datetime.now(timezone(timedelta(hours=-7))).strftime('%H:%M:%S'), 'message': message})
        save(job)


def execute_tool(args, output, timeout=300, env=None):
    """Only trusted engines are executed. Never use a sample as a program."""
    if STOP_REQUESTED.is_set():raise RuntimeError('Se solicitó detener los motores.')
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    with output.open('w', encoding='utf-8') as stream:
        proc = subprocess.Popen(args, stdout=stream, stderr=subprocess.STDOUT,
                                cwd=ROOT, creationflags=flags, env=env)
        with LOCK:
            TOOL_PROCESSES.add(proc)
        try:
            return proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'],
                               capture_output=True, creationflags=flags)
            else:
                proc.kill()
            proc.wait()
            raise RuntimeError('El motor superó el límite de 5 minutos. Consulta engine.log.')
        finally:
            with LOCK:
                TOOL_PROCESSES.discard(proc)


def decompile_motor(job,motor,folder,sample,out):
    update(job, phase=f'Decompilando con {motor.upper()}')
    log(job, f'Iniciando {motor.upper()}; la muestra no se ejecuta en el equipo anfitrión.')
    code = out / 'sources'
    code.mkdir(exist_ok=True)
    if motor == 'jadx':
        jar = next((ROOT / 'tools/jadx/lib').glob('jadx-*-all.jar'))
        args = [java_path(), '-Xmx2g', '-cp', str(jar), 'jadx.cli.JadxCLI',
                '--config', 'none', '-j', '2', '-d', str(code), str(sample)]
    elif motor == 'ilspy':
        args = [str(ROOT / 'tools/ilspy/ilspycmd.exe'), '--disable-updatecheck', '-p', '-o', str(code), str(sample)]
    elif motor == 'binaryninja':
        args=external_tools.binaryninja_command(ROOT,job['external_tools'],sample,code)
    else:
        # Ghidra is a trusted optional engine. Wrapper receives only fixed paths.
        project = folder / 'ghidra-project'
        project.mkdir(exist_ok=True)
        env = tool_environment(folder)
        env['GHIDRA_HOME'] = str(ghidra_home())
        env['JAVA_HOME_OVERRIDE'] = env['JAVA_HOME']
        ghidra_state = folder / 'ghidra-state'
        ghidra_state.mkdir(exist_ok=True)
        env['GHIDRA_HEADLESS_JAVA_OPTIONS'] = ' '.join(f'-Dapplication.{kind}dir="{ghidra_state}"' for kind in ('settings', 'cache', 'temp'))
        env['STRATA_SAMPLE'] = str(sample)
        env['STRATA_PROJECT'] = str(project)
        env['STRATA_SOURCE'] = str(code / 'decompiled.c')
        args = None
        rc = execute_tool(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(ROOT / 'scripts/ghidra.ps1')],
                          out / 'engine.log', env=env)
    if args:
        env = tool_environment(folder)
        rc = execute_tool(args, out / 'engine.log', env=env)
    decompiled = any(p.is_file() and p.suffix in ('.java', '.cs', '.c') for p in code.rglob('*'))
    log(job, f'Motor finalizado con código {rc}.')
    if rc:
        log(job, 'El motor reportó errores; revisa engine.log. Puede haber código parcial.')
        if motor=='binaryninja':job['notice']='Binary Ninja no completó el análisis. Revisa engine.log y tu configuración de API/licencia.'
    return decompiled,rc


def write_combined_summary(job):
    """All contributions share an index, without ranking or merging source versions."""
    out=DATA/job['id']/'result'
    runs=job.get('motor_runs',[])
    imports=job.get('imports',[])
    value={'format':job.get('metadata',{}).get('format'),'engines':runs,'imports':imports,
           'policy':'All compatible configured motors; no automatic ranking or source merging.'}
    (out/'combined.json').write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['ANÁLISIS COMBINADO',job['name'],'','Todos los aportes aparecen juntos. No se prioriza ni se fusiona el código de ningún motor.','']
    for run in runs:
        lines.append(f"{run['engine'].upper()} · {run['status']} · {run.get('source_files',0)} archivos de código")
        if run.get('path'):lines.append('  Resultados: '+run['path'])
        if run.get('reason'):lines.append('  '+run['reason'])
    if not runs:lines.append('El formato no tiene un motor de decompilación compatible; se conserva la inspección local.')
    if imports:
        lines.extend(['','APORTES IMPORTADOS'])
        for item in imports:lines.append(f"{item['tool'].upper()} · {item['files']} archivos · {item['path']}\n  Correspondencia con el binario declarada por el usuario; no verificada.")
    lines.extend(['','Cada versión conserva su procedencia y sus registros.','Puedes seleccionar aportes de varios motores para Revisar con IA; el envío requiere revisar el mensaje.','dotPeek utiliza exportación manual. Binary Ninja automático requiere una API/licencia compatible.'])
    (out/'combined-summary.txt').write_text('\n'.join(lines),encoding='utf-8')
    report=out/'report.json'
    if report.exists():
        existing=json.loads(report.read_text(encoding='utf-8'))
        existing['motor_runs']=runs; existing['imports']=imports
        report.write_text(json.dumps(existing,ensure_ascii=False,indent=2),encoding='utf-8')


def decompile_combined(job,default,folder,sample,out,available):
    job['motor_runs']=[]
    recovered=False
    for motor in engine_options(default):
        run={'engine':motor,'status':'pendiente','source_files':0}
        job['motor_runs'].append(run)
        if STOP_REQUESTED.is_set():
            run.update(status='detenido',reason='Se solicitó detener el análisis; este motor no se inicia.')
        elif not available.get(motor):
            run.update(status='sin configurar',reason='Motor no instalado/configurado. Los demás motores continúan.')
        elif motor=='dotpeek':
            run.update(status='exportación manual pendiente',reason='Abre dotPeek, usa Export to Project e importa el código al mismo análisis.')
        else:
            work=folder/'motor-work'/motor; work.mkdir(parents=True,exist_ok=True)
            result=out/'motors'/motor; result.mkdir(parents=True,exist_ok=True)
            run['path']=result.relative_to(out).as_posix()
            try:
                run['status']='analizando'
                write_combined_summary(job)
                ok,rc=decompile_motor(job,motor,work,sample,result)
                count=sum(1 for p in (result/'sources').rglob('*') if p.is_file() and p.suffix.lower() in ('.java','.cs','.c','.h','.cpp'))
                run.update(status='código parcial' if ok and rc else 'código recuperado' if ok else 'sin código',source_files=count,exit_code=rc)
                if rc:run['reason']='El motor reportó errores. Consulta '+run['path']+'/engine.log.'
                recovered=recovered or ok
            except Exception as exc:
                run.update(status='error',reason=str(exc))
                log(job,f'{motor.upper()}: {exc}. Continúa el análisis combinado.')
        write_combined_summary(job)
        save(job)
    # Per-motor notices belong in the shared index, not as a misleading global failure.
    job.pop('notice',None)
    write_combined_summary(job)
    return recovered


def analyze(job):
    folder = DATA / job['id']
    sample = folder / 'input' / job['name']
    out = folder / 'result'
    out.mkdir(exist_ok=True)
    update(job, status='running', phase='Identificando archivo')
    data = sample.read_bytes()
    fmt, motor = classify(data)
    requested=job.get('requested_engine','auto')
    default=motor
    if requested not in ('auto','combined'):
        if requested not in engine_options(motor):raise ValueError('El motor elegido no es compatible con este archivo.')
        motor=requested
    elif requested=='combined':motor='combined'
    counts = [data.count(i) for i in range(256)]
    entropy = -sum((c/len(data))*math.log2(c/len(data)) for c in counts if c) if data else 0
    strings = [s.decode('ascii') for s in re.findall(rb'[\x20-\x7e]{5,}', data)[:10000]]
    metadata = {'name': job['name'], 'size': len(data), 'format': fmt, 'engine': motor,
                'sha256': hashlib.sha256(data).hexdigest(), 'entropy': round(entropy, 3),
                'strings_count': len(strings), 'mode': job['mode']}
    update(job, metadata=metadata)
    (out / 'strings.txt').write_text('\n'.join(strings), encoding='utf-8')
    (out / 'hex.txt').write_text('\n'.join(f'{i:08x}  {data[i:i+16].hex(" "):<47}  ' + ''.join(chr(b) if 32 <= b <= 126 else '.' for b in data[i:i+16]) for i in range(0, min(len(data), 65536), 16)), encoding='utf-8')
    log(job, f'{fmt} · SHA-256 calculado · {len(data):,} bytes')
    if data[:2] == b'PK':
        with zipfile.ZipFile(sample) as z:
            (out / 'archive-index.txt').write_text('\n'.join(f'{i.file_size:>12}  {i.filename}' for i in z.infolist()[:20000]), encoding='utf-8')
    available = engines()
    if job.get('external_tools'):
        available.update(external_tools.availability(ROOT,job['external_tools']))
    decompiled = False
    if motor=='combined':
        decompiled=decompile_combined(job,default,folder,sample,out,available)
    elif motor=='dotpeek':
        reason='dotPeek requiere exportación desde su interfaz. Pulsa Análisis avanzado y después Importar código exportado.'
        log(job,reason)
        job['notice']=reason
    elif motor and available.get(motor):
        decompiled,rc=decompile_motor(job,motor,folder,sample,out)
    else:
        reason = f'Configura {motor.upper()} para decompilar este formato.' if motor else 'Este formato no tiene un motor de decompilación compatible.'
        log(job, reason)
        job['notice'] = reason
    normal = None
    if job['mode'] == 'normal':
        normal = prepare_execution(job, sample)
    report = {**metadata, 'decompiled': decompiled, 'normal': normal,
              'notes': ['El código recuperado puede diferir del original; la ofuscación y las optimizaciones limitan el resultado.',
                        'Las cadenas y la entropía son datos de inspección, no pruebas de comportamiento.',
                        'El análisis estático no ejecuta la muestra; los parsers pueden tener vulnerabilidades.']}
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    if motor=='combined':write_combined_summary(job)
    update(job, status='completed' if decompiled else 'partial', phase='Análisis terminado',
           decompiled=decompiled, normal=normal, finished=time.time())


def prepare_sandbox(job, sample):
    # No sample is ever launched automatically on the host.
    if sample.suffix.lower() != '.exe' or not job['metadata']['format'].startswith('Windows'):
        log(job, 'La ejecución Normal está disponible para EXE Windows. Este archivo conserva su análisis estático.')
        return {'ready': False, 'reason': 'La ejecución aislada admite EXE Windows; APK/JAR requieren otro entorno.'}
    if not engines()['sandbox']:
        log(job, 'Windows Sandbox no está instalado. No se abrió la muestra.')
        return {'ready': False, 'reason': 'Instala Windows Sandbox para abrir esta app en un entorno aislado.'}
    stage = DATA / job['id'] / 'sandbox-input'
    stage.mkdir(exist_ok=True)
    shutil.copyfile(sample, stage / 'sample.exe')
    shutil.copyfile(ROOT / 'scripts/monitor.ps1', stage / 'monitor.ps1')
    config = f'''<Configuration>
<Networking>Disable</Networking><VGpu>Disable</VGpu>
<ClipboardRedirection>Disable</ClipboardRedirection>
<AudioInput>Disable</AudioInput><VideoInput>Disable</VideoInput>
<PrinterRedirection>Disable</PrinterRedirection><MemoryInMB>4096</MemoryInMB>
<MappedFolders><MappedFolder><HostFolder>{escape(str(stage))}</HostFolder>
<SandboxFolder>C:\\StrataInput</SandboxFolder><ReadOnly>true</ReadOnly></MappedFolder></MappedFolders>
<LogonCommand><Command>powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\\StrataInput\\monitor.ps1</Command></LogonCommand>
</Configuration>'''
    (DATA / job['id'] / 'analysis.wsb').write_text(config, encoding='utf-8')
    log(job, 'Sesión desechable preparada. La apertura requiere confirmación explícita en la interfaz.')
    return {'ready': True, 'launched': False, 'reason': 'Listo para abrir en Windows Sandbox.'}


def prepare_execution(job, sample):
    target = job.get('target', 'vm')
    if target == 'pc':
        fmt = job['metadata']['format']
        supported = (sample.suffix.lower() == '.exe' and fmt.startswith('Windows')) or (sample.suffix.lower() == '.jar' and fmt == 'Java JAR')
        return {'target': 'pc', 'ready': supported, 'launched': False,
                'reason': 'Abrir en este PC requiere confirmación. La aplicación tendrá los permisos de tu usuario.' if supported else 'Este PC puede abrir EXE Windows y JAR ejecutables. Este formato requiere otro sistema o emulador.'}
    if job.get('vm_kind') == 'external':
        supported = sample.suffix.lower() == '.exe' and job['metadata']['format'].startswith('Windows')
        return {'target': 'external', 'ready': supported, 'launched': False,
                'reason': 'Exporta el paquete y ejecútalo dentro de tu VM Windows con la red desactivada.' if supported else 'El paquete de ejecución para VM admite EXE Windows. APK, ELF y Mach-O necesitan su entorno correspondiente.'}
    result = prepare_sandbox(job, sample)
    result['target'] = 'vm'
    return result


def load_jobs():
    DATA.mkdir(exist_ok=True)
    for path in DATA.glob('*/job.json'):
        try:
            job = json.loads(path.read_text(encoding='utf-8'))
            if not re.fullmatch('[0-9a-f]{32}', job['id']):
                continue
            if job['status'] in ('queued', 'running'):
                job.update(status='failed', phase='El análisis se interrumpió al cerrar Strata')
            JOBS[job['id']] = job
        except (ValueError, KeyError, OSError):
            continue


def create_job(path, mode='safe', target='vm', vm_kind='sandbox', selected_engine='auto'):
    path = Path(path).resolve()
    if not path.is_file() or not 0 < path.stat().st_size <= MAX_UPLOAD:
        raise ValueError('Selecciona un archivo de 1 byte a 100 MB.')
    if mode not in ('safe', 'normal') or target not in ('pc', 'vm') or vm_kind not in ('sandbox', 'external'):
        raise ValueError('Modo o entorno inválido')
    if TASKS.full():
        raise ValueError('La cola está llena. Espera a que termine un análisis.')
    if selected_engine not in ('auto','combined'):
        default=classify(path.read_bytes())[1]
        if selected_engine not in engine_options(default):raise ValueError('El motor elegido no es compatible con este archivo.')
        if not engines().get(selected_engine):raise ValueError('El motor elegido no está configurado. Abre Motores y ayuda o elige Automático.')
    ident = uuid.uuid4().hex
    folder = DATA / ident / 'input'
    folder.mkdir(parents=True)
    name = re.sub(r'[^\w. -]', '_', path.stem)[:90] + path.suffix[:12]
    if name.split('.')[0].upper() in {'CON','PRN','AUX','NUL', *[f'COM{i}' for i in range(10)], *[f'LPT{i}' for i in range(10)]}:
        name = 'sample' + path.suffix
    shutil.copyfile(path, folder / name)
    job = {'id': ident, 'name': name, 'original': str(path), 'mode': mode, 'target': target,
           'vm_kind': vm_kind, 'status': 'queued', 'phase': 'En cola', 'created': time.time(), 'logs': [],'requested_engine':selected_engine}
    if selected_engine in ('dotpeek','binaryninja','combined'):
        job['external_tools']=external_tools.load(ROOT,DATA)
    with LOCK:
        JOBS[ident] = job
        save(job)
    return job


def export_results(job, destination):
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        for entry in result_files(job):
            archive.write(safe_result(job, entry['path']), entry['path'])


def export_vm(job, destination):
    if job['mode'] != 'normal' or (job.get('normal') or {}).get('target') != 'external' or not job['normal']['ready']:
        raise ValueError('No hay un paquete VM compatible preparado.')
    with zipfile.ZipFile(destination, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.write(DATA / job['id'] / 'input' / job['name'], 'sample.exe')
        archive.write(ROOT / 'scripts/monitor-external.ps1', 'Abrir-en-VM.ps1')
        archive.writestr('sha256.txt', job['metadata']['sha256'])
        archive.writestr('LEEME.txt', 'Transfiere este paquete a una VM Windows desechable. Desactiva red y las integraciones con el host. Ejecuta Abrir-en-VM.ps1 dentro de la VM; verifica el SHA-256 y confirma cuando el script lo solicite. El registro permanece dentro de la VM. No abras sample.exe en el host.')
    log(job, 'Paquete VM exportado; la muestra todavía no se ha ejecutado.')


def launch(job, confirmed=False):
    normal = job.get('normal') or {}
    if confirmed is not True or job['mode'] != 'normal' or not normal.get('ready'):
        raise ValueError('Confirma la apertura de un análisis Normal compatible.')
    if normal['target'] == 'external':
        raise ValueError('Exporta el paquete para abrirlo manualmente en tu VM.')
    if normal['target'] == 'vm':
        sandbox = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'System32/WindowsSandbox.exe'
        proc = subprocess.Popen([str(sandbox), str(DATA / job['id'] / 'analysis.wsb')])
        log(job, 'Windows Sandbox solicitado. La observación aparece dentro de la VM.')
    else:
        sample = Path(job['original'])
        with sample.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != job['metadata']['sha256']:
            raise ValueError('El archivo original cambió desde el análisis. Analízalo otra vez antes de abrirlo.')
        if sample.suffix.lower() == '.jar':
            with zipfile.ZipFile(sample) as archive:
                manifest = archive.read('META-INF/MANIFEST.MF').decode('utf-8', errors='replace')
            if not re.search(r'^Main-Class:', manifest, re.M | re.I):
                raise ValueError('Este JAR no declara Main-Class; no es una aplicación ejecutable.')
            args = [java_path(), '-jar', str(sample)]
        else:
            args = [str(sample)]
        proc = subprocess.Popen(args, cwd=sample.parent)
        log(job, f'Aplicación abierta en este PC. PID {proc.pid}.')
        threading.Thread(target=observe_pc, args=(job, proc), daemon=True).start()
    normal['launched'] = True
    save(job)
    return proc.pid


def observe_pc(job, proc):
    evidence = {'target': 'pc', 'sha256': job['metadata']['sha256'], 'pid': proc.pid, 'started': time.time(),
                'note': 'Observación del proceso inicial, sin interceptación de archivos, registro, red o procesos hijos.'}
    try:
        evidence['exit_code'] = proc.wait(timeout=60)
        evidence['status'] = 'finished'
    except subprocess.TimeoutExpired:
        evidence['status'] = 'still-running-after-60s'
    evidence['observation_end'] = time.time()
    (DATA / job['id'] / 'result/execution.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    log(job, f'Observación del proceso inicial: {evidence["status"]}.')


def stop_tools():
    STOP_REQUESTED.set()
    with LOCK:
        processes = list(TOOL_PROCESSES)
    for proc in processes:
        if proc.poll() is None:
            subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)


def worker():
    while True:
        job = TASKS.get()
        try:
            analyze(job)
        except Exception as exc:
            log(job, str(exc))
            update(job, status='failed', phase='Error de análisis', error=str(exc))
        finally:
            TASKS.task_done()


def result_files(job):
    base = DATA / job['id'] / 'result'
    if not base.exists():
        return []
    return sorted([{'path': p.relative_to(base).as_posix(), 'size': p.stat().st_size}
                   for p in base.rglob('*') if p.is_file() and not p.is_symlink()],
                  key=lambda item: item['path'])[:30000]


def safe_result(job, name):
    base = (DATA / job['id'] / 'result').resolve()
    path = (base / name).resolve()
    if not path.is_relative_to(base) or not path.is_file():
        raise ValueError('Archivo no encontrado')
    return path

