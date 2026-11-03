"""Cloud regressions use temporary SQLite, mocked HTTP, and no hardware."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from urllib.error import HTTPError, URLError
from cloud_client import CloudClient, CloudError, NoRedirect, protect_token, save_config
from registry_store import Registry

ROW={'uid':'0001','name':'Example Operator','initials':'EO','active':1}

class CloudTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name);self.store=Registry(self.root/'test.sqlite3')
        self.client=CloudClient.__new__(CloudClient)
        self.client.url='https://registry.example';self.client.token='test.'+'x'*43

    def tearDown(self):
        self.store.close();self.temp.cleanup()

    def test_download_preserves_history_and_backup(self):
        self.store.save('0001','Local Person','LP',True)
        self.store.backup(self.root/'backup.sqlite3')
        self.store.import_cloud(self.client.url,{'version':2,'records':[ROW]})
        self.assertEqual(self.store.get('0001')['name'],ROW['name'])
        self.assertEqual(self.store.cloud_version(self.client.url),2)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM history').fetchone()[0],2)
        backup=Registry(self.root/'backup.sqlite3')
        try:self.assertEqual(backup.get('0001')['name'],'Local Person')
        finally:backup.close()

    def test_malformed_snapshot_is_not_applied(self):
        self.store.save('0001','Local Person','LP',True)
        for records in [[ROW,ROW],[{**ROW,'active':True}],[{**ROW,'uid':'0'}]]:
            with self.assertRaises(CloudError):self.store.import_cloud(self.client.url,{'version':2,'records':records})
        self.assertEqual(self.store.get('0001')['name'],'Local Person')
        self.assertIsNone(self.store.cloud_version(self.client.url))

    def test_transaction_failure_rolls_back_records_and_version(self):
        self.store.save('0001','Local Person','LP',True)
        self.store.db.execute("CREATE TRIGGER reject_cloud BEFORE INSERT ON history WHEN NEW.action='cloud_download' BEGIN SELECT RAISE(ABORT,'test failure'); END")
        with self.assertRaises(Exception):self.store.import_cloud(self.client.url,{'version':2,'records':[ROW]})
        self.assertEqual(self.store.get('0001')['name'],'Local Person')
        self.assertIsNone(self.store.cloud_version(self.client.url))

    def test_online_identity_requires_active_matching_record(self):
        response={'version':3,'checked_utc':'2026-11-03T00:00:00Z','record':ROW}
        with patch.object(self.client,'call',return_value=response):
            self.assertEqual(self.client.check('0001')['operator_registry_version'],3)
            with self.assertRaises(CloudError):self.client.check('0002')
        with patch.object(self.client,'call',return_value={**response,'record':{**ROW,'active':0}}):
            with self.assertRaises(CloudError):self.client.check('0001')

    def test_timeout_auth_conflict_never_retry(self):
        for exc in [URLError('offline'),HTTPError('url',401,'secret',{},None),HTTPError('url',409,'secret',{},None)]:
            opener=MagicMock();opener.open.side_effect=exc
            with patch('cloud_client.request.build_opener',return_value=opener):
                with self.assertRaises(CloudError) as raised:self.client.check('0001')
                self.assertNotIn(self.client.token,str(raised.exception));opener.open.assert_called_once()

    def test_redirect_rejected(self):
        with self.assertRaises(CloudError):NoRedirect().redirect_request(None,None,302,'',{},'https://other.example')

    def test_windows_credentials_round_trip_without_plaintext(self):
        token='test.'+'x'*43;config=self.root/'registry-cloud.local.json'
        save_config(config,self.client.url,token)
        self.assertNotIn(token,config.read_text())
        self.assertEqual(CloudClient(config).token,token)
        self.assertNotEqual(protect_token(token),token)

if __name__=='__main__':unittest.main()
