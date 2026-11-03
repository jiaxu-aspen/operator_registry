OPERATOR REGISTRY - LOCAL ENROLLMENT

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
Use Back up registry to save a consistent copy. No internet is required.
Use this PC as the master enrollment station. To transfer the registry, close
both apps, back up each existing database, then copy the master backup to the
other station as operators.sqlite3. Do not merge independent copies by overwrite.
The database contains operator information; store backups in an approved location.

This is a standalone enrollment tool. Auto SW Load and Auto ATP read this
registry format. The integrated NexNav Workstation uses its own copy at
NexNav Workstation/Operator Registry/operators.sqlite3; changes made here
are not automatically synchronized to that copy. Follow the backup and
transfer procedure above when provisioning a station.
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
