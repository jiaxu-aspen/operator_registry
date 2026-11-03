"""Registry-only cloud controls; network work never touches Tk or SQLite.

The main UI captures records before dispatch, prevents concurrent navigation,
and applies downloaded data only after a summary confirmation and local backup.
"""
from datetime import datetime
import threading
import tkinter as tk
from tkinter import ttk, messagebox
from cloud_client import CloudClient, save_config, validate_records


class CloudControls:
    def init_cloud(self, parent, base):
        """Add explicit configuration, upload, download and sync status controls."""
        self.cloud_config_path=base/'registry-cloud.local.json'
        self.cloud_status=tk.StringVar(value='Cloud configured' if self.cloud_config_path.exists() else 'Cloud not configured â€” local registry')
        area=ttk.LabelFrame(parent,text='Cloud registry',padding=8)
        area.pack(fill='x',pady=(8,0))
        self.cloud_buttons=[]
        for text,command in [('Cloud settings',self.configure_cloud),('Upload current registry',lambda:self.cloud_work('upload')),
                             ('Download latest',lambda:self.cloud_work('download'))]:
            button=ttk.Button(area,text=text,command=command);button.pack(side='left',padx=4)
            self.cloud_buttons.append(button)
        ttk.Label(parent,textvariable=self.cloud_status,wraplength=800).pack(anchor='w',pady=4)

    def configure_cloud(self):
        """Mask the app token and persist only DPAPI ciphertext for this user."""
        if self.busy:return
        dialog=tk.Toplevel(self.root);dialog.title('Cloud registry settings');dialog.transient(self.root)
        panel=ttk.Frame(dialog,padding=20);panel.pack(fill='both',expand=True)
        url=tk.StringVar();token=tk.StringVar()
        if self.cloud_config_path.exists():
            try:url.set(CloudClient(self.cloud_config_path).url)
            except ValueError:pass
        ttk.Label(panel,text='Worker HTTPS address').pack(anchor='w')
        ttk.Entry(panel,textvariable=url,width=65).pack(fill='x',pady=(0,12))
        ttk.Label(panel,text='Registry administrator token').pack(anchor='w')
        ttk.Entry(panel,textvariable=token,show='*',width=65).pack(fill='x',pady=(0,12))
        def save():
            try:save_config(self.cloud_config_path,url.get(),token.get())
            except Exception as exc:messagebox.showerror('Settings not saved',str(exc),parent=dialog);return
            token.set('');self.cloud_status.set('Cloud configured. Upload or download to check connection.');dialog.destroy()
        ttk.Button(panel,text='Save settings',command=save).pack(anchor='e')
        dialog.grab_set()

    def cloud_work(self, action):
        """Snapshot all UI-thread data before one bounded background operation."""
        if self.busy:return
        if self.dirty():
            messagebox.showinfo('Unsaved operator edits','Save or clear the operator form before cloud synchronization.',parent=self.root);return
        try:
            client=CloudClient(self.cloud_config_path)
            records=validate_records(self.store.rows())
            version=self.store.cloud_version(client.url)
        except Exception as exc:messagebox.showerror('Cloud unavailable',str(exc),parent=self.root);return
        if action=='upload' and not messagebox.askyesno('Publish registry',
                f'Publish {len(records)} operator records to {client.url}?',parent=self.root):return
        self.set_busy(True);self.cloud_status.set('Uploadingâ€¦' if action=='upload' else 'Downloadingâ€¦')
        def worker():
            try:
                if action=='upload':
                    base=version
                    if base is None:
                        remote=client.download()
                        if remote['version']!=0:
                            raise ValueError('This registry has not retrieved the cloud version. Back up local edits, then download latest first.')
                        base=0
                    result=client.upload(records,base)
                else:result=client.download()
                self.events.put(('cloud_'+action,(client.url,result)))
            except Exception as exc:self.events.put(('cloud_error',str(exc)))
        threading.Thread(target=worker,daemon=True).start()

    def cloud_result(self, kind, value):
        """Confirm replacements on Tk thread and back up before atomic import."""
        if kind=='cloud_error':
            self.cloud_status.set(value);messagebox.showerror('Cloud sync failed',value,parent=self.root);return
        endpoint,snapshot=value
        try:
            if kind=='cloud_upload':
                self.store.mark_synced(endpoint,snapshot['version'])
            else:
                old={r['uid']:r for r in validate_records(self.store.rows())}
                new={r['uid']:r for r in snapshot['records']}
                added=len(new.keys()-old.keys());removed=len(old.keys()-new.keys())
                changed=sum(old[k]!=new[k] for k in old.keys() & new.keys())
                if not messagebox.askyesno('Retrieve cloud registry',
                    f"Cloud version {snapshot['version']}: {added} added, {changed} changed, {removed} local-only removed.\n\n"
                    'Replace local records? Unpublished local edits will be replaced. A backup will be saved first.',parent=self.root):
                    self.cloud_status.set('Download reviewed; local records unchanged.');return
                backup=self.store.path.with_name('operators-before-cloud-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.sqlite3')
                self.store.backup(backup)
                self.store.import_cloud(endpoint,snapshot)
                self.load({'uid':'','name':'','initials':'','active':1},False);self.populate()
            self.cloud_status.set(f"Cloud version {snapshot['version']} Â· Last sync {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        except Exception as exc:
            self.cloud_status.set('Cloud result could not be applied. Local backup is retained.')
            messagebox.showerror('Sync not completed',str(exc),parent=self.root)
