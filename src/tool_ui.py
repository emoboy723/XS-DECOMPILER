"""Native setup and import flow for optional desktop decompilers."""
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
import webbrowser
import engine
import external_tools


class ToolSettings:
    def __init__(self,app,parent):
        self.app=app
        self.events=queue.Queue()
        self.import_busy=False
        self.status=tk.StringVar()
        try:values=external_tools.load(engine.ROOT,engine.DATA)
        except ValueError as exc:
            values=dict(external_tools.DEFAULTS)
            self.status.set(str(exc))
        self.variables={key:tk.BooleanVar(value=value) if isinstance(value,bool) else tk.StringVar(value=value) for key,value in values.items()}
        notebook=ttk.Notebook(parent); notebook.pack(fill='both',expand=True)
        dot=ttk.Frame(notebook,padding=18); ninja=ttk.Frame(notebook,padding=18)
        notebook.add(dot,text='dotPeek · .NET'); notebook.add(ninja,text='Binary Ninja · nativo')
        self.heading(dot,'dotPeek','Abre ensamblados .NET, exporta el proyecto C# e importa la carpeta en Strata.')
        self.field(dot,'dotpeek','Ejecutable dotPeek')
        ttk.Label(dot,text='La exportación se realiza en dotPeek con Export to Project.\nILSpy sigue disponible para decompilar directamente dentro de Strata.',style='Muted.TLabel',wraplength=720).pack(anchor='w',pady=18)
        ttk.Button(dot,text='Obtener dotPeek · sitio oficial',command=lambda:webbrowser.open('https://www.jetbrains.com/decompiler/')).pack(anchor='w')
        self.heading(ninja,'Binary Ninja','Análisis avanzado en su interfaz o decompilación automática mediante su API licenciada.')
        self.field(ninja,'binaryninja_gui','Ejecutable Binary Ninja')
        ttk.Button(ninja,text='Obtener Binary Ninja · sitio oficial',command=lambda:webbrowser.open('https://binary.ninja/')).pack(anchor='w',pady=(10,16))
        ttk.Button(ninja,text='Configurar decompilación automática…',command=self.open_api).pack(anchor='w')
        ttk.Label(ninja,text='Opcional: requiere Python dedicado, API y licencia Commercial, Ultimate o headless.\nPara Free y Non-commercial usa Abrir en Binary Ninja e importa el código exportado.',style='Muted.TLabel',wraplength=720).pack(anchor='w',pady=16)
        row=ttk.Frame(parent); row.pack(fill='x',pady=(16,8))
        ttk.Button(row,text='Buscar instalaciones',command=self.discover).pack(side='left')
        ttk.Button(row,text='Guardar rutas',style='Primary.TButton',command=self.save).pack(side='right')
        ttk.Label(parent,textvariable=self.status,style='Muted.TLabel',wraplength=780).pack(anchor='w')
        self.describe()
        app.after(150,self.poll)

    def heading(self,parent,title,description):
        ttk.Label(parent,text=title,style='Section.TLabel').pack(anchor='w')
        ttk.Label(parent,text=description,style='Muted.TLabel',wraplength=740).pack(anchor='w',pady=(8,18))

    def field(self,parent,key,label,directory=False):
        ttk.Label(parent,text=label,style='Muted.TLabel').pack(anchor='w',pady=(9,5))
        row=ttk.Frame(parent); row.pack(fill='x')
        ttk.Entry(row,textvariable=self.variables[key]).pack(side='left',fill='x',expand=True)
        def choose():
            value=filedialog.askdirectory(parent=self.app,title=label) if directory else filedialog.askopenfilename(parent=self.app,title=label,filetypes=[('Ejecutable','*.exe')])
            if value:self.variables[key].set(value)
        ttk.Button(row,text='Examinar',command=choose).pack(side='right',padx=(10,0))

    def open_api(self):
        dialog=tk.Toplevel(self.app); dialog.title('Binary Ninja · API automática')
        dialog.geometry('690x470'); dialog.minsize(650,440); dialog.transient(self.app); dialog.grab_set()
        self.api_frame=ttk.Frame(dialog,padding=22); self.api_frame.pack(fill='both',expand=True)
        self.heading(self.api_frame,'Decompilación con la API','Elige un Python dedicado compatible con tu instalación de Binary Ninja y su carpeta API.')
        snapshot={key:self.variables[key].get() for key in ('binaryninja_python','binaryninja_api','binaryninja_headless')}
        self.field(self.api_frame,'binaryninja_python','Ejecutable Python dedicado')
        self.field(self.api_frame,'binaryninja_api','Carpeta API (contiene binaryninja/__init__.py)',directory=True)
        ttk.Checkbutton(self.api_frame,text='Habilitar API con mi licencia Commercial, Ultimate o headless',variable=self.variables['binaryninja_headless']).pack(anchor='w',pady=16)
        ttk.Label(self.api_frame,text='La licencia permanece gestionada por Binary Ninja y se comprueba al analizar.\nStrata no guarda ni copia sus credenciales. Free y Non-commercial utilizan la interfaz.',style='Muted.TLabel',wraplength=620).pack(anchor='w',pady=8)
        row=ttk.Frame(self.api_frame); row.pack(side='bottom',fill='x',pady=(12,0))
        def cancel():
            for key,value in snapshot.items():self.variables[key].set(value)
            dialog.destroy()
        def apply():
            if self.save():dialog.destroy()
        ttk.Button(row,text='Guardar API',style='Primary.TButton',command=apply).pack(side='right')
        ttk.Button(row,text='Cancelar',command=cancel).pack(side='right',padx=8)
        dialog.protocol('WM_DELETE_WINDOW',cancel)

    def describe(self):
        available=engine.engines()
        dot='dotPeek: configurado' if available['dotpeek'] else 'dotPeek: pendiente de instalar/configurar'
        ninja='Binary Ninja API: configurada; licencia sin verificar' if available['binaryninja'] else 'Binary Ninja: interfaz configurada' if available['binaryninja_gui'] else 'Binary Ninja: pendiente de instalar/configurar'
        self.status.set(dot+'\n'+ninja)

    def discover(self):
        values=external_tools.discover(engine.ROOT)
        found=0
        for key,value in values.items():
            if value and key!='binaryninja_headless':
                self.variables[key].set(value); found+=1
        self.status.set('Rutas encontradas. Pulsa Guardar rutas.' if found else 'No se encontraron instalaciones en las ubicaciones habituales. Instala la herramienta y selecciona su ejecutable con Examinar.')

    def save(self):
        try:
            external_tools.save(engine.ROOT,engine.DATA,{key:value.get() for key,value in self.variables.items()})
            self.describe()
            self.app.refresh_engine_choices()
            return True
        except Exception as exc:
            messagebox.showerror('No se guardaron las rutas',str(exc),parent=self.app)
            return False

    def open_advanced(self):
        job=engine.JOBS.get(self.app.active)
        if not job:return
        fmt=job.get('metadata',{}).get('format','')
        tool='dotpeek' if fmt=='Windows .NET' else 'binaryninja'
        try:
            sample=engine.DATA/job['id']/'input'/job['name']
            external_tools.launch(engine.ROOT,external_tools.load(engine.ROOT,engine.DATA),tool,sample,fmt)
            self.app.status.set('Archivo abierto como datos en '+('dotPeek' if tool=='dotpeek' else 'Binary Ninja')+'. Exporta el código y usa Importar código exportado.')
        except Exception as exc:
            messagebox.showinfo('Configura la herramienta externa',str(exc),parent=self.app)
            self.app.show('engines')

    def import_code(self):
        if self.import_busy:return
        job=engine.JOBS.get(self.app.active)
        if not job:return
        tool='dotpeek' if job.get('metadata',{}).get('format')=='Windows .NET' else 'binaryninja'
        directory=filedialog.askdirectory(parent=self.app,title='Seleccionar carpeta de código exportado por '+tool)
        if not directory:return
        self.import_busy=True
        self.app.status.set('Importando copia del código exportado…')
        def run():
            try:
                target,count=external_tools.import_sources(directory,engine.DATA/job['id']/'result',tool)
                engine.log(job,f'{tool}: {count} archivos importados; correspondencia con la muestra declarada por el usuario, no verificada.')
                job.setdefault('imports',[]).append({'tool':tool,'path':target.relative_to(engine.DATA/job['id']/'result').as_posix(),'files':count})
                # Imported text is kept distinct from the motor's decompilation status.
                engine.save(job)
                if job.get('requested_engine')=='combined':engine.write_combined_summary(job)
                self.events.put(('imported',job['id'],count))
            except Exception as exc:self.events.put(('error',str(exc)))
        threading.Thread(target=run,daemon=True).start()

    def poll(self):
        try:
            while True:
                event=self.events.get_nowait()
                self.import_busy=False
                if event[0]=='error':messagebox.showerror('No se importó el código',event[1],parent=self.app)
                else:
                    self.app.status.set(f'{event[2]} archivos importados como copia.')
                    if self.app.active==event[1]:
                        self.app.last_files=None; self.app.refresh_result()
        except queue.Empty:pass
        self.app.after(150,self.poll)
