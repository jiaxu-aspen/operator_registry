"""Smoke-test real Tk controls with fake cloud responses and no card reader."""
import tempfile
import tkinter as tk
from pathlib import Path
from unittest.mock import patch, Mock
import unittest
import operator_registry


class CloudUITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.base=Path(self.tmp.name)
        self.root=tk.Tk();self.root.withdraw()
        with patch.object(operator_registry,'BASE',self.base), patch.object(operator_registry.App,'discover'):
            self.app=operator_registry.App(self.root)
        self.root.update_idletasks()

    def tearDown(self):
        self.app.store.close();self.root.destroy();self.tmp.cleanup()

    def test_download_confirmation_backup_and_visible_controls(self):
        self.app.store.save('0001','Local Person','LP',True)
        snapshot={'version':1,'records':[{'uid':'0001','name':'Cloud Person','initials':'CP','active':1}]}
        with patch('cloud_ui.messagebox.askyesno',return_value=False):
            self.app.cloud_result('cloud_download',('https://registry.example',snapshot))
        self.assertEqual(self.app.store.get('0001')['name'],'Local Person')
        with patch('cloud_ui.messagebox.askyesno',return_value=True):
            self.app.cloud_result('cloud_download',('https://registry.example',snapshot))
        self.assertEqual(self.app.store.get('0001')['name'],'Cloud Person')
        self.assertEqual(len(list(self.base.glob('operators-before-cloud-*.sqlite3'))),1)
        self.assertIn('version 1',self.app.cloud_status.get())
        self.assertEqual([b.cget('text') for b in self.app.cloud_buttons],
                         ['Cloud settings','Upload current registry','Download latest'])

    def test_busy_locks_edits_and_cloud_navigation(self):
        self.app.set_busy(True)
        for widget in [self.app.name_entry,self.app.initials_entry,self.app.active_check,*self.app.cloud_buttons]:
            self.assertEqual(str(widget.cget('state')),'disabled')
        self.app.set_busy(False)
        self.assertEqual(str(self.app.name_entry.cget('state')),'normal')

    def test_local_save_marks_unpublished_changes(self):
        self.app.load({'uid':'0001','name':'Example','initials':'EX','active':1},False)
        self.app.save()
        self.assertIn('upload to publish',self.app.cloud_status.get())


if __name__=='__main__':unittest.main()
