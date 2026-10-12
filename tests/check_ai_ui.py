import json
from pathlib import Path
import tempfile
import threading
import time
from unittest.mock import patch
import tkinter as tk
from tkinter import ttk
import engine
from desktop import Strata
from ai_selftest import Server

scratch=Path(__file__).resolve().parent/'ui-test-data'
scratch.mkdir(exist_ok=True)
engine.DATA=scratch
app=Strata()
app.update()
ai=app.ai
with Server() as server:
    conn=ai.settings.set_connection(server.connection,'fixture-key')
    analyst=ai.settings.set_agent({'name':'Analista','role':'analista','connection':conn['id'],'instructions':'Explica el código.'})
    reviewer=ai.settings.set_agent({'name':'Revisor','role':'revisor','connection':conn['id'],'instructions':'Revisa la propuesta.'})
    ai.refresh()
    fixture=scratch/'fixture.js'; fixture.write_text('const x = "a" + "b";',encoding='utf-8')
    ai.add_file(fixture)
    ai.agent_tree.selection_set(analyst['id'],reviewer['id'])
    assert 'code' not in app.pages
    assert all(key in app.pages for key in ('ai','local','review'))
    app.show('ai')
    ai.start_round()

    def buttons(widget):
        for child in widget.winfo_children():
            if isinstance(child,ttk.Button):yield child
            yield from buttons(child)
    def send_preview():
        dialog=next(w for w in app.winfo_children() if isinstance(w,tk.Toplevel))
        button=next(b for b in buttons(dialog) if b.cget('text')=='Enviar este mensaje')
        button.invoke()
        deadline=time.monotonic()+10
        while ai.busy and time.monotonic()<deadline:
            app.update(); time.sleep(.02)
        assert not ai.busy
    first_dialog=next(w for w in app.winfo_children() if isinstance(w,tk.Toplevel))
    next(b for b in buttons(first_dialog) if b.cget('text')=='Volver sin enviar').invoke()
    assert ai.next_button.cget('state')!='disabled'
    ai.next_button.invoke()
    send_preview()
    assert len(ai.session.value['results'])==1, ai.state.get()
    assert len(server.received)==1
    assert ai.next_button.cget('state')!='disabled'
    ai.next_button.invoke(); send_preview()
    assert len(ai.session.value['results'])==2, ai.state.get()
    assert not ai.details_open
    assert 'prompt_tokens' not in ai.result_text.get('1.0','end')
    ai.toggle_details(); app.update()
    assert ai.details_open and ai.details_frame.winfo_ismapped()
    ai.toggle_details(); app.update()
    assert not ai.details_frame.winfo_ismapped()
    assert ai.original_code.get('1.0','end-1c')=='const x = "a" + "b";'
    assert ai.proposed_code.get('1.0','end-1c')=='const x = "ab";'
    assert ai.original_code.tag_ranges('changed') and ai.proposed_code.tag_ranges('changed')
    assert len(server.received)==2
    assert len(server.received[1][1]['messages'])==2
    assert 'previous_results' in server.received[1][1]['messages'][1]['content']
    with patch('ai_ui.messagebox.askyesno',return_value=True):ai.accept()
    assert len(ai.session.value['accepted'])==1
    ai.cancel_round()
    assert ai.session.value['status']=='completado'  # Completed history cannot be cancelled retrospectively.
    assert fixture.read_text()=='const x = "a" + "b";'
    ai.add_file(fixture,workspace='local')
    ai.file_tree.selection_set('0'); ai.remove_files('ai')
    assert not ai.files and len(ai.local_files)==1
    app.show('local'); ai.local()
    deadline=time.monotonic()+10
    while ai.busy and time.monotonic()<deadline:
        app.update(); time.sleep(.02)
    assert ai.session.value['kind']=='local'
    app.update()
    assert not ai.next_button.winfo_ismapped()
    assert ai.session.value['results'][0]['proposals'][0]['code']=='const x = "ab";'
    with patch('ai_ui.messagebox.askyesno',return_value=True):ai.accept()
    assert len(ai.session.value['accepted'])==1
    ai.session.export(scratch/'ui-session.zip')
    ai.refresh_history()
    ai.history.selection_set(ai.session.ident); ai.open_history()
    assert ai.session.value['accepted']
    app.geometry('1120x760'); app.update()
    assert ai.original_code.winfo_width()>200 and ai.proposed_code.winfo_width()>200
    ai.toggle_details(); app.update()
    assert ai.details_frame.winfo_ismapped()
    assert ai.original_code.winfo_height()>80 and ai.proposed_code.winfo_height()>80
    ai.toggle_details(); app.update()
    report={'success':True,'checks':['separate sidebar sections','independent AI and local file selections','two agent previews','resume after dismissing preview','two actual local HTTP requests','previous result preview','side by side code and highlights','legible summary without usage JSON','collapsible technical details','local review hides agent controls','accepted copy preserves original','local dispatcher','completed history preserved','history reload','ZIP export','minimum window size keeps comparison visible']}
    (Path(__file__).resolve().parent/'ai-ui-validation.json').write_text(json.dumps(report,indent=2))
app.destroy()
print('Native UI flow passed')
