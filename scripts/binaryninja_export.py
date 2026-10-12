"""Strata's optional Binary Ninja headless adapter; requires the user's licensed API."""
import argparse
import json
import os
from pathlib import Path
import sys


def export(bn,sample,destination):
    destination=Path(destination)
    destination.mkdir(parents=True,exist_ok=True)
    recovered=[]; failures=[]
    with bn.load(str(sample)) as view:
        if view is None:raise ValueError('Binary Ninja no reconoce el archivo o no puede analizarlo.')
        with (destination/'decompiled.c').open('w',encoding='utf-8') as stream:
            stream.write('// Binary Ninja recovered HLIL pseudocode; not original or guaranteed compilable C.\n')
            for function in view.functions:
                try:
                    hlil=function.hlil
                    if hlil is None:
                        failures.append({'address':function.start,'reason':'HLIL unavailable'})
                        continue
                    lines=[str(line) for line in hlil.root.lines] if hlil.root is not None else []
                    if not lines:
                        failures.append({'address':function.start,'reason':'No HLIL lines'})
                        continue
                    # Serialize symbol names inside a comment to avoid introducing source text.
                    name=str(function.name).replace('*/','* /').replace('\n',' ')
                    stream.write(f'\n/* {name} @ 0x{function.start:x} */\n')
                    stream.write('\n'.join(lines)+'\n')
                    recovered.append({'name':str(function.name),'address':function.start})
                except Exception as exc:
                    failures.append({'address':function.start,'reason':str(exc)})
    (destination/'functions.json').write_text(json.dumps({'functions':recovered,'unrecovered':failures},ensure_ascii=False,indent=2),encoding='utf-8')
    if not recovered:
        (destination/'decompiled.c').unlink()
        raise ValueError('No se recuperó HLIL de ninguna función; consulta functions.json.')
    print(f'Binary Ninja: {len(recovered)} funciones recuperadas; {len(failures)} sin recuperar.')
    return len(recovered)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--api',required=True)
    parser.add_argument('--input',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    for key in ('BN_DISABLE_USER_SETTINGS','BN_DISABLE_USER_PLUGINS','BN_DISABLE_REPOSITORY_PLUGINS'):
        os.environ[key]='True'
    sys.path.insert(0,str(Path(args.api).resolve()))
    try:
        import binaryninja
        export(binaryninja,Path(args.input).resolve(),args.output)
    except Exception as exc:
        print(f'Binary Ninja: error de API, licencia o análisis: {exc}',file=sys.stderr)
        return 1
    return 0


if __name__=='__main__':
    raise SystemExit(main())
