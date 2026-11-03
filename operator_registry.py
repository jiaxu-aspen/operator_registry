"""Standalone card enrollment UI. No ATP instruments or test files are accessed."""
from pathlib import Path
from datetime import datetime
import ctypes
import queue
import sqlite3
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from card_reader import Reader
from registry_store import Registry

BASE = Path(__file__).resolve().parent

class App:
    def __init__(self, root):
        self.root = root
        self.store = Registry(BASE / 'operators.sqlite3')
        self.events = queue.Queue()
        self.busy = False
        self.editing = False
        self.original = None
        self.root.title('ATP Operator Registry')
        self.root.configure(background='white')
        self.root.minsize(820, 610)
        self.reader = tk.StringVar()
        self.uid = tk.StringVar()
        self.name = tk.StringVar()
        self.initials = tk.StringVar()
        self.active = tk.BooleanVar(value=True)
        self.status = tk.StringVar(value='Looking for an OMNIKEY reader…')
        style = ttk.Style(root)
        style.theme_use('clam')
        style.configure('.', font=('Segoe UI', 11), background='white')
        style.configure('Treeview', rowheight=30, background='white', fieldbackground='white')
        style.configure('Title.TLabel', font=('Segoe UI', 22, 'bold'), foreground='#245a81')
        style.configure('TButton', padding=(12, 7))
        body = ttk.Frame(root, padding=24)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text='Operator Registry', style='Title.TLabel').pack(anchor='w')
        ttk.Label(body, text='Scan a card • Enter the operator • Save locally').pack(anchor='w', pady=(4,16))
        reader_row = ttk.Frame(body); reader_row.pack(fill='x')
        self.readers = ttk.Combobox(reader_row, textvariable=self.reader, state='readonly', width=50)
        self.readers.pack(side='left', fill='x', expand=True)
        self.refresh_button = ttk.Button(reader_row, text='Refresh reader', command=self.discover)
        self.refresh_button.pack(side='left', padx=(10,0))
        form = ttk.LabelFrame(body, text='Card and operator', padding=16)
        form.pack(fill='x', pady=16)
        form.columnconfigure(1, weight=1)
        ttk.Label(form, text='Card ID').grid(row=0,column=0,sticky='w',padx=(0,16),pady=5)
        ttk.Entry(form,textvariable=self.uid,state='readonly',width=35).grid(row=0,column=1,sticky='ew',pady=5)
        self.scan_button=ttk.Button(form,text='Scan card',command=self.scan)
        self.scan_button.grid(row=0,column=2,padx=(12,0))
        ttk.Label(form,text='Operator name').grid(row=1,column=0,sticky='w',pady=5)
        self.name_entry=ttk.Entry(form,textvariable=self.name)
        self.name_entry.grid(row=1,column=1,columnspan=2,sticky='ew',pady=5)
        ttk.Label(form,text='Tester initials').grid(row=2,column=0,sticky='w',pady=5)
        ttk.Entry(form,textvariable=self.initials,width=16).grid(row=2,column=1,sticky='w',pady=5)
        ttk.Checkbutton(form,text='Card active',variable=self.active).grid(row=2,column=2,sticky='w')
        buttons=ttk.Frame(form);buttons.grid(row=3,column=0,columnspan=3,sticky='e',pady=(12,0))
        self.clear_button=ttk.Button(buttons,text='New card',command=self.new_card)
        self.clear_button.pack(side='left',padx=8)
        self.save_button=ttk.Button(buttons,text='Save operator',command=self.save)
        self.save_button.pack(side='left')
        ttk.Label(body,textvariable=self.status,wraplength=760,foreground='#245a81').pack(anchor='w',pady=(0,12))
        area=ttk.Frame(body);area.pack(fill='both',expand=True)
        self.table=ttk.Treeview(area,columns=('name','initials','active','uid'),show='headings',height=7,selectmode='browse')
        for key,title,width in [('name','Operator',230),('initials','Initials',80),('active','Status',90),('uid','Card ID',220)]:
            self.table.heading(key,text=title);self.table.column(key,width=width,minwidth=65)
        self.table.pack(side='left',fill='both',expand=True)
        scrollbar=ttk.Scrollbar(area,orient='vertical',command=self.table.yview)
        scrollbar.pack(side='right',fill='y');self.table.configure(yscrollcommand=scrollbar.set)
        self.table.bind('<<TreeviewSelect>>',self.select)
        bottom=ttk.Frame(body);bottom.pack(fill='x',pady=(12,0))
        ttk.Button(bottom,text='Back up registry',command=self.backup).pack(side='right')
        ttk.Label(bottom,text='Select a row to edit or disable a card.').pack(side='left')
        self.populate()
        root.update_idletasks()
        width,height=900,720
        root.geometry(f'{width}x{height}+{max(0,(root.winfo_screenwidth()-width)//2)}+{max(0,(root.winfo_screenheight()-height)//2)}')
        root.protocol('WM_DELETE_WINDOW',self.close)
        root.after(100,self.poll)
        self.discover()

    def dirty(self):
        """Prevent a new scan or selection from silently losing unsaved identity edits."""
        if self.original:
            return (self.name.get(),self.initials.get(),self.active.get()) != (self.original['name'],self.original['initials'],bool(self.original['active']))
        return bool(self.name.get() or self.initials.get())

    def discard(self):
        return not self.dirty() or messagebox.askyesno('Unsaved changes','Discard the unsaved operator edits?',parent=self.root)

    def set_busy(self,value):
        """Lock form navigation during a scan so its result cannot replace another edit."""
        self.busy=value
        for button in (self.scan_button,self.refresh_button,self.save_button,self.clear_button):
            button.configure(state='disabled' if value else 'normal')

    def work(self,kind):
        """Run PC/SC calls off the Tk thread; only the main thread updates widgets."""
        selected=self.reader.get()
        self.set_busy(True)
        self.status.set('Reading card…' if kind=='scan' else 'Looking for an OMNIKEY reader…')
        def worker():
            device=None
            try:
                device=Reader()
                result=device.readers() if kind=='readers' else device.uid(selected)
                self.events.put((kind,result))
            except Exception as exc:
                self.events.put(('error',str(exc)))
            finally:
                if device:device.close()
        threading.Thread(target=worker,daemon=True).start()

    def discover(self):
        if not self.busy:self.work('readers')

    def scan(self):
        if self.busy:return
        if not self.reader.get():
            messagebox.showinfo('Reader required','Connect the OMNIKEY and click Refresh reader.',parent=self.root);return
        if self.discard():self.work('scan')

    def poll(self):
        """A scan never writes a registry record; saving is always an explicit action."""
        try:
            while True:
                kind,value=self.events.get_nowait();self.set_busy(False)
                if kind=='error':self.status.set(value)
                elif kind=='readers':
                    self.readers['values']=value
                    if self.reader.get() not in value:self.reader.set(value[0] if value else '')
                    self.status.set('Reader ready. Hold one card on it and click Scan card.' if value else 'No OMNIKEY found. Connect the reader and refresh.')
                else:
                    record=self.store.get(value)
                    self.load(record or {'uid':value,'name':'','initials':'','active':1},bool(record))
                    self.status.set('Registered card loaded. You may edit its details.' if record else 'New card scanned. Enter the name and initials, then save.')
                    self.name_entry.focus_set()
        except queue.Empty:pass
        self.root.after(100,self.poll)

    def load(self,record,existing):
        self.editing=existing;self.original=dict(record) if existing else None
        self.uid.set(record['uid']);self.name.set(record['name']);self.initials.set(record['initials']);self.active.set(bool(record['active']))
        self.save_button.configure(text='Save changes' if existing else 'Save operator')

    def new_card(self):
        if not self.busy and self.discard():
            self.load({'uid':'','name':'','initials':'','active':1},False)
            self.table.selection_remove(self.table.selection())
            self.status.set('Hold the next card on the reader, then click Scan card.')

    def populate(self):
        self.table.delete(*self.table.get_children())
        for r in self.store.rows():
            self.table.insert('', 'end',iid=r['uid'],values=(r['name'],r['initials'],'Active' if r['active'] else 'Disabled',r['uid']))

    def select(self,event=None):
        if self.busy or not self.table.selection():return
        uid=self.table.selection()[0]
        if uid==self.uid.get():return
        if self.discard():
            record=self.store.get(uid)
            if record:self.load(record,True);self.status.set('Editing selected card. Click Save changes when finished.')

    def save(self):
        """Confirm reassignment of an existing identity, while retaining its audit history."""
        if self.busy:return
        if self.original and (self.name.get().strip(),self.initials.get().strip().upper()) != (self.original['name'],self.original['initials']):
            if not messagebox.askyesno('Change card assignment','Update the operator assigned to this card? The previous details remain in the change history.',parent=self.root):return
        try:
            record=self.store.save(self.uid.get(),self.name.get(),self.initials.get(),self.active.get(),self.editing)
            self.load(record,True);self.populate()
            self.status.set(f"Saved {record['name']} ({record['initials']}) — {'active' if record['active'] else 'disabled'}.")
        except (ValueError,sqlite3.Error) as exc:
            messagebox.showerror('Not saved',str(exc),parent=self.root)

    def backup(self):
        filename=filedialog.asksaveasfilename(parent=self.root,title='Back up operator registry',defaultextension='.sqlite3',initialfile='operators-backup-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.sqlite3',filetypes=[('SQLite registry','*.sqlite3')])
        if filename:
            try:self.store.backup(filename);self.status.set('Registry backup saved, including change history.')
            except (OSError,ValueError,sqlite3.Error) as exc:messagebox.showerror('Backup failed',str(exc),parent=self.root)

    def close(self):
        if self.discard():self.store.close();self.root.destroy()

def main():
    """Enable DPI awareness before creating Tk so text is sharp at startup."""
    try:ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError,OSError):pass
    root=tk.Tk()
    try:App(root)
    except Exception as exc:
        messagebox.showerror('Registry could not open',str(exc),parent=root);root.destroy();return
    root.mainloop()

if __name__=='__main__':main()
