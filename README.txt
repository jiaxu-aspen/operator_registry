OPERATOR REGISTRY - ENROLLMENT AND CLOUD SYNC
Application version: 1.1.0

See RELEASE_NOTES.txt for this version's changes. The app version is separate
from the cloud registry revision, which increases each time records are uploaded.

1. Double-click Open Operator Registry.cmd.
2. Hold one compatible card on the OMNIKEY reader and click Scan card.
3. Enter the operator's full name and tester initials. Leave Card active checked.
4. Click Save operator. Nothing is written until you click Save.
5. Click New card to enroll the next operator.

Scan a registered card or select its row to edit it. Uncheck Card active and
save to disable a lost/retired card. Names are not read from the card itself.
Card identifiers retain leading zeros and are displayed in hexadecimal.
Verify each credential returns the same ID after removing and presenting it
again before relying on it for operator identification. Randomized identifiers
are not suitable for this registry. This is identification, not authentication.

The registry is operators.sqlite3 beside the app, including a change history.
Use Back up registry to save a consistent copy. Local editing works offline;
cloud uploads, downloads, and configured station checks require internet.
Use this PC as the master enrollment station. To transfer the registry, close
both apps, back up each existing database, then copy the master backup to the
other station as operators.sqlite3. Do not merge independent copies by overwrite.
The database contains operator information; store backups in an approved location.

This is a standalone enrollment tool. Auto SW Load and Auto ATP read this
registry format. The integrated NexNav Workstation uses its own copy at
NexNav Workstation/Operator Registry/operators.sqlite3; changes made here
are not automatically synchronized to that copy. With cloud configuration,
the integrated engines check the online registry instead of their local copy.
See CLOUD_SETUP.txt for deployment, credentials, and daily use.
The launcher works with this PC's bundled Python, or Python 3 with Tkinter.
The reader uses Windows Smart Card (PC/SC); it does not write to the card.

SOURCE AND VALIDATION

Source repository: https://github.com/jiaxu-aspen/operator_registry
Requires Windows and Python 3 with Tkinter; no third-party Python packages
are required. The database is created locally on first launch. Operator
databases and backups are excluded from Git.
Run the hardware-free storage tests from this folder:
  python -m unittest -v test_registry
These tests use temporary databases and do not access the card reader.

CLOUD DAILY USE

1. Download latest before editing (back up unpublished local edits first).
2. Scan/edit a card and Save operator. This saves locally only.
3. Upload current registry to publish your changes to online test stations.
4. A successful upload displays the new cloud version.

Download latest shows a change summary and backs up local SQLite before
replacement. Local history remains available. Uploads refuse stale versions
and removal of published cards; disable lost/retired cards instead.
After an upload timeout, retrieve latest and review it before retrying.
Cloud settings stores credentials encrypted for the current Windows user.
