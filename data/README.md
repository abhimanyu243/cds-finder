Put your metadata extracts here:

- `CDS_FIELD_ORIGIN.csv` (required)
- `IXTRCTNENBLDVW.csv` (required)
- `DD03N.csv` (recommended: STRUCOBJN, FIELDNAME, KEYFLAG, the key fields of each view)
- `DDDDLSRCT.csv` (optional: description of each view)
- `DD08B.csv` (optional: associations each view defines, shown in the Details tab)
- `DataProductCatalogue.csv` (optional: data products that use each view)

File names only need to contain those words. Restart the app after replacing files.

`cds_finder.db` is created here the first time the app starts. It holds the table mapping that users maintain on the Table mapping page, with its history. Back it up.

Everything in this folder except this file is excluded from version control, so client metadata does not end up there by accident.
