import json
from pathlib import Path
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk
import engine
from desktop import Strata

engine.DATA=Path(__file__).parent/'setup-test-data'
engine.DATA.mkdir(exist_ok=True)
app=Strata()
ai=app.ai
def descendants(parent):
    for child in parent.winfo_children():
        yield child
        yield from descendants(child)
before=len(ai.settings.values['agents'])
ai.editor('connections',new=True)
app.update()
dialog=next(w for w in app.winfo_children() if isinstance(w,tk.Toplevel))
entries=[w for w in descendants(dialog) if isinstance(w,ttk.Entry) and not isinstance(w,ttk.Combobox)]
entries[0].insert(0,'Modelo de prueba')
entries[2].insert(0,'fixture-model')
next(w for w in descendants(dialog) if isinstance(w,ttk.Button) and w.cget('text')=='Guardar').invoke()
app.update()
assert len(ai.settings.values['agents'])==before+1
agent=ai.settings.values['agents'][-1]
assert agent['role']=='analista' and agent['instructions']
for key in app.nav:
    app.show(key); app.update()
    assert app.current_page==key
    assert sum(button.cget('style')=='Selected.Nav.TButton' for button in app.nav.values())==1
    assert app.nav[key].cget('style')=='Selected.Nav.TButton'
style=ttk.Style(app)
assert style.lookup('Selected.Nav.TButton','background',('active',))=='#ededed'
assert style.lookup('Selected.Nav.TButton','foreground',('active',))=='#090909'
app.show('ai'); app.update()
for number in range(3):
    ai.settings.set_agent({'name':f'Fixture {number}','connection':agent['connection'],'role':'analista','instructions':'Explica el código de prueba.'})
ai.refresh(); app.update()
ai.agent_tree.selection_set(())
for ident in ai.agent_tree.get_children()[:4]:
    ai.agent_tree.see(ident); app.update()
    x,y,w,h=ai.agent_tree.bbox(ident)
    ai.toggle_agent(SimpleNamespace(y=y+h//2))
assert len(ai.agent_tree.selection())==min(3,len(ai.agent_tree.get_children()))
ident=ai.agent_tree.selection()[0]
ai.agent_tree.see(ident); app.update()
x,y,w,h=ai.agent_tree.bbox(ident)
ai.toggle_agent(SimpleNamespace(y=y+h//2))
assert ident not in ai.agent_tree.selection()
app.geometry('1120x760'); app.update()
assert app.nav['engines'].winfo_rooty()+app.nav['engines'].winfo_height()<app.winfo_rooty()+app.winfo_height()
report={'success':True,'checks':['model creates ready analyst','single active sidebar entry on every page','active navigation retains contrast on hover','single-click agent toggle','maximum three selected agents','navigation fits minimum window']}
(Path(__file__).parent/'agent-setup-validation.json').write_text(json.dumps(report,indent=2))
app.destroy()
print('Agent setup and navigation passed')
