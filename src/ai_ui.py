"""Native model configuration, explicit request previews and reviewed copies."""
import difflib
import hashlib
import json
from pathlib import Path
import queue
import shutil
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import ai_core as core
import deobfuscator
import engine

BG, PANEL, FG, MUTED = '#090909', '#131313', '#ededed', '#a3a3a3'
FONT, MONO = 'Segoe UI Variable', 'Cascadia Code'
EXTENSIONS = ('.js','.mjs','.cjs','.java','.cs','.c','.h','.cpp')


def text_widget(parent, height=12):
    holder = ttk.Frame(parent)
    holder.pack(fill='both', expand=True)
    widget = tk.Text(holder, height=height, bg=PANEL, fg=FG, insertbackground=FG, selectbackground='#424242',
                     font=(MONO,10), relief='flat', wrap='word', padx=12, pady=12)
    widget.pack(side='left', fill='both', expand=True)
    bar = ttk.Scrollbar(holder, command=widget.yview)
    bar.pack(side='right', fill='y')
    widget.configure(yscrollcommand=bar.set)
    return widget


def set_text(widget, content):
    widget.configure(state='normal')
    widget.delete('1.0', 'end')
    widget.insert('1.0', content)
    widget.configure(state='disabled')


class AgentsUI:
    def __init__(self, app, settings_page, analysis_page, local_page, review_page):
        self.app = app
        self.settings = core.Settings(engine.DATA)
        self.files = []
        self.local_files = []
        self.file_lists = {}
        self.counts = {}
        self.session = None
        self.index = 0
        self.pending_agents = []
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.busy = False
        self.state = tk.StringVar(value='Elige archivos para comenzar. Los originales se conservan.')
        self.build_settings(settings_page)
        self.build_analysis(analysis_page,local_page,review_page)
        self.refresh()
        self.app.after(100, self.poll)

    def title(self, parent, title, subtitle):
        ttk.Label(parent, text=title, style='Title.TLabel').pack(anchor='w')
        ttk.Label(parent, text=subtitle, style='Muted.TLabel', wraplength=780).pack(anchor='w', pady=(9,20))

    def build_settings(self, parent):
        self.title(parent, 'Agentes y modelos', 'Añade un modelo para empezar. Un agente usa ese modelo con instrucciones para una tarea concreta.')
        self.setup_hint=tk.StringVar()
        ttk.Label(parent,textvariable=self.setup_hint,style='Muted.TLabel',wraplength=780).pack(anchor='w',pady=(0,12))
        notebook = ttk.Notebook(parent)
        notebook.pack(fill='both', expand=True)
        self.lists = {}
        for kind, caption, columns in [('connections','Modelos y claves API',('name','provider','model','url')),('agents','Agentes personalizados',('name','role','connection'))]:
            page = ttk.Frame(notebook, padding=16)
            notebook.add(page, text=caption)
            explanation='Elige dónde se ejecuta la IA y qué modelo utiliza. Al añadirlo puedes crear un analista automáticamente.' if kind=='connections' else 'Analista explica el código; desofuscador propone cambios; revisor comprueba las propuestas. Puedes usar un solo agente.'
            ttk.Label(page,text=explanation,style='Muted.TLabel',wraplength=740).pack(anchor='w',pady=(0,14))
            tree = ttk.Treeview(page, columns=columns, show='headings', selectmode='browse')
            for col in columns:
                tree.heading(col, text={'name':'Nombre','provider':'Proveedor','model':'Modelo','url':'Dirección del servicio','role':'Tarea','connection':'Modelo configurado'}[col])
                tree.column(col, width=160, minwidth=80)
            tree.pack(fill='both', expand=True)
            tree.bind('<Double-1>', lambda _e, k=kind:self.editor(k))
            self.lists[kind] = tree
            row = ttk.Frame(page)
            row.pack(fill='x', pady=(14,0))
            for label, action in [('Añadir modelo' if kind=='connections' else 'Crear agente', lambda k=kind:self.editor(k,new=True)),('Editar',lambda k=kind:self.editor(k)),('Duplicar',lambda k=kind:self.editor(k,duplicate=True)),('Eliminar',lambda k=kind:self.remove(k))]:
                ttk.Button(row, text=label, command=action,style='Primary.TButton' if label.startswith(('Añadir','Crear')) else 'TButton').pack(side='left', padx=(0,8))
        ttk.Label(parent, text='Al mover la carpeta a otro PC o usuario, introduce las claves de nuevo. Ollama necesita estar instalado y tener el modelo disponible.',
                  style='Muted.TLabel', wraplength=800).pack(anchor='w', pady=(16,0))

    def refresh(self):
        previous=set(self.agent_tree.selection())
        self.setup_hint.set('Empieza en Modelos y claves API → Añadir modelo.' if not self.settings.values['connections'] else 'Modelo configurado. Ve a Análisis con IA para elegir archivos y marcar los agentes que usarás.')
        for kind, tree in self.lists.items():
            tree.delete(*tree.get_children())
            for item in self.settings.values[kind]:
                if kind == 'connections':
                    values = (item['name'], 'Ollama' if item['provider']=='ollama' else 'API compatible', item['model'], item['url'])
                else:
                    conn = self.settings.connection(item['connection'])
                    values = (item['name'], item['role'].capitalize(), conn['name']+' · '+conn['model'])
                tree.insert('', 'end', iid=item['id'], values=values)
        self.agent_tree.delete(*self.agent_tree.get_children())
        for agent in sorted(self.settings.values['agents'], key=lambda a:core.ROLES.index(a['role'])):
            conn = self.settings.connection(agent['connection'])
            self.agent_tree.insert('', 'end', iid=agent['id'], values=('Sin marcar',agent['name'],agent['role'].capitalize(),conn['model']))
        available=self.agent_tree.get_children()
        selected=[ident for ident in available if ident in previous]
        if not selected and available:
            selected=[available[0]]
        self.agent_tree.selection_set(selected)
        self.update_agent_selection()
        self.refresh_history()

    def update_agent_selection(self, _event=None):
        selected=set(self.agent_tree.selection())
        for ident in self.agent_tree.get_children():
            self.agent_tree.set(ident,'selected','Sí' if ident in selected else 'Sin marcar')
        self.agent_hint.set(f'{len(selected)} de 3 agentes seleccionados. Haz clic en una fila para marcarla o desmarcarla.' if self.settings.values['agents'] else 'Añade un modelo en Agentes y modelos. Puedes crear allí tu primer analista automáticamente.')

    def toggle_agent(self,event):
        ident=self.agent_tree.identify_row(event.y)
        if not ident:return
        if ident in self.agent_tree.selection():
            self.agent_tree.selection_remove(ident)
        elif len(self.agent_tree.selection())<3:
            self.agent_tree.selection_add(ident)
        else:
            self.agent_hint.set('Ya hay 3 agentes seleccionados. Desmarca uno antes de añadir otro.')
            return 'break'
        self.agent_tree.focus(ident)
        self.update_agent_selection()
        return 'break'

    def remove(self, kind):
        selection = self.lists[kind].selection()
        if not selection:
            return
        if not messagebox.askyesno('Eliminar', '¿Eliminar esta configuración? Las sesiones guardadas se conservarán.', parent=self.app):
            return
        try:
            self.settings.remove(kind, selection[0])
            self.refresh()
        except ValueError as exc:
            messagebox.showerror('No se pudo eliminar', str(exc), parent=self.app)

    def editor(self, kind, new=False, duplicate=False):
        selection = self.lists[kind].selection()
        if not new and not selection:
            return
        item = {} if new else dict(next(v for v in self.settings.values[kind] if v['id']==selection[0]))
        if duplicate:
            item.pop('id', None)
            item.pop('secret', None)
            item['name'] += ' (copia)'
        if kind=='agents' and not self.settings.values['connections']:
            messagebox.showinfo('Añade una conexión', 'Crea primero una conexión y escribe su modelo.', parent=self.app)
            return
        dialog = tk.Toplevel(self.app)
        dialog.title('Configurar modelo' if kind=='connections' else 'Configurar agente')
        dialog.configure(bg=BG)
        dialog.geometry('690x640')
        dialog.minsize(610,570)
        dialog.transient(self.app)
        dialog.grab_set()
        frame = ttk.Frame(dialog, padding=24)
        frame.pack(fill='both', expand=True)
        variables = {}

        def field(name, label, default='', values=None):
            ttk.Label(frame, text=label, style='Muted.TLabel').pack(anchor='w', pady=(9,4))
            var = tk.StringVar(value=item.get(name, default))
            variables[name] = var
            control = ttk.Combobox(frame, textvariable=var, values=values, state='readonly') if values else ttk.Entry(frame, textvariable=var)
            control.pack(fill='x')
            return control

        field('name','Nombre')
        if kind == 'connections':
            providers={'Ollama (en este PC)':'ollama','API compatible con OpenAI':'compatible'}
            item['provider_label']=next(label for label,value in providers.items() if value==item.get('provider','ollama'))
            provider_control=field('provider_label','Dónde está el modelo',values=tuple(providers))
            field('url','URL base (compatible: incluye /v1 cuando corresponda)', 'http://localhost:11434')
            def provider_changed(_event=None):
                if variables['url'].get() in ('http://localhost:11434','https://api.openai.com/v1'):
                    variables['url'].set('http://localhost:11434' if providers[variables['provider_label'].get()]=='ollama' else 'https://api.openai.com/v1')
            provider_control.bind('<<ComboboxSelected>>',provider_changed)
            field('model','Nombre exacto del modelo')
            ttk.Label(frame, text='Clave API nueva (vacío conserva la existente; las copias no incluyen claves)', style='Muted.TLabel').pack(anchor='w',pady=(12,5))
            key_var = tk.StringVar()
            ttk.Entry(frame, textvariable=key_var, show='•').pack(fill='x')
            remove_key = tk.BooleanVar()
            ttk.Checkbutton(frame, text='Eliminar la clave guardada', variable=remove_key).pack(anchor='w',pady=12)
            create_analyst=tk.BooleanVar(value=new or duplicate)
            if new or duplicate:
                ttk.Checkbutton(frame,text='Crear también un analista listo para usar',variable=create_analyst).pack(anchor='w')
            ttk.Label(frame, text='HTTP solo para localhost / bucle local. Los demás endpoints requieren HTTPS.\nLa URL, modelo y clave se configuran por separado.', style='Muted.TLabel',wraplength=630).pack(anchor='w',pady=12)
        else:
            connections = self.settings.values['connections']
            labels = {f"{c['name']} · {c['model']} ({i+1})":c['id'] for i,c in enumerate(connections)}
            initial = next((label for label, ident in labels.items() if ident==item.get('connection')), next(iter(labels)))
            item['connection_label'] = initial
            field('connection_label','Modelo que usará el agente', initial, tuple(labels))
            role_control = field('role','Rol / plantilla','analista',core.ROLES)
            ttk.Label(frame, text='Instrucciones del agente', style='Muted.TLabel').pack(anchor='w',pady=(12,4))
            instructions = text_widget(frame, height=8)
            instructions.insert('1.0',item.get('instructions', core.TEMPLATES[variables['role'].get()]))
            def template(_event=None):
                instructions.delete('1.0','end')
                instructions.insert('1.0',core.TEMPLATES[variables['role'].get()])
            ttk.Button(frame,text='Usar plantilla del rol',command=template).pack(anchor='w',pady=8)
        footer = ttk.Frame(frame)
        footer.pack(fill='x', pady=(15,0))
        ttk.Button(footer,text='Cancelar',command=dialog.destroy).pack(side='right')

        def save():
            try:
                data = {key:var.get().strip() for key,var in variables.items()}
                if item.get('id'):
                    data['id'] = item['id']
                if kind == 'connections':
                    data['provider']=providers[data.pop('provider_label')]
                    secret = '' if remove_key.get() else key_var.get() or None
                    connection=self.settings.set_connection(data, secret)
                    if (new or duplicate) and create_analyst.get():
                        self.settings.set_agent({'name':'Analista · '+connection['name'],'connection':connection['id'],'role':'analista','instructions':core.TEMPLATES['analista']})
                else:
                    data['connection'] = labels[data.pop('connection_label')]
                    data['instructions'] = instructions.get('1.0','end-1c').strip()
                    self.settings.set_agent(data)
                dialog.destroy()
                self.refresh()
            except Exception as exc:
                messagebox.showerror('Configuración inválida', str(exc), parent=dialog)
        ttk.Button(footer,text='Guardar',style='Primary.TButton',command=save).pack(side='right',padx=8)

    def build_analysis(self, analysis, local, review):
        self.title(analysis,'Análisis con IA','Elige el código y los agentes. Revisa el mensaje completo antes de enviarlo.')
        self.source_panel(analysis,'ai')
        heading=ttk.Frame(analysis)
        heading.pack(fill='x',pady=(22,8))
        ttk.Label(heading,text='Agentes para esta ronda',style='Section.TLabel').pack(side='left')
        ttk.Button(heading,text='Configurar agentes',command=lambda:self.app.show('agents')).pack(side='right')
        self.agent_hint=tk.StringVar()
        ttk.Label(analysis,textvariable=self.agent_hint,style='Muted.TLabel',wraplength=850).pack(anchor='w',pady=(0,10))
        self.agent_tree=ttk.Treeview(analysis,columns=('selected','name','role','model'),show='headings',selectmode='extended',height=4)
        for col,caption in [('selected','Usar en esta ronda'),('name','Agente'),('role','Tarea'),('model','Modelo')]:
            self.agent_tree.heading(col,text=caption); self.agent_tree.column(col,width=200)
        self.agent_tree.column('selected',width=130,minwidth=110,stretch=False)
        self.agent_tree.bind('<Button-1>',self.toggle_agent)
        self.agent_tree.bind('<<TreeviewSelect>>',self.update_agent_selection)
        self.agent_tree.pack(fill='both',expand=True)
        row=ttk.Frame(analysis); row.pack(fill='x',pady=(18,0))
        ttk.Label(row,text='Una llamada por agente. Máximo 3 agentes.',style='Muted.TLabel').pack(side='left')
        self.prepare_button=ttk.Button(row,text='Revisar mensaje y analizar',style='Primary.TButton',command=self.start_round)
        self.prepare_button.pack(side='right')
        self.feedback(analysis)

        self.title(local,'Desofuscador local','Simplifica JavaScript sin ejecutarlo ni enviarlo a un proveedor.')
        self.source_panel(local,'local')
        rules=ttk.Frame(local,style='Panel.TFrame',padding=20)
        rules.pack(fill='x',pady=22)
        ttk.Label(rules,text='Qué puede simplificar',style='Panel.TLabel',font=(FONT,12,'bold')).pack(anchor='w')
        ttk.Label(rules,text='Cadenas literales y escapes\nSumas, restas y multiplicaciones de enteros seguros',style='Panel.TLabel',foreground=MUTED,justify='left').pack(anchor='w',pady=(10,0))
        ttk.Label(local,text='Las llamadas, variables, cifrado dinámico y sintaxis incompleta se conservan. Podrás comparar el resultado y guardar una copia.',style='Muted.TLabel',wraplength=850).pack(anchor='w')
        row=ttk.Frame(local); row.pack(fill='x',pady=(22,0))
        ttk.Button(row,text='Cargar ejemplo',command=self.local_example).pack(side='left')
        self.local_button=ttk.Button(row,text='Desofuscar archivos',style='Primary.TButton',command=self.local)
        self.local_button.pack(side='right')
        self.feedback(local)

        self.title(review,'Revisión de cambios','Lee el resumen. Compara el original y la propuesta antes de guardar una copia.')
        self.review_status=tk.StringVar(value='Aún no hay resultados. Inicia un análisis con IA o una desofuscación local.')
        ttk.Label(review,textvariable=self.review_status,style='Muted.TLabel',wraplength=880).pack(anchor='w',pady=(0,12))
        actions=ttk.Frame(review); actions.pack(fill='x',pady=(0,12))
        self.next_button=ttk.Button(actions,text='Revisar siguiente agente',command=self.preview_next,state='disabled')
        self.next_button.pack(side='left')
        self.cancel_button=ttk.Button(actions,text='Cancelar ronda',command=self.cancel_round,state='disabled')
        self.cancel_button.pack(side='left',padx=8)
        self.export_button=ttk.Button(actions,text='Exportar sesión',command=self.export,state='disabled')
        self.export_button.pack(side='right')
        self.next_button.pack_forget()
        self.cancel_button.pack_forget()
        # A vertical splitter preserves space for code when summaries or logs grow.
        stack=ttk.Panedwindow(review,orient='vertical')
        self.review_split=stack
        stack.pack(fill='both',expand=True)
        summary=ttk.Frame(stack)
        stack.add(summary,weight=1)
        ttk.Label(summary,text='Resumen',style='Section.TLabel').pack(anchor='w',pady=(0,8))
        self.result_text=text_widget(summary,height=5)
        self.details_button=ttk.Button(summary,text='Mostrar detalles técnicos',command=self.toggle_details)
        self.details_button.pack(anchor='w',pady=8)
        self.details_frame=ttk.Frame(summary)
        self.details=text_widget(self.details_frame,height=5)
        self.details_open=False
        comparison=ttk.Frame(stack)
        stack.add(comparison,weight=3)
        controls=ttk.Frame(comparison); controls.pack(fill='x',pady=(10,8))
        self.proposal_var=tk.StringVar()
        self.proposal_combo=ttk.Combobox(controls,textvariable=self.proposal_var,state='readonly')
        self.proposal_combo.pack(side='left',fill='x',expand=True)
        self.proposal_combo.bind('<<ComboboxSelected>>',lambda _:self.show_diff())
        self.accept_button=ttk.Button(controls,text='Guardar copia revisada',style='Primary.TButton',command=self.accept,state='disabled')
        self.accept_button.pack(side='right',padx=(12,0))
        self.change_reason=tk.StringVar(value='Elige una propuesta para compararla.')
        ttk.Label(comparison,textvariable=self.change_reason,style='Muted.TLabel',wraplength=850).pack(anchor='w',pady=(0,8))
        split=ttk.Panedwindow(comparison,orient='horizontal')
        split.pack(fill='both',expand=True)
        panels=[]
        for label in ('Original','Propuesta'):
            pane=ttk.Frame(split,style='Panel.TFrame',padding=(8,8))
            split.add(pane,weight=1)
            ttk.Label(pane,text=label,style='Panel.TLabel',font=(FONT,11,'bold')).pack(anchor='w',pady=(0,6))
            code=text_widget(pane,height=12); code.configure(wrap='none')
            horizontal=ttk.Scrollbar(pane,orient='horizontal',command=code.xview)
            horizontal.pack(fill='x'); code.configure(xscrollcommand=horizontal.set)
            code.tag_configure('changed',background='#352828' if label=='Original' else '#243329')
            panels.append(code)
        self.original_code,self.proposed_code=panels
        set_text(self.original_code,'Aquí aparecerá el código original.')
        set_text(self.proposed_code,'Aquí aparecerá la propuesta seleccionada.')
        self.feedback(review)

        history=ttk.Frame(self.app.history_notebook,padding=14)
        self.app.history_notebook.add(history,text='Análisis de código')
        self.history_page=history
        self.history=ttk.Treeview(history,columns=('date','kind','state','files'),show='headings',selectmode='browse')
        for col,caption,width in [('date','Fecha',160),('kind','Tipo',100),('state','Estado',140),('files','Archivos',330)]:
            self.history.heading(col,text=caption); self.history.column(col,width=width)
        self.history.pack(fill='both',expand=True)
        self.history.bind('<Double-1>',lambda _:self.open_history())
        ttk.Button(history,text='Abrir en revisión',command=self.open_history).pack(anchor='e',pady=(12,0))

    def feedback(self,parent):
        ttk.Label(parent,textvariable=self.state,style='Muted.TLabel',wraplength=850).pack(anchor='w',pady=(16,0))

    def source_panel(self,parent,workspace):
        title=ttk.Frame(parent); title.pack(fill='x',pady=(0,10))
        ttk.Label(title,text='Archivos de código',style='Section.TLabel').pack(side='left')
        ttk.Button(title,text='Importar archivos',command=lambda:self.import_files(workspace)).pack(side='right')
        tree=ttk.Treeview(parent,columns=('name','chars'),show='headings',selectmode='extended',height=5)
        tree.heading('name',text='Archivo'); tree.heading('chars',text='Caracteres')
        tree.column('name',width=550); tree.column('chars',width=120,stretch=False)
        tree.pack(fill='x')
        self.file_lists[workspace]=tree
        if workspace=='ai':self.file_tree=tree
        else:self.local_tree=tree
        count=tk.StringVar(value='Sin archivos. Importa código o añádelo desde una decompilación.')
        self.counts[workspace]=count
        row=ttk.Frame(parent); row.pack(fill='x',pady=(10,0))
        ttk.Label(row,textvariable=count,style='Muted.TLabel',wraplength=440).pack(side='left')
        ttk.Button(row,text='Quitar',command=lambda:self.remove_files(workspace)).pack(side='right')
        ttk.Button(row,text='Añadir del análisis',command=lambda:self.pick_results(workspace)).pack(side='right',padx=8)

    def toggle_details(self):
        self.details_open=not self.details_open
        if self.details_open:self.details_frame.pack(fill='both',expand=True)
        else:self.details_frame.pack_forget()
        self.details_button.configure(text='Ocultar detalles técnicos' if self.details_open else 'Mostrar detalles técnicos')
        def resize():
            height=self.review_split.winfo_height()
            if height>100:self.review_split.sashpos(0,int(height*(.55 if self.details_open else .30)))
        self.app.after_idle(resize)

    def local_example(self):
        try:
            self.ensure_idle()
            self.add_file(engine.ROOT/'samples/Obfuscated.js',workspace='local')
        except Exception as exc:messagebox.showerror('Ejemplo',str(exc),parent=self.app)

    def ensure_idle(self):
        if self.busy:
            raise ValueError('Espera o cancela la solicitud en curso.')

    def add_file(self, path, name=None, job=None, workspace='ai'):
        path=Path(path)
        files=self.local_files if workspace=='local' else self.files
        extensions=('.js','.mjs','.cjs') if workspace=='local' else EXTENSIONS
        if path.suffix.lower() not in extensions:
            if workspace=='local':raise ValueError('El desofuscador local admite archivos .js, .mjs o .cjs. Para otros lenguajes usa Análisis con IA.')
            raise ValueError('Selecciona JavaScript, Java, C#, C o C++.')
        if path.stat().st_size>4*core.MAX_CODE:
            raise ValueError('Archivo demasiado grande. El límite total es 48.000 caracteres.')
        code=path.read_text(encoding='utf-8-sig',errors='strict')
        display=name or path.name
        if any(f['name']==display for f in files):
            raise ValueError('Ya hay un archivo con ese nombre. Quita el anterior o renombra el archivo importado.')
        if not code.strip() or sum(len(f['code']) for f in files)+len(code)>core.MAX_CODE:
            raise ValueError('Código vacío o más de 48.000 caracteres en total. Reduce la selección; no se trunca.')
        files.append({'name':display,'code':code,'job':job})
        self.render_files(workspace)

    def render_files(self,workspace='ai'):
        tree=self.file_lists[workspace]
        files=self.local_files if workspace=='local' else self.files
        tree.delete(*tree.get_children())
        for index,file in enumerate(files):
            tree.insert('','end',iid=str(index),values=(file['name'],len(file['code'])))
        self.counts[workspace].set(f'{len(files)} {"archivo" if len(files)==1 else "archivos"} · {sum(len(f["code"]) for f in files):,} / 48.000 caracteres' if files else 'Sin archivos. Importa código para comenzar.')

    def import_files(self,workspace='ai'):
        try:
            self.ensure_idle()
            types='*.js *.mjs *.cjs' if workspace=='local' else '*.js *.mjs *.cjs *.java *.cs *.c *.h *.cpp'
            for file in filedialog.askopenfilenames(parent=self.app,title='Importar código',filetypes=[('Código',types)]):
                self.add_file(file,workspace=workspace)
        except Exception as exc:
            messagebox.showerror('No se pudo importar',str(exc),parent=self.app)

    def pick_results(self,workspace='ai'):
        if not self.app.active:
            messagebox.showinfo('Selecciona un análisis','Abre un análisis desde Resultados o Historial.',parent=self.app)
            return
        job=engine.JOBS[self.app.active]
        extensions=('.js','.mjs','.cjs') if workspace=='local' else EXTENSIONS
        files=[f['path'] for f in engine.result_files(job) if Path(f['path']).suffix.lower() in extensions]
        if not files:
            messagebox.showinfo('Sin código compatible','Este análisis no contiene archivos compatibles con esta sección.',parent=self.app)
            return
        dialog=tk.Toplevel(self.app)
        dialog.title('Código recuperado'); dialog.geometry('660x480'); dialog.configure(bg=BG)
        dialog.transient(self.app); dialog.grab_set()
        frame=ttk.Frame(dialog,padding=20); frame.pack(fill='both',expand=True)
        tree=ttk.Treeview(frame,show='tree',selectmode='extended')
        tree.pack(fill='both',expand=True)
        for i,file in enumerate(files):tree.insert('','end',iid=str(i),text=file)
        def add():
            try:
                self.ensure_idle()
                for item in tree.selection():
                    name=files[int(item)]
                    self.add_file(engine.safe_result(job,name),name,job['id'],workspace)
                dialog.destroy()
            except Exception as exc:messagebox.showerror('Selección inválida',str(exc),parent=dialog)
        ttk.Button(frame,text='Añadir seleccionados',command=add).pack(anchor='e',pady=12)

    def add_current(self):
        try:
            self.ensure_idle()
            if not self.app.active or not self.app.current_path:
                raise ValueError('Selecciona primero un archivo de código en Resultados.')
            job=engine.JOBS[self.app.active]
            self.add_file(engine.safe_result(job,self.app.current_path),self.app.current_path,job['id'])
            self.app.show('ai')
        except Exception as exc:messagebox.showerror('Código',str(exc),parent=self.app)

    def remove_files(self,workspace='ai'):
        if self.busy:return
        indices={int(i) for i in self.file_lists[workspace].selection()}
        if workspace=='local':self.local_files=[f for i,f in enumerate(self.local_files) if i not in indices]
        else:self.files=[f for i,f in enumerate(self.files) if i not in indices]
        self.render_files(workspace)

    def new_session(self, files, agents, kind):
        jobs={f.get('job') for f in files}
        job=next(iter(jobs)) if len(jobs)==1 else None
        clean=[{'name':f['name'],'code':f['code']} for f in files]
        self.session=core.Session(engine.DATA,clean,agents,job,kind)
        if self.details_open:self.toggle_details()
        self.render_session()
        self.refresh_history()
        self.app.show('review')

    def start_round(self):
        try:
            self.ensure_idle()
            ids=set(self.agent_tree.selection())
            agents=[dict(a) for a in self.settings.values['agents'] if a['id'] in ids]
            agents.sort(key=lambda a:core.ROLES.index(a['role']))
            if not 1<=len(agents)<=core.MAX_AGENTS:raise ValueError('Selecciona de 1 a 3 agentes.')
            self.pending_agents=[]
            for agent in agents:
                conn=dict(self.settings.connection(agent['connection']))
                secret=self.settings.key(conn['id'])
                conn.pop('secret',None)
                self.pending_agents.append((agent,conn,secret))
            snapshots=[dict(a, endpoint=c['url'], model=c['model'], provider=c['provider']) for a,c,_ in self.pending_agents]
            for _agent,_conn,secret in self.pending_agents:
                if secret and (any(secret in f['code'] for f in self.files) or any(secret in a['instructions'] for a in agents)):
                    raise ValueError('La selección o las instrucciones contienen una clave configurada. Elimínala antes de crear la sesión.')
            self.new_session(self.files,snapshots,'ai')
            self.index=0
            self.render_session()
            self.preview_next()
        except Exception as exc:messagebox.showerror('No se pudo preparar',str(exc),parent=self.app)

    def preview_next(self):
        if self.busy or not self.session or self.index>=len(self.pending_agents):return
        agent,conn,key=self.pending_agents[self.index]
        previous=[{'agent':r['agent'],'content':r['raw']} for r in self.session.value['results'] if r.get('raw')]
        messages=core.messages_for(agent,self.session.value['files'],previous)
        if key and any(key in m['content'] for m in messages):
            messagebox.showerror('Clave en contenido','El contenido contiene la clave configurada. Quítala del código o de las instrucciones antes de enviarlo.',parent=self.app)
            return
        dialog=tk.Toplevel(self.app)
        dialog.title('Vista previa exacta · '+agent['name']); dialog.geometry('900x720'); dialog.minsize(650,500)
        dialog.configure(bg=BG); dialog.transient(self.app); dialog.grab_set()
        frame=ttk.Frame(dialog,padding=22); frame.pack(fill='both',expand=True)
        ttk.Label(frame,text=f'{agent["name"]} · {agent["role"]} · {conn["model"]}',style='Section.TLabel').pack(anchor='w')
        ttk.Label(frame,text=f'Destino: {conn["url"]}\nUna llamada. Incluye instrucciones, código y resultados anteriores mostrados abajo. Puede consumir saldo del proveedor.',style='Muted.TLabel',wraplength=830).pack(anchor='w',pady=12)
        widget=text_widget(frame)
        set_text(widget,json.dumps({'model':conn['model'],'messages':messages,'stream':False,
                                   **({'format':'json','options':{'num_predict':4096}} if conn['provider']=='ollama' else {'max_tokens':4096})},ensure_ascii=False,indent=2))
        row=ttk.Frame(frame); row.pack(fill='x',pady=(12,0))
        ttk.Button(row,text='Volver sin enviar',command=dialog.destroy).pack(side='right')
        def send():
            dialog.destroy(); self.busy=True; self.cancel=threading.Event()
            self.session.value['status']='solicitando'; self.session.save()
            self.state.set('Solicitando: '+agent['name']+' · cancelar no garantiza evitar el cobro de una solicitud ya enviada.')
            self.next_button.configure(state='disabled')
            self.cancel_button.configure(state='normal')
            self.prepare_button.configure(state='disabled')
            self.local_button.configure(state='disabled')
            self.accept_button.configure(state='disabled')
            self.review_status.set('Analizando con '+agent['name']+'…')
            def work():
                try:
                    response=core.request(conn,key,messages,self.cancel)
                    self.events.put(('success',agent,response))
                except Exception as exc:self.events.put(('error',str(exc)))
            threading.Thread(target=work,daemon=True).start()
        ttk.Button(row,text='Enviar este mensaje',style='Primary.TButton',command=send).pack(side='right',padx=8)

    def cancel_round(self):
        if not self.busy and not self.pending_agents:
            return
        self.cancel.set()
        if self.session:
            self.session.value['status']='cancelado'; self.session.save()
        self.pending_agents=[]
        self.next_button.configure(state='disabled')
        self.cancel_button.configure(state='disabled')
        self.state.set('Ronda cancelada. Los resultados recibidos permanecen en el historial.')
        self.review_status.set('Ronda cancelada')
        self.refresh_history()

    def poll(self):
        try:
            while True:
                event=self.events.get_nowait()
                self.busy=False
                if event[0]=='local' and not self.cancel.is_set():
                    self.session.value['results']=event[1]
                    self.session.value['status']='completado'
                    self.state.set('Desofuscación local terminada. Revisa las diferencias antes de guardar una copia.')
                elif event[0]=='success' and not self.cancel.is_set():
                    agent,response=event[1:]
                    secrets=[secret for _a,_c,secret in self.pending_agents]
                    raw=core.redact(response['content'],secrets)
                    parsed=core.interpret(raw,self.session.value['files'])
                    self.session.value['results'].append({'agent':agent['name'],'raw':raw,'usage':response['usage'],**parsed})
                    self.index+=1
                    more=self.index<len(self.pending_agents)
                    self.session.value['status']='pendiente de revisión' if more else 'completado'
                    self.state.set('Resultado recibido. Revisa los cambios.'+(' El siguiente agente requiere otra vista previa.' if more else ''))
                    self.next_button.configure(state='normal' if more else 'disabled')
                    if not more:self.pending_agents=[]
                else:
                    self.session.value['status']='cancelado' if self.cancel.is_set() else 'error'
                    if event[0]=='error':self.session.value['error']=event[1]
                    self.state.set(self.session.value.get('error','Ronda cancelada.'))
                    self.pending_agents=[]
                    self.next_button.configure(state='disabled')
                self.session.save(); self.mirror(); self.render_session(); self.refresh_history()
                self.prepare_button.configure(state='normal')
                self.local_button.configure(state='normal')
                self.cancel_button.configure(state='normal' if self.pending_agents else 'disabled')
        except queue.Empty:
            pass
        self.app.after(100,self.poll)

    def local(self):
        try:
            self.ensure_idle()
            selected=list(self.local_files)
            if not selected:raise ValueError('Importa archivos JavaScript o carga el ejemplo para comenzar.')
            if any(Path(f['name']).suffix.lower() not in ('.js','.mjs','.cjs') for f in selected):
                raise ValueError('El desofuscador local solo admite JavaScript. Para otros lenguajes utiliza agentes.')
            self.new_session(selected,[],'local')
            self.cancel=threading.Event()
            self.pending_agents=[]
            self.busy=True; self.state.set('Analizando sintaxis JavaScript localmente…')
            self.prepare_button.configure(state='disabled')
            self.local_button.configure(state='disabled')
            self.accept_button.configure(state='disabled')
            self.cancel_button.configure(state='normal')
            self.review_status.set('Desofuscación local en curso…')
            self.next_button.configure(state='disabled')
            self.render_session()
            self.review_status.set('Desofuscación local en curso…')
            session=self.session
            def work():
                try:
                    results=[]
                    for file in session.value['files']:
                        transformed=deobfuscator.deobfuscate(file['code'])
                        proposal=[]
                        if transformed['code']!=file['code']:
                            proposal=[{'file':file['name'],'code':transformed['code'],'reason':'Reglas locales conservadoras; consulta el registro de transformaciones.',
                                       'original_sha256':hashlib.sha256(file['code'].encode()).hexdigest()}]
                        results.append({'agent':'Desofuscador local','summary':file['name']+f': {len(transformed["transformations"])} transformaciones.',
                                        'evidence':[json.dumps(t,ensure_ascii=False) for t in transformed['transformations']],
                                        'uncertainties':transformed['notes'],'proposals':proposal,'usage':{}})
                    self.events.put(('local',results))
                except Exception as exc:self.events.put(('error',str(exc)))
            # Local results share the same main-thread dispatcher without any network request.
            threading.Thread(target=work,daemon=True).start()
        except Exception as exc:messagebox.showerror('Desofuscación',str(exc),parent=self.app)

    def render_session(self):
        if not self.session:return
        value=self.session.value
        kind='Desofuscación local' if value['kind']=='local' else 'Análisis con IA'
        self.review_status.set(kind+' · '+value['status'].capitalize())
        next_ready=value['kind']=='ai' and self.index<len(self.pending_agents)
        if next_ready:
            self.next_button.pack(side='left',before=self.export_button)
            self.next_button.configure(state='disabled' if self.busy else 'normal')
        else:self.next_button.pack_forget()
        if self.busy or next_ready:
            self.cancel_button.pack(side='left',padx=8,before=self.export_button)
            self.cancel_button.configure(state='normal')
        else:self.cancel_button.pack_forget()
        parts=[]
        details=[]
        self.proposals=[]
        labels=[]
        for result in value['results']:
            parts.extend([result['agent'],result['summary']])
            if result['uncertainties']:
                parts.append('Observaciones: '+' '.join(result['uncertainties']))
            parts.append('')
            details.append(result['agent'])
            for evidence in result['evidence']:
                try:
                    record=json.loads(evidence)
                    if not isinstance(record,dict) or 'rule' not in record:raise ValueError()
                    details.extend([f'Línea {record["line"]} · {record["rule"]}',f'Antes: {record["before"]}',f'Después: {record["after"]}',''])
                except (ValueError,TypeError,KeyError):details.append(evidence)
            if result.get('usage'):
                details.append('Consumo informado: '+', '.join(f'{key}: {amount}' for key,amount in result['usage'].items()))
            for proposal in result['proposals']:
                self.proposals.append(proposal)
                labels.append(f'{len(labels)+1}. {result["agent"]} · {proposal["file"]}')
        if value.get('error'):parts.append(value['error'])
        if value['accepted']:parts.append(f'{len(value["accepted"])} copias guardadas. Los archivos originales se conservan.')
        if value['kind']=='ai' and self.proposals:parts.append('Las propuestas de IA requieren revisión; su equivalencia no está garantizada.')
        set_text(self.result_text,'\n'.join(parts).strip() or 'La sesión está preparada. Revisa el mensaje antes de enviarlo.')
        set_text(self.details,'\n'.join(details).strip() or 'Todavía no hay registros técnicos para esta sesión.')
        self.export_button.configure(state='normal')
        self.proposal_combo.configure(values=labels)
        self.proposal_var.set(labels[0] if labels else '')
        self.show_diff()

    def selected_proposal(self):
        index=self.proposal_combo.current()
        return self.proposals[index] if index>=0 else None

    def show_diff(self):
        proposal=self.selected_proposal()
        self.accept_button.configure(state='normal' if proposal and not self.busy else 'disabled')
        if not proposal:
            self.change_reason.set('No se propusieron cambios. Puedes consultar el resumen y los detalles técnicos.')
            original=self.session.value['files'][0]['code'] if self.session and self.session.value['files'] else 'Aquí aparecerá el código original.'
            set_text(self.original_code,original)
            set_text(self.proposed_code,'Todavía no hay una propuesta de código para comparar.')
            return
        original=next(f['code'] for f in self.session.value['files'] if f['name']==proposal['file'])
        self.change_reason.set(proposal['reason'])
        set_text(self.original_code,original)
        set_text(self.proposed_code,proposal['code'])
        for opcode,i1,i2,j1,j2 in difflib.SequenceMatcher(None,original.splitlines(),proposal['code'].splitlines(),autojunk=False).get_opcodes():
            if opcode!='equal':
                if i2>i1:self.original_code.tag_add('changed',f'{i1+1}.0',f'{i2+1}.0')
                if j2>j1:self.proposed_code.tag_add('changed',f'{j1+1}.0',f'{j2+1}.0')

    def accept(self):
        try:
            self.ensure_idle()
            proposal=self.selected_proposal()
            if not proposal:raise ValueError('Selecciona una propuesta para comparar y guardar.')
            if not messagebox.askyesno('Guardar copia revisada','¿Guardar esta propuesta como una copia separada? Revisa las diferencias; la IA puede cambiar el comportamiento.',parent=self.app):return
            path=self.session.accept(proposal)
            self.mirror(); self.render_session()
            self.state.set('Copia guardada: '+str(path))
        except Exception as exc:messagebox.showerror('No se pudo guardar',str(exc),parent=self.app)

    def mirror(self):
        job=self.session.value.get('job')
        if not job or job not in engine.JOBS:return
        destination=engine.DATA/job/'result'/'ai'/self.session.ident
        destination.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(self.session.folder/'session.json',destination/'session.json')
        for item in self.session.value['accepted']:
            source=(self.session.folder/item['copy']).resolve()
            if not source.is_relative_to(self.session.folder.resolve()):continue
            output=destination/item['copy']; output.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,output)

    def refresh_history(self):
        self.history.delete(*self.history.get_children())
        self.history_paths={}
        for file in sorted((engine.DATA/'ai').glob('*/session.json'),key=lambda p:p.stat().st_mtime,reverse=True):
            try:
                value=json.loads(file.read_text(encoding='utf-8'))
                self.history_paths[value['id']]=file
                self.history.insert('','end',iid=value['id'],values=(value['created'][:19].replace('T',' '),value['kind'],value['status'],', '.join(f['name'] for f in value['files'])))
            except (ValueError,OSError,KeyError):continue

    def open_history(self):
        selection=self.history.selection()
        if not selection or self.busy:return
        self.session=core.Session.load(self.history_paths[selection[0]])
        if self.details_open:self.toggle_details()
        self.pending_agents=[]; self.index=0
        self.next_button.configure(state='disabled')
        self.render_session(); self.app.show('review')
        self.cancel_button.configure(state='disabled')
        self.state.set('Sesión guardada. Inicia una nueva ronda desde Análisis con IA o Desofuscador local.')

    def export(self):
        if not self.session:return
        path=filedialog.asksaveasfilename(parent=self.app,title='Exportar sesión sin claves',defaultextension='.zip',initialfile='strata-'+self.session.ident[:8]+'.zip',filetypes=[('ZIP','*.zip')])
        if path:
            try:self.session.export(path); self.state.set('Sesión exportada sin configuración ni claves.')
            except Exception as exc:messagebox.showerror('Exportación',str(exc),parent=self.app)
