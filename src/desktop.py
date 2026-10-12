"""Native Tk desktop. This entry point never starts a web server."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import re
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from datetime import datetime
import engine
import ai_ui
import tool_ui

BG = '#090909'
PANEL = '#131313'
RAISED = '#202020'
FG = '#ededed'
MUTED = '#a3a3a3'
LINE = '#303030'
FONT = 'Segoe UI Variable'
MONO = 'Cascadia Code'
STATES = {'queued':'En cola','running':'Analizando','completed':'Código recuperado','partial':'Inspección sin código','failed':'Error'}


class Strata(tk.Tk):
    def __init__(self, initial=None):
        super().__init__()
        self.title('Strata | Ingeniería reversa')
        self.geometry('1320x860')
        self.minsize(1120, 760)
        self.configure(bg=BG)
        self.mode = tk.StringVar(value='safe')
        self.target = tk.StringVar(value='vm')
        self.vm_kind = tk.StringVar(value='Windows Sandbox')
        self.engine_choice = tk.StringVar(value='Combinado · motores compatibles')
        self.engine_hint = tk.StringVar(value='Coordina los motores compatibles disponibles y reúne sus aportes sin priorizarlos.')
        self.engine_labels={'Combinado · motores compatibles':'combined','Automático · un motor':'auto'}
        self.file_label = tk.StringVar(value='Ningún archivo seleccionado')
        self.note = tk.StringVar(value='Seguro inspecciona el archivo sin abrir la aplicación.')
        self.status = tk.StringVar(value='Listo. Procesamiento local, sin navegador.')
        self.phase = tk.StringVar(value='Selecciona un archivo para comenzar')
        self.result_title = tk.StringVar(value='Resultados')
        self.metadata = tk.StringVar(value='')
        self.filter = tk.StringVar()
        self.search = tk.StringVar()
        self.code_path = tk.StringVar(value='Selecciona un archivo en el explorador')
        self.selected = None
        self.active = None
        self.current_content = ''
        self.current_path = ''
        self.last_files = None
        self.last_logs = None
        self.match_cursor = '1.0'
        self.match_count = tk.StringVar(value='')
        self.style_setup()
        icon = engine.ROOT / 'Strata.ico'
        if icon.exists():
            self.iconbitmap(str(icon))
        engine.load_jobs()
        self.build()
        self.bind('<Control-o>', lambda event: self.choose())
        self.bind('<Control-f>', lambda event: self.search_entry.focus_set())
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.filter.trace_add('write', lambda *_: self.render_tree())
        self.mode.trace_add('write', lambda *_: self.mode_changed())
        self.target.trace_add('write', lambda *_: self.mode_changed())
        threading.Thread(target=engine.worker, daemon=True).start()
        self.after(80, self.dark_title)
        self.after(450, self.poll)
        if initial:
            self.select_file(initial)

    def style_setup(self):
        style = ttk.Style(self)
        style.theme_use('clam')
        style.configure('.', background=BG, foreground=FG, font=(FONT,10), bordercolor=LINE,
                        darkcolor=LINE, lightcolor=LINE, focuscolor=FG)
        style.configure('TFrame', background=BG)
        style.configure('Panel.TFrame', background=PANEL)
        style.configure('TLabel', background=BG, foreground=FG)
        style.configure('Muted.TLabel', foreground=MUTED)
        style.configure('Panel.TLabel', background=PANEL)
        style.configure('Eyebrow.TLabel', foreground=MUTED, font=(FONT,9))
        style.configure('Title.TLabel', font=(FONT,28,'bold'))
        style.configure('Section.TLabel', font=(FONT,12,'bold'))
        style.configure('TButton', background=RAISED, foreground=FG, padding=(16,10), borderwidth=0, font=(FONT,10))
        style.map('TButton', background=[('active','#343434'),('disabled','#171717')], foreground=[('disabled','#777777')])
        style.configure('Primary.TButton', background=FG, foreground='#101010', font=(FONT,10,'bold'))
        style.map('Primary.TButton', background=[('active','#cccccc'),('disabled','#343434')], foreground=[('disabled','#969696')])
        style.configure('Nav.TButton', background=PANEL, padding=(12,10), anchor='w')
        style.map('Nav.TButton', background=[('active','#252525')], foreground=[('active',FG)])
        style.configure('Selected.Nav.TButton', background=FG, foreground=BG, font=(FONT,10,'bold'))
        style.map('Selected.Nav.TButton', background=[('active',FG),('pressed','#cccccc')], foreground=[('active',BG),('pressed',BG)])
        style.configure('TRadiobutton', background=PANEL, foreground=FG, padding=7, indicatorcolor='#5d5d5d')
        style.map('TRadiobutton', background=[('active',RAISED)], indicatorcolor=[('selected','#dedede')], foreground=[('disabled','#888888')])
        style.configure('TCheckbutton', background=PANEL, foreground=FG)
        style.configure('TEntry', fieldbackground=PANEL, foreground=FG, padding=8, insertcolor=FG, borderwidth=1)
        style.configure('TCombobox', fieldbackground=PANEL, foreground=FG, padding=7, arrowcolor=FG)
        style.map('TCombobox', fieldbackground=[('readonly',PANEL)], foreground=[('readonly',FG)], selectbackground=[('readonly',PANEL)])
        style.configure('Treeview', background=PANEL, fieldbackground=PANEL, foreground='#cccccc', rowheight=29, borderwidth=0)
        style.configure('Treeview.Heading', background=RAISED, foreground=MUTED, padding=9)
        style.map('Treeview', background=[('selected','#373737')], foreground=[('selected','#ffffff')])
        style.configure('TNotebook', background=BG, borderwidth=0)
        style.configure('TNotebook.Tab', background=PANEL, foreground=MUTED, padding=(19,10), borderwidth=0)
        style.map('TNotebook.Tab', background=[('selected',RAISED)], foreground=[('selected',FG)])
        style.configure('Horizontal.TProgressbar', troughcolor=PANEL, background='#999999', borderwidth=0)
        style.configure('TSeparator', background=LINE)
        for orient in ('Vertical','Horizontal'):
            style.configure(orient+'.TScrollbar', background='#444444', troughcolor=PANEL, lightcolor='#444444', darkcolor='#444444', bordercolor=PANEL, arrowcolor=MUTED, borderwidth=0)
            style.map(orient+'.TScrollbar',background=[('active','#666666'),('pressed','#777777')])

    def dark_title(self):
        try:
            handle = ctypes.windll.user32.GetParent(self.winfo_id())
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(handle,20,ctypes.byref(value),4)
        except (AttributeError, OSError):
            pass

    def label(self, parent, text=None, style='TLabel', **kw):
        return ttk.Label(parent, text=text, style=style, **kw)

    def build(self):
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        sidebar = ttk.Frame(self, style='Panel.TFrame', width=242, padding=(20,26))
        sidebar.grid(row=0,column=0,sticky='ns')
        sidebar.pack_propagate(False)
        self.label(sidebar,'STRATA','Panel.TLabel',font=(FONT,22,'bold')).pack(anchor='w')
        self.label(sidebar,'INGENIERÍA REVERSA','Panel.TLabel',font=(FONT,8),foreground=MUTED).pack(anchor='w',pady=(5,24))
        self.nav = {}
        self.nav_names = {}
        for key, name in [('new','Decompilar app'),('result','Código recuperado'),('ai','Análisis con IA'),('local','Desofuscador local'),('review','Revisión de cambios'),('agents','Agentes y modelos'),('history','Historial'),('engines','Motores y ayuda')]:
            group = {'new':'Aplicaciones','ai':'Código e IA','agents':'Configuración','history':'Biblioteca'}.get(key)
            if group:
                self.label(sidebar,group,'Panel.TLabel',font=(FONT,9),foreground=MUTED).pack(anchor='w',pady=(12,6))
            button = ttk.Button(sidebar,text=name,style='Nav.TButton',command=lambda k=key:self.show(k))
            button.pack(fill='x',pady=4)
            self.nav[key] = button
            self.nav_names[key] = name
        foot = ttk.Frame(sidebar, style='Panel.TFrame')
        foot.pack(side='bottom',fill='x')
        self.label(foot,'DESKTOP / PORTABLE','Panel.TLabel',font=(FONT,8),foreground=MUTED).pack(anchor='w')
        self.label(foot,'Sin navegador\nIA opcional\nEnvíos revisables','Panel.TLabel',foreground=MUTED,font=(FONT,9),justify='left').pack(anchor='w',pady=(15,0))
        body=ttk.Frame(self,padding=(34,28,34,12))
        body.grid(row=0,column=1,sticky='nsew')
        body.rowconfigure(0,weight=1)
        body.columnconfigure(0,weight=1)
        self.pages={}
        for name in self.nav:
            frame=ttk.Frame(body)
            frame.grid(row=0,column=0,sticky='nsew')
            self.pages[name]=frame
        self.build_new(self.pages['new'])
        self.build_result(self.pages['result'])
        self.build_history(self.pages['history'])
        self.build_engines(self.pages['engines'])
        self.ai = ai_ui.AgentsUI(self,self.pages['agents'],self.pages['ai'],self.pages['local'],self.pages['review'])
        ttk.Separator(body).grid(row=1,column=0,sticky='ew',pady=(16,9))
        self.label(body,textvariable=self.status,style='Muted.TLabel',font=(FONT,9)).grid(row=2,column=0,sticky='w')
        self.show('new')

    def build_new(self, parent):
        self.label(parent,'ANÁLISIS LOCAL','Eyebrow.TLabel').pack(anchor='w',pady=(0,12))
        self.label(parent,'Comprende la aplicación.','Title.TLabel').pack(anchor='w')
        self.label(parent,'Selecciona un archivo. Strata detecta el formato y el motor adecuado.','Muted.TLabel').pack(anchor='w',pady=(10,30))
        panel=ttk.Frame(parent,style='Panel.TFrame',padding=24)
        panel.pack(fill='x')
        self.label(panel,'01  ARCHIVO','Panel.TLabel',font=(FONT,9),foreground=MUTED).pack(anchor='w')
        row=ttk.Frame(panel,style='Panel.TFrame')
        row.pack(fill='x',pady=(14,12))
        self.label(row,textvariable=self.file_label,style='Panel.TLabel',font=(FONT,12),wraplength=590).pack(side='left',fill='x',expand=True)
        ttk.Button(row,text='Seleccionar archivo',command=self.choose).pack(side='right',padx=(15,0))
        self.label(panel,'EXE / DLL / APK / DEX / JAR / CLASS / ELF / Mach-O · hasta 100 MB',style='Panel.TLabel',foreground=MUTED,font=(FONT,9)).pack(anchor='w')
        motorrow=ttk.Frame(panel,style='Panel.TFrame'); motorrow.pack(fill='x',pady=(16,0))
        self.label(motorrow,'Motor de decompilación','Panel.TLabel',foreground=MUTED).pack(side='left',padx=(0,12))
        self.engine_combo=ttk.Combobox(motorrow,textvariable=self.engine_choice,values=tuple(self.engine_labels),state='readonly',width=33)
        self.engine_combo.pack(side='left')
        ttk.Button(motorrow,text='Configurar motores',command=lambda:self.show('engines')).pack(side='right')
        self.label(panel,textvariable=self.engine_hint,style='Panel.TLabel',foreground=MUTED,font=(FONT,9),wraplength=780).pack(anchor='w',pady=(6,0))
        ttk.Separator(panel).pack(fill='x',pady=16)
        self.label(panel,'02  MODO DE DECOMPILACIÓN','Panel.TLabel',font=(FONT,9),foreground=MUTED).pack(anchor='w')
        modes=ttk.Frame(panel,style='Panel.TFrame')
        modes.pack(fill='x',pady=(14,5))
        for value,title,desc in [('safe','Seguro','Decompila sin abrir la aplicación.'),('normal','Normal','Decompila y permite abrirla en PC o VM.')]:
            box=ttk.Frame(modes,style='Panel.TFrame',padding=(0,0,34,0))
            box.pack(side='left',fill='x',expand=True)
            ttk.Radiobutton(box,text=title,variable=self.mode,value=value).pack(anchor='w')
            self.label(box,desc,'Panel.TLabel',foreground=MUTED,font=(FONT,10)).pack(anchor='w',padx=7,pady=4)
        self.execution_row=ttk.Frame(panel,style='Panel.TFrame')
        self.execution_row.pack(fill='x',pady=(13,0))
        self.label(self.execution_row,'Abrir en:','Panel.TLabel',foreground=MUTED).pack(side='left',padx=(7,15))
        self.pc_radio=ttk.Radiobutton(self.execution_row,text='Este PC',variable=self.target,value='pc')
        self.pc_radio.pack(side='left')
        self.vm_radio=ttk.Radiobutton(self.execution_row,text='VM',variable=self.target,value='vm')
        self.vm_radio.pack(side='left',padx=(15,10))
        self.vm_choice=ttk.Combobox(self.execution_row,textvariable=self.vm_kind,values=('Windows Sandbox','VM propia (exportar paquete)'),state='readonly',width=29)
        self.vm_choice.pack(side='left')
        self.label(panel,textvariable=self.note,style='Panel.TLabel',foreground=MUTED,wraplength=790).pack(anchor='w',pady=(22,8))
        actions=ttk.Frame(parent)
        actions.pack(fill='x',pady=(25,15))
        self.start_button=ttk.Button(actions,text='Decompilar aplicación',style='Primary.TButton',command=self.start,state='disabled')
        self.start_button.pack(side='right')
        ttk.Button(actions,text='Abrir muestra de prueba',command=lambda:self.select_file(engine.ROOT/'samples/Hello.class')).pack(side='left')
        self.label(parent,'El código recuperado es una aproximación. La ofuscación y los formatos protegidos pueden limitar el resultado.',style='Muted.TLabel',wraplength=800,font=(FONT,9)).pack(anchor='w',pady=(12,0))
        self.mode_changed()

    def build_result(self,parent):
        top=ttk.Frame(parent)
        top.pack(fill='x')
        self.label(top,textvariable=self.result_title,style='Section.TLabel',font=(FONT,20,'bold')).pack(side='left')
        self.export_button=ttk.Button(top,text='Exportar ZIP',command=self.export,state='disabled')
        self.export_button.pack(side='right')
        self.launch_button=ttk.Button(top,text='Abrir aplicación',style='Primary.TButton',command=self.open_application,state='disabled')
        self.launch_button.pack(side='right',padx=10)
        advanced=ttk.Frame(parent); advanced.pack(fill='x',pady=(10,0))
        self.advanced_button=ttk.Button(advanced,text='Análisis avanzado',command=lambda:self.tools_ui.open_advanced(),state='disabled')
        self.advanced_button.pack(side='left')
        self.import_code_button=ttk.Button(advanced,text='Importar código exportado',command=lambda:self.tools_ui.import_code(),state='disabled')
        self.import_code_button.pack(side='left',padx=8)
        self.combined_button=ttk.Button(advanced,text='Ver todos los aportes',command=lambda:self.load_file('combined-summary.txt'),state='disabled')
        self.combined_button.pack(side='left',padx=(0,8))
        self.review_motors_button=ttk.Button(advanced,text='Revisar con IA',command=self.review_motor_results,state='disabled')
        self.review_motors_button.pack(side='left')
        self.label(parent,textvariable=self.phase,style='Muted.TLabel',wraplength=850).pack(anchor='w',pady=(12,8))
        self.progress=ttk.Progressbar(parent,mode='indeterminate')
        self.progress.pack(fill='x',pady=(0,12))
        self.label(parent,textvariable=self.metadata,style='Muted.TLabel',font=(MONO,9),wraplength=850,justify='left').pack(anchor='w',pady=(0,16))
        self.logbox=tk.Text(parent,height=5,bg=PANEL,fg=MUTED,relief='flat',font=(MONO,9),wrap='word',padx=12,pady=10,state='disabled')
        self.logbox.pack(side='bottom',fill='x',pady=(12,0))
        split=ttk.Panedwindow(parent,orient='horizontal')
        split.pack(fill='both',expand=True)
        left=ttk.Frame(split,style='Panel.TFrame',padding=12)
        split.add(left,weight=1)
        self.label(left,'EXPLORADOR','Panel.TLabel',font=(FONT,9),foreground=MUTED).pack(anchor='w',pady=(0,12))
        self.label(left,'Buscar archivos','Panel.TLabel',foreground=MUTED,font=(FONT,9)).pack(anchor='w',pady=(0,5))
        ttk.Entry(left,textvariable=self.filter,width=25).pack(fill='x',pady=(0,12))
        self.tree=ttk.Treeview(left,show='tree',selectmode='browse',height=18)
        self.tree.pack(fill='both',expand=True)
        self.tree.bind('<<TreeviewSelect>>',self.file_selected)
        right=ttk.Frame(split)
        split.add(right,weight=4)
        tools=ttk.Frame(right)
        tools.pack(fill='x',pady=(0,8))
        self.label(tools,textvariable=self.code_path,style='Muted.TLabel',font=(MONO,9),wraplength=520).pack(side='left',fill='x',expand=True)
        ttk.Button(tools,text='Copiar',command=self.copy_code).pack(side='right')
        ttk.Button(tools,text='Analizar con IA',command=lambda:self.ai.add_current()).pack(side='right',padx=6)
        searchrow=ttk.Frame(right)
        searchrow.pack(fill='x',pady=(0,9))
        self.label(searchrow,'Buscar:',style='Muted.TLabel',font=(FONT,9)).pack(side='left',padx=(0,8))
        self.search_entry=ttk.Entry(searchrow,textvariable=self.search,width=27)
        self.search_entry.pack(side='left')
        self.search_entry.bind('<Return>',lambda _:self.find_next())
        ttk.Button(searchrow,text='Buscar siguiente',command=self.find_next).pack(side='left',padx=8)
        self.label(searchrow,textvariable=self.match_count,style='Muted.TLabel').pack(side='left')
        textframe=ttk.Frame(right,style='Panel.TFrame')
        textframe.pack(fill='both',expand=True)
        textframe.rowconfigure(0,weight=1)
        textframe.columnconfigure(1,weight=1)
        self.gutter=tk.Text(textframe,bg=PANEL,fg='#666666',font=(MONO,10),width=5,wrap='none',relief='flat',padx=7,pady=16,state='disabled',takefocus=0)
        self.gutter.grid(row=0,column=0,sticky='ns')
        self.code=tk.Text(textframe,bg=PANEL,fg='#d0d0d0',insertbackground=FG,selectbackground='#424242',
                          font=(MONO,10),wrap='none',relief='flat',padx=16,pady=16,undo=False,state='disabled')
        self.code.grid(row=0,column=1,sticky='nsew')
        y=ttk.Scrollbar(textframe,orient='vertical',command=self.code.yview)
        y.grid(row=0,column=2,sticky='ns')
        x=ttk.Scrollbar(textframe,orient='horizontal',command=self.code.xview)
        x.grid(row=1,column=1,sticky='ew')
        def sync_scroll(first,last):
            y.set(first,last)
            self.gutter.yview_moveto(first)
        self.code.configure(yscrollcommand=sync_scroll,xscrollcommand=x.set)
        self.code.tag_configure('keyword',foreground='#e0c5a1')
        self.code.tag_configure('comment',foreground='#777777')
        self.code.tag_configure('string',foreground='#b6c8b1')
        self.code.tag_configure('match',background='#6c6437',foreground='white')
        self.show_text('El código recuperado y las evidencias aparecerán aquí.')

    def build_history(self,parent):
        self.label(parent,'Historial','Title.TLabel').pack(anchor='w')
        self.label(parent,'Los análisis se guardan dentro de la carpeta portable.','Muted.TLabel').pack(anchor='w',pady=(10,25))
        self.history_notebook=ttk.Notebook(parent)
        self.history_notebook.pack(fill='both',expand=True)
        apps=ttk.Frame(self.history_notebook,padding=14)
        self.history_notebook.add(apps,text='Aplicaciones')
        self.history=ttk.Treeview(apps,columns=('name','mode','format','state'),show='headings',selectmode='browse')
        for col,title,width in [('name','Archivo',260),('mode','Modo / entorno',150),('format','Formato',160),('state','Estado',150)]:
            self.history.heading(col,text=title)
            self.history.column(col,width=width,minwidth=80)
        self.history.pack(fill='both',expand=True)
        self.history.bind('<Double-1>',lambda _:self.open_history())
        ttk.Button(apps,text='Abrir análisis seleccionado',command=self.open_history).pack(anchor='e',pady=18)

    def build_engines(self,parent):
        self.label(parent,'Motores y entornos','Title.TLabel').pack(anchor='w')
        self.label(parent,'Motores incluidos y conexiones opcionales con dotPeek y Binary Ninja.','Muted.TLabel').pack(anchor='w',pady=(10,18))
        notebook=ttk.Notebook(parent); notebook.pack(fill='both',expand=True)
        included=ttk.Frame(notebook,padding=16); external=ttk.Frame(notebook,padding=16)
        notebook.add(included,text='Incluidos y ayuda'); notebook.add(external,text='Herramientas externas')
        self.tools_ui=tool_ui.ToolSettings(self,external)
        parent=included
        available=engine.engines()
        for key,name,formats in [('jadx','JADX','APK, DEX, CLASS, JAR: código Java'),('ilspy','ILSpy','EXE y DLL de .NET: código C#'),('ghidra','Ghidra','PE nativo, ELF y Mach-O: pseudocódigo C'),('sandbox','Windows Sandbox','Apertura aislada de EXE Windows; característica opcional del sistema')]:
            row=ttk.Frame(parent,style='Panel.TFrame',padding=17)
            row.pack(fill='x',pady=5)
            self.label(row,name,'Panel.TLabel',font=(FONT,12,'bold')).pack(side='left')
            self.label(row,'Disponible' if available[key] else 'No disponible','Panel.TLabel',foreground='#b6c8b1' if available[key] else '#d6bfa0').pack(side='right')
            self.label(row,formats,'Panel.TLabel',foreground=MUTED).pack(side='left',padx=25)
        helptext='Seguro analiza sin ejecutar la muestra. Normal permite abrir EXE Windows o JAR ejecutables en este PC, EXE en Sandbox, o exportar un paquete para una VM Windows propia.\n\nAPK necesita Android; ELF necesita Linux; Mach-O necesita macOS. Su decompilación estática puede hacerse aquí, pero no se abren automáticamente en Windows. DLL, DEX y CLASS no son aplicaciones ejecutables por sí solos.\n\nLa ejecución añade observación del proceso; no elimina automáticamente protecciones ni recupera código original de cualquier aplicación.'
        self.label(parent,helptext,'Muted.TLabel',wraplength=825,justify='left').pack(anchor='w',pady=25)
        ttk.Button(parent,text='Abrir carpeta portable',command=lambda:os.startfile(engine.ROOT)).pack(anchor='w')

    def show(self,name):
        self.current_page = name
        self.pages[name].tkraise()
        self.title('Strata · '+self.nav_names[name])
        for key,button in self.nav.items():
            button.configure(style='Selected.Nav.TButton' if key==name else 'Nav.TButton')
        if name=='history':
            self.render_history()
            if hasattr(self,'ai'):self.ai.refresh_history()

    def mode_changed(self):
        normal=self.mode.get()=='normal'
        state='normal' if normal else 'disabled'
        self.pc_radio.configure(state=state)
        self.vm_radio.configure(state=state)
        self.vm_choice.configure(state='readonly' if normal and self.target.get()=='vm' else 'disabled')
        if not normal:
            self.note.set('Seguro inspecciona y decompila el archivo sin abrir la aplicación.')
        elif self.target.get()=='pc':
            self.note.set('PC abre la aplicación con los permisos de tu usuario. La apertura requiere confirmación después del análisis.')
        else:
            self.note.set('VM: elige Windows Sandbox o exporta un paquete para tu VM Windows. La apertura se confirma después del análisis.')

    def choose(self):
        path=filedialog.askopenfilename(parent=self,title='Seleccionar aplicación',filetypes=[('Aplicaciones y binarios','*.exe *.dll *.apk *.dex *.jar *.class *.so *.elf *.dylib *.bin *.zip'),('Todos los archivos','*.*')])
        if path:self.select_file(path)

    def select_file(self,path):
        path=Path(path)
        if not path.is_file() or not 0<path.stat().st_size<=engine.MAX_UPLOAD:
            messagebox.showerror('Archivo no válido','Selecciona un archivo de 1 byte a 100 MB.',parent=self)
            return
        self.selected=path
        self.refresh_engine_choices(reset=True)
        size=path.stat().st_size
        size_text=f'{size:,} bytes' if size<1024 else f'{size/1024:.1f} KB' if size<1048576 else f'{size/1048576:.2f} MB'
        self.file_label.set(f'{path.name}\n{size_text}')
        self.start_button.configure(state='normal')
        self.status.set(str(path))
        self.show('new')

    def start(self):
        if not self.selected:return
        try:
            job=engine.create_job(self.selected,self.mode.get(),self.target.get(),'external' if self.vm_kind.get().startswith('VM propia') else 'sandbox',self.engine_labels[self.engine_choice.get()])
            self.activate_job(job)
            engine.TASKS.put_nowait(job)
            self.show('result')
        except Exception as exc:
            messagebox.showerror('No se pudo iniciar',str(exc),parent=self)

    def refresh_engine_choices(self,reset=False):
        default=engine.classify(self.selected.read_bytes())[1] if self.selected else None
        names={'jadx':'JADX','ilspy':'ILSpy','ghidra':'Ghidra','dotpeek':'dotPeek · exportación en su interfaz','binaryninja':'Binary Ninja · API automática'}
        self.engine_labels={'Combinado · motores compatibles':'combined','Automático · un motor':'auto'}
        available=engine.engines()
        for key in engine.engine_options(default):
            label=names[key]+(' · sin configurar' if not available.get(key) else '')
            self.engine_labels[label]=key
        self.engine_combo.configure(values=tuple(self.engine_labels))
        if reset or self.engine_choice.get() not in self.engine_labels:self.engine_choice.set('Combinado · motores compatibles')
        compatible=', '.join(names[key].split(' · ')[0] for key in engine.engine_options(default))
        self.engine_hint.set('Combinado reúne los aportes compatibles: '+compatible+'. Los que falten se indicarán en el resumen.' if default else 'El formato se inspecciona; los motores compatibles se identificarán al seleccionar el archivo.')

    def review_motor_results(self):
        self.show('ai')
        self.ai.pick_results()

    def activate_job(self,job):
        self.active=job['id']
        self.current_path=''
        self.current_content=''
        self.last_files=None
        self.last_logs=None
        self.filter.set('')
        self.search.set('')
        self.match_count.set('')
        self.code_path.set('Selecciona un archivo en el explorador')
        self.show_text('Preparando resultados…')
        self.refresh_result()

    def poll(self):
        if self.active:self.refresh_result()
        self.after(600,self.poll)

    def refresh_result(self):
        job=engine.JOBS.get(self.active)
        if not job:return
        with engine.LOCK:
            status=job['status']
            meta=job.get('metadata')
            files=engine.result_files(job)
            logs=list(job['logs'])
            normal=job.get('normal') or {}
            notice=job.get('error') or job.get('notice')
        running=status in ('queued','running')
        external_kind='dotPeek' if (meta or {}).get('format')=='Windows .NET' else 'Binary Ninja'
        self.advanced_button.configure(state='normal' if meta and not running else 'disabled',text='Abrir en '+external_kind)
        self.import_code_button.configure(state='normal' if meta and not running else 'disabled')
        combined=job.get('requested_engine')=='combined'
        self.combined_button.configure(state='normal' if combined and not running else 'disabled')
        self.review_motors_button.configure(state='normal' if files and not running else 'disabled')
        self.result_title.set(job['name'])
        self.phase.set(job['phase'] + (f' · {notice}' if notice else '') + (f'\n{normal["reason"]}' if normal else ''))
        self.status.set(f'{STATES[status]} · {"Seguro" if job["mode"]=="safe" else "Normal / "+job.get("target","vm").upper()}')
        if running:self.progress.start(18)
        else:self.progress.stop()
        self.export_button.configure(state='normal' if files and not running else 'disabled')
        self.launch_button.configure(state='normal' if normal.get('ready') and not running else 'disabled',text='Sin ejecución (Seguro)' if job['mode']=='safe' else 'Exportar paquete VM' if normal.get('target')=='external' else 'Abrir en PC' if normal.get('target')=='pc' else 'Abrir en VM')
        if meta:
            self.metadata.set(f'{meta["format"]}  |  {meta["size"]:,} bytes  |  Motor: {(meta["engine"] or "inspección").upper()}  |  Entropía: {meta["entropy"]}/8\nSHA-256: {meta["sha256"]}')
        if files!=self.last_files:
            self.last_files=files
            self.render_tree()
        if logs!=self.last_logs:
            self.last_logs=logs
            self.logbox.configure(state='normal')
            self.logbox.delete('1.0','end')
            self.logbox.insert('end','\n'.join(l['time']+'  '+l['message'] for l in logs))
            self.logbox.configure(state='disabled')
            self.logbox.see('end')
        if not running and not self.current_path and files:
            first=(next((f for f in files if f['path']=='combined-summary.txt'),None) if combined else None) or next((f for f in files if f['path'].endswith(('.java','.cs','.c'))),None) or next((f for f in files if f['path']=='report.json'),files[0])
            self.load_file(first['path'])

    def render_tree(self):
        if not hasattr(self,'tree'):return
        self.tree.delete(*self.tree.get_children())
        query=self.filter.get().lower()
        folders=set()
        for entry in self.last_files or []:
            path=entry['path']
            if query not in path.lower():continue
            parts=path.split('/')
            parent=''
            for i,part in enumerate(parts[:-1]):
                key='dir:'+'/'.join(parts[:i+1])
                if key not in folders:
                    self.tree.insert(parent,'end',iid=key,text=part,open=True)
                    folders.add(key)
                parent=key
            self.tree.insert(parent,'end',iid='file:'+path,text=parts[-1],values=(path,))
        if self.current_path and self.tree.exists('file:'+self.current_path):
            self.tree.selection_set('file:'+self.current_path)

    def file_selected(self,_event):
        selected=self.tree.selection()
        if selected and selected[0].startswith('file:'):
            path=selected[0][5:]
            if path!=self.current_path:self.load_file(path)

    def load_file(self,path):
        try:
            file=engine.safe_result(engine.JOBS[self.active],path)
            if file.stat().st_size>2*1024*1024:
                raise ValueError('El visor admite hasta 2 MB. Exporta el ZIP para leer el archivo completo.')
            self.current_content=file.read_text(encoding='utf-8',errors='replace')
            self.current_path=path
            if self.tree.exists('file:'+path):
                self.tree.selection_set('file:'+path)
            self.code_path.set(path)
            self.show_text(self.current_content,syntax=path.endswith(('.java','.cs','.c')))
            self.match_cursor='1.0'
        except Exception as exc:
            self.show_text(str(exc))

    def show_text(self,text,syntax=False):
        self.code.configure(state='normal')
        self.code.delete('1.0','end')
        lines=text.splitlines()
        text='\n'.join(lines[:20000])
        if len(lines)>20000:text+='\n\n[Vista limitada a 20 000 líneas. El ZIP contiene el archivo completo.]'
        self.code.insert('1.0',text)
        self.gutter.configure(state='normal')
        self.gutter.delete('1.0','end')
        self.gutter.insert('1.0','\n'.join(str(i+1) for i in range(len(text.split('\n')))))
        self.gutter.configure(state='disabled')
        if syntax:
            pattern=r'//[^\n]*|"(?:\\.|[^"\\])*"|\b(?:public|private|protected|class|static|void|return|if|else|new|using|namespace|int|bool|boolean|string|String|package|import|try|catch|throw|final|const|struct|while|for|switch|case|null|true|false)\b'
            for i,match in enumerate(re.finditer(pattern,text)):
                if i>15000:break
                tag='comment' if match[0].startswith('//') else 'string' if match[0].startswith('"') else 'keyword'
                self.code.tag_add(tag,f'1.0+{match.start()}c',f'1.0+{match.end()}c')
        self.code.configure(state='disabled')

    def find_next(self):
        term=self.search.get()
        self.code.tag_remove('match','1.0','end')
        if not term:return
        match=self.code.search(term,self.match_cursor,stopindex='end',nocase=True)
        if not match:match=self.code.search(term,'1.0',stopindex='end',nocase=True)
        if match:
            end=f'{match}+{len(term)}c'
            self.code.tag_add('match',match,end)
            self.code.see(match)
            self.match_cursor=self.code.index(end)
            self.match_count.set('Coincidencia en línea '+match.split('.')[0])
        else:self.match_count.set('Sin coincidencias')

    def copy_code(self):
        if self.current_content:
            self.clipboard_clear()
            self.clipboard_append(self.current_content)
            self.status.set('Contenido del archivo copiado.')

    def export(self):
        if not self.active:return
        path=filedialog.asksaveasfilename(parent=self,title='Exportar resultados',defaultextension='.zip',initialfile=f'strata-{self.active[:8]}.zip',filetypes=[('ZIP','*.zip')])
        if path:
            try:
                engine.export_results(engine.JOBS[self.active],path)
                self.status.set('Exportado: '+path)
            except Exception as exc:messagebox.showerror('Error de exportación',str(exc),parent=self)

    def open_application(self):
        job=engine.JOBS[self.active]
        normal=job.get('normal') or {}
        if normal.get('target')=='external':
            path=filedialog.asksaveasfilename(parent=self,title='Paquete para VM Windows',initialfile=f'vm-{job["id"][:8]}.zip',defaultextension='.zip',filetypes=[('ZIP','*.zip')])
            if path:
                try:
                    engine.export_vm(job,path)
                    self.status.set('Paquete VM exportado: '+path)
                    messagebox.showinfo('Paquete preparado','Transfiere el ZIP a tu VM Windows. Dentro de la VM, desactiva la red y ejecuta Abrir-en-VM.ps1. La muestra todavía no se abrió.',parent=self)
                except Exception as exc:messagebox.showerror('Error',str(exc),parent=self)
            return
        dialog=tk.Toplevel(self)
        dialog.title('Confirmar apertura')
        dialog.configure(bg=PANEL)
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry('610x370')
        dialog.resizable(False,False)
        frame=ttk.Frame(dialog,style='Panel.TFrame',padding=25)
        frame.pack(fill='both',expand=True)
        pc=normal.get('target')=='pc'
        title='Abrir en este PC' if pc else 'Abrir en Windows Sandbox'
        self.label(frame,title,'Panel.TLabel',font=(FONT,19,'bold')).pack(anchor='w')
        description='La aplicación se ejecutará en tu equipo con los permisos de tu usuario y acceso a tus archivos y red.' if pc else 'Se abrirá una sesión desechable sin red ni portapapeles. Solo se comparte la carpeta de entrada dedicada, en lectura.'
        self.label(frame,description,'Panel.TLabel',foreground=MUTED,wraplength=550).pack(anchor='w',pady=15)
        self.label(frame,'SHA-256: '+job['metadata']['sha256'],'Panel.TLabel',font=(MONO,9),wraplength=550).pack(anchor='w',pady=8)
        confirmed=tk.BooleanVar()
        confirmation='Reconozco esta aplicación como conocida y confiable, y autorizo abrirla en este PC.' if pc else 'Confirmo una sesión desechable sin credenciales ni datos personales y autorizo ejecutar la muestra.'
        tk.Checkbutton(frame,text=confirmation,variable=confirmed,bg=PANEL,fg=FG,selectcolor=RAISED,activebackground=PANEL,activeforeground=FG,wraplength=500,justify='left',font=(FONT,10),anchor='w').pack(anchor='w',pady=20)
        row=ttk.Frame(frame,style='Panel.TFrame')
        row.pack(fill='x')
        ttk.Button(row,text='Cancelar',command=dialog.destroy).pack(side='right')
        def open_now():
            try:
                pid=engine.launch(job,confirmed.get())
                dialog.destroy()
                self.status.set(f'Apertura solicitada. PID {pid}.')
            except Exception as exc:messagebox.showerror('No se pudo abrir',str(exc),parent=dialog)
        button=ttk.Button(row,text='Abrir aplicación',style='Primary.TButton',command=open_now,state='disabled')
        button.pack(side='right',padx=12)
        confirmed.trace_add('write',lambda *_:button.configure(state='normal' if confirmed.get() else 'disabled'))

    def render_history(self):
        self.history.delete(*self.history.get_children())
        with engine.LOCK:
            jobs=sorted(engine.JOBS.values(),key=lambda j:j['created'],reverse=True)
        for job in jobs:
            mode='Seguro' if job['mode']=='safe' else 'Normal / '+job.get('target','vm').upper()
            self.history.insert('','end',iid=job['id'],values=(job['name'],mode,job.get('metadata',{}).get('format','Identificando'),STATES[job['status']]))

    def open_history(self):
        selection=self.history.selection()
        if selection:
            self.activate_job(engine.JOBS[selection[0]])
            self.show('result')

    def close(self):
        if self.ai.busy:
            if not messagebox.askyesno('Solicitud en curso','¿Cancelar la solicitud y cerrar? El proveedor puede haber procesado el mensaje enviado.',parent=self):return
            self.ai.cancel.set()
            if self.ai.session:
                self.ai.session.value['status']='cancelado'; self.ai.session.save()
        busy=any(j['status'] in ('queued','running') for j in engine.JOBS.values())
        if busy and not messagebox.askyesno('Análisis en curso','Hay análisis en curso. ¿Detener los motores y cerrar Strata?',parent=self):return
        if busy:engine.stop_tools()
        self.destroy()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--open',dest='initial')
    parser.add_argument('--self-test',action='store_true')
    parser.add_argument('--test-report')
    parser.add_argument('--ai-self-test',action='store_true')
    args=parser.parse_args()
    if args.ai_self_test:
        from ai_selftest import run
        run(args.test_report)
        return
    if args.self_test:
        from selftest import run
        run(args.test_report)
        return
    try:
        Strata(args.initial).mainloop()
    except Exception as exc:
        error_path=engine.ROOT/'startup-error.txt'
        import traceback
        error_path.write_text(traceback.format_exc(),encoding='utf-8')
        messagebox.showerror('Strata',f'No se pudo iniciar: {exc}\nConsulta {error_path}')


if __name__=='__main__':
    main()
