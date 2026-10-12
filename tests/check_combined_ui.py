import json
from pathlib import Path
import tempfile
import tkinter as tk
from tkinter import ttk
from unittest.mock import patch
import engine
from desktop import Strata

def descendants(parent):
    for child in parent.winfo_children():
        yield child
        yield from descendants(child)

with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as scratch:
    engine.DATA=Path(scratch)/'data'
    app=Strata(); app.geometry('1120x760'); app.update()
    app.select_file(engine.ROOT/'samples/NativeHost.bin')
    assert app.engine_labels[app.engine_choice.get()]=='combined'
    job=engine.create_job(app.selected,selected_engine='combined')
    def fake(job,motor,folder,sample,out):
        code=out/'sources'; code.mkdir()
        (code/'decompiled.c').write_text('return 1;' if motor=='ghidra' else 'return 2;')
        return True,0
    with patch('external_tools.availability',return_value={'binaryninja':True,'dotpeek':False,'binaryninja_gui':False}),patch.object(engine,'decompile_motor',side_effect=fake):
        engine.analyze(job)
    app.activate_job(job); app.show('result'); app.update()
    assert app.current_path=='combined-summary.txt'
    assert app.tree.exists('file:motors/ghidra/sources/decompiled.c')
    assert app.tree.exists('file:motors/binaryninja/sources/decompiled.c')
    assert app.review_motors_button.winfo_rootx()+app.review_motors_button.winfo_width()<app.winfo_rootx()+app.winfo_width()
    assert app.code.winfo_height()>80
    app.review_motors_button.invoke(); app.update()
    assert app.current_page=='ai'
    dialog=next(w for w in app.winfo_children() if isinstance(w,tk.Toplevel))
    picker=next(w for w in descendants(dialog) if isinstance(w,ttk.Treeview))
    picker.selection_set(picker.get_children())
    next(w for w in descendants(dialog) if isinstance(w,ttk.Button) and w.cget('text')=='Añadir seleccionados').invoke()
    assert len(app.ai.files)==2 and {f['job'] for f in app.ai.files}=={job['id']}
    assert any('ghidra' in f['name'] for f in app.ai.files) and any('binaryninja' in f['name'] for f in app.ai.files)
    assert app.ai.session is None  # Selecting outputs never sends or starts an AI round.
    app.destroy()
(engine.ROOT/'VALIDACION-COMBINADO-UI.json').write_text(json.dumps({'success':True,'checks':['combined is default','shared summary opens before any source','both motor sources visible together','result controls fit minimum window','AI selection retains both motor provenances without sending']},indent=2))
print('Combined desktop UI passed')
