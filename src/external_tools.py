"""Optional, user-installed decompilers. No downloads or license files are copied."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

DEFAULTS={'dotpeek':'','binaryninja_gui':'','binaryninja_python':'','binaryninja_api':'','binaryninja_headless':False}


def load(root,data):
    path=Path(data)/'external-tools.json'
    try:
        value=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        if not isinstance(value,dict):raise ValueError('Configuración de motores externos inválida.')
        if any(key in value and not isinstance(value[key],type(default)) for key,default in DEFAULTS.items()):
            raise ValueError('Tipos inválidos en external-tools.json; las rutas deben ser texto y headless un booleano.')
        return {key:value.get(key,default) for key,default in DEFAULTS.items()}
    except (OSError,json.JSONDecodeError) as exc:
        raise ValueError('No se pudo leer external-tools.json; revisa su contenido.') from exc


def resolve(root,value):
    path=Path(value)
    return (path if path.is_absolute() else Path(root)/path).resolve()


def save(root,data,values):
    result={key:values.get(key,default) for key,default in DEFAULTS.items()}
    for key in ('dotpeek','binaryninja_gui','binaryninja_python'):
        value=result[key].strip()
        if value and (not resolve(root,value).is_file() or resolve(root,value).suffix.lower()!='.exe'):
            raise ValueError(f'{key}: selecciona un ejecutable .exe existente.')
        result[key]=value
    api=result['binaryninja_api'].strip()
    if api and not (resolve(root,api)/'binaryninja/__init__.py').is_file():
        raise ValueError('La carpeta API debe contener binaryninja/__init__.py (normalmente Binary Ninja/python).')
    result['binaryninja_api']=api
    result['binaryninja_headless']=bool(result['binaryninja_headless'])
    if result['binaryninja_headless'] and not (result['binaryninja_python'] and api):
        raise ValueError('Para automatización elige un Python dedicado y la carpeta API de Binary Ninja.')
    destination=Path(data)/'external-tools.json'
    destination.parent.mkdir(parents=True,exist_ok=True)
    temporary=destination.with_suffix('.tmp')
    temporary.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(destination)
    return result


def availability(root,values):
    def executable(key):
        return bool(values.get(key) and resolve(root,values[key]).is_file())
    return {'dotpeek':executable('dotpeek'),'binaryninja_gui':executable('binaryninja_gui'),
            'binaryninja':bool(values.get('binaryninja_headless') and executable('binaryninja_python') and values.get('binaryninja_api')
                              and (resolve(root,values['binaryninja_api'])/'binaryninja/__init__.py').is_file())}


def discover(root):
    values=dict(DEFAULTS)
    local=Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))
    program=Path(os.environ.get('ProgramFiles','C:/Program Files'))
    dotpeek=list((Path(root)/'tools/dotpeek').glob('dotPeek*.exe'))
    for base in (program/'JetBrains',local/'JetBrains'):
        dotpeek.extend(base.glob('dotPeek*/dotPeek*.exe'))
    ninja=[Path(root)/'tools/binaryninja/binaryninja.exe',program/'Vector35/BinaryNinja/binaryninja.exe',
           program/'Binary Ninja/binaryninja.exe',local/'Programs/Binary Ninja/binaryninja.exe',local/'Vector35/BinaryNinja/binaryninja.exe']
    values['dotpeek']=next((str(p.resolve()) for p in dotpeek if p.is_file()),'')
    values['binaryninja_gui']=next((str(p.resolve()) for p in ninja if p.is_file()),'')
    if values['binaryninja_gui']:
        api=Path(values['binaryninja_gui']).parent/'python'
        if (api/'binaryninja/__init__.py').is_file():values['binaryninja_api']=str(api)
    # Never opt users into headless licensing or select an arbitrary Python automatically.
    return values


def binaryninja_command(root,values,sample,output):
    if not availability(root,values)['binaryninja']:
        raise ValueError('Configura la API de Binary Ninja en Motores y ayuda → Herramientas externas.')
    return [str(resolve(root,values['binaryninja_python'])), '-I', str(Path(root)/'scripts/binaryninja_export.py'),
            '--api',str(resolve(root,values['binaryninja_api'])),'--input',str(sample),'--output',str(output)]


def launch(root,values,tool,sample,fmt):
    key='dotpeek' if tool=='dotpeek' else 'binaryninja_gui' if tool=='binaryninja' else None
    if key is None:raise ValueError('Herramienta externa inválida.')
    if tool=='dotpeek' and fmt!='Windows .NET':raise ValueError('dotPeek se usa con ensamblados .NET.')
    if not availability(root,values)[key]:raise ValueError('Herramienta no instalada/configurada. Abre Motores y ayuda → Herramientas externas.')
    # Only launch the decompiler. The sample is a data argument, never a command.
    return subprocess.Popen([str(resolve(root,values[key])),str(Path(sample).resolve())],cwd=resolve(root,values[key]).parent).pid


def import_sources(folder,result,tool):
    if tool not in ('dotpeek','binaryninja'):raise ValueError('Origen de importación inválido.')
    source=Path(folder).resolve()
    base=Path(result).resolve()
    if not source.is_dir():raise ValueError('La carpeta exportada no existe.')
    if source==base or source.is_relative_to(base) or base.is_relative_to(source):
        raise ValueError('Selecciona una carpeta exportada fuera del directorio de resultados.')
    allowed={'.cs','.csproj','.sln'} if tool=='dotpeek' else {'.c','.h','.cpp','.txt'}
    files=[]; total=0
    # Do not follow symlinks or Windows junctions, or import executables/resources.
    for directory,dirs,names in os.walk(source,followlinks=False):
        dirs[:]=[name for name in dirs if not (Path(directory)/name).is_symlink() and not (Path(directory)/name).is_junction()]
        for name in names:
            path=Path(directory)/name
            if path.suffix.lower() not in allowed or path.is_symlink() or not path.resolve().is_relative_to(source):continue
            total+=path.stat().st_size
            files.append(path)
            if len(files)>20000 or total>100*1024*1024:raise ValueError('La exportación supera 20.000 archivos o 100 MB; reduce la carpeta.')
    code_ext={'.cs'} if tool=='dotpeek' else {'.c','.h','.cpp','.txt'}
    if not any(path.suffix.lower() in code_ext and path.stat().st_size for path in files):
        raise ValueError('No se encontró código exportado compatible.')
    target=base/'sources'/f'{tool}-import-{uuid.uuid4().hex[:12]}'
    target.mkdir(parents=True)
    try:
        for path in files:
            dest=target/path.relative_to(source)
            dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(path,dest)
        (target/'strata-import.json').write_text(json.dumps({'tool':tool,'files':len(files),'bytes':total,'provenance':'user-selected external export; correspondence with sample not verified'},indent=2),encoding='utf-8')
    except Exception:
        shutil.rmtree(target)
        raise
    return target,len(files)
