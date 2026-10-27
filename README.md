# Seerah Contacts — web interface

A local-only web app that turns a student CSV/Excel file into WhatsApp-ready
VCF contact files.

## Start

### Windows

Double-click `start_web.bat`, or run it from Command Prompt:

```bat
start_web.bat
```

Python 3 must be installed and available on your PATH. If it is missing, the
script shows the download link and installation instructions.

### Linux / macOS

```bash
./start_web.sh
```

Or, if the script is not executable:

```bash
python3 webapp.py
```

Your browser opens at <http://127.0.0.1:8000>. If port 8000 is busy, the app
uses the next free port and prints the address in the terminal.

## How to use

1. Drop the registration **.csv** or **.xlsx** file onto the page.
2. Enter the batch code, for example `SCRYK-8001`.
3. Choose the contact name style.
4. Click **Generate contact file**.
5. Download the `.vcf` and import it into the phone's local contacts app.

The contact names look like `[SCRYK-8001] Ahmed Ali`, so searching the batch
code in WhatsApp shows only that batch's contacts.

## Where files are saved

- `vcf_output/<CODE>.vcf` — generated contact file
- `vcf_output/vcf_skipped_rows.csv` — rows skipped and why

## Privacy

- The server listens on `127.0.0.1` only.
- Files are read and written on this computer.
- Nothing is uploaded, synced, or sent to any cloud service.
- No third-party Python packages are required; CSV and XLSX are read with the
  standard library.

## Command line (optional)

The original CLI still works:

```bash
python3 make_vcf.py --input students.csv --code SCRYK-8001
```

On Windows:

```bat
py -3 make_vcf.py --input students.csv --code SCRYK-8001
```

## Do not commit student data

The `.gitignore` excludes student exports (`*.csv`, `*.xlsx`, `*.xls`,
`*.xlsm`), generated contact files (`*.vcf`), reports, and the `vcf_output/`
folder. Never force-add these files to Git. Use `git push` rather than
drag-and-drop uploading a folder, because `.gitignore` only protects Git
commands.
