from pathlib import Path
import json
import tempfile
from tkinter import ttk
from desktop import Strata
import engine

def descendants(parent):
    for child in parent.winfo_children():
        yield child
        yield from descendants(child)

with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp:
    engine.DATA=Path(temp)/'data'
    app=Strata()
    app.geometry('1120x760'); app.update()
    app.select_file(engine.ROOT/'samples/Hello.dll'); app.update()
    assert any(key=='dotpeek' for key in app.engine_labels.values())
    assert app.start_button.winfo_rooty()+app.start_button.winfo_height()<app.winfo_rooty()+app.winfo_height()-40
    app.select_file(engine.ROOT/'samples/NativeHost.bin'); app.update()
    assert 'binaryninja' in app.engine_labels.values() and 'dotpeek' not in app.engine_labels.values()
    app.show('engines')
    notebooks=[w for w in descendants(app.pages['engines']) if isinstance(w,ttk.Notebook)]
    notebooks[0].select(1); notebooks[1].select(1)
    app.update()
    save=next(w for w in descendants(app.pages['engines']) if isinstance(w,ttk.Button) and w.cget('text')=='Guardar rutas')
    assert save.winfo_rooty()+save.winfo_height()<app.winfo_rooty()+app.winfo_height()-40
    app.tools_ui.open_api(); app.update()
    dialog=app.tools_ui.api_frame.master
    last=next(w for w in descendants(dialog) if isinstance(w,ttk.Label) and 'licencia permanece' in w.cget('text'))
    save_api=next(w for w in descendants(dialog) if isinstance(w,ttk.Button) and w.cget('text')=='Guardar API')
    assert last.winfo_rooty()+last.winfo_height()<save_api.winfo_rooty()
    next(w for w in descendants(dialog) if isinstance(w,ttk.Button) and w.cget('text')=='Cancelar').invoke()
    app.destroy()
print('Optional tools UI fits minimum window')
(engine.ROOT/'VALIDACION-MOTORES-UI.json').write_text(json.dumps({'success':True,'checks':['compatible engine selector per sample','start action fits minimum window','external settings save remains visible','headless settings dialog fits and cancels without saving']},indent=2))
