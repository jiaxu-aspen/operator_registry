"""Regression checks use temporary databases; no enrollment data is altered."""
import tempfile
import unittest
from pathlib import Path
from registry_store import Registry

class RegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'registry.sqlite3';self.r=Registry(self.path)
    def tearDown(self):
        self.r.close();self.temp.cleanup()
    def test_duplicate_and_audit(self):
        self.r.save('001122','Sample Operator','so',True)
        with self.assertRaises(ValueError):self.r.save('001122','Different Person','DP',True)
        self.assertEqual(self.r.get('001122')['name'],'Sample Operator')
        self.r.save('001122','Sample Operator','SO',False,existing=True)
        self.assertEqual(self.r.get('001122')['active'],0)
        self.assertEqual(self.r.db.execute('SELECT count(*) FROM history').fetchone()[0],2)
    def test_validation_and_backup(self):
        for uid,name,initials in [('', 'Name','N'),('A','Name','N'),('00','','N'),('00','Name','1')]:
            with self.assertRaises(ValueError):self.r.save(uid,name,initials,True)
        self.r.save('0001','Test Person','TP',True)
        target=Path(self.temp.name)/'backup.sqlite3';self.r.backup(target)
        other=Registry(target)
        try:self.assertEqual(other.get('0001'),self.r.get('0001'))
        finally:other.close()
        with self.assertRaises(ValueError):self.r.backup(self.path)
    def test_persistence(self):
        self.r.save('0102','Test Person','TP',True)
        other=Registry(self.path)
        try:self.assertEqual(other.get('0102')['initials'],'TP')
        finally:other.close()

if __name__=='__main__':unittest.main()
