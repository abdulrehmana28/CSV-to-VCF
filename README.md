# Seerah Contacts — web interface

A local-only web app that turns a student CSV/Excel file into WhatsApp-ready
VCF contact files.

## Project setup

### Requirements

- **Python 3.8 or newer** (3.10+ recommended)
- A modern web browser (Chrome, Edge, Firefox, or Safari)
- No `pip` packages are needed
- No internet connection is needed after the project is downloaded

### 1. Get the project

Clone the repository:

```bash
git clone https://github.com/YOUR-USERNAME/YOUR-REPO.git
cd YOUR-REPO
```

Alternatively, download the repository as a ZIP from GitHub and extract it.

### 2. Check Python

**Windows**

```bat
py -3 --version
```

If `py` is not available, try:

```bat
python --version
```

**Linux / macOS**

```bash
python3 --version
```

You should see `Python 3.x.x`. If Python is missing, install it from
<https://www.python.org/downloads/>. On Windows, select **Add Python to PATH**
during installation.

### 3. Start the app

**Windows**

Double-click `start_web.bat`, or run it from Command Prompt:

```bat
start_web.bat
```

The script uses `py -3` first and falls back to `python`. If Python is missing,
it shows the download link and installation instructions.

**Linux / macOS**

```bash
./start_web.sh
```

If you get a permission error:

```bash
chmod +x start_web.sh
./start_web.sh
```

You can also start the server directly:

```bash
python3 webapp.py
```

### 4. Open the app

The browser opens automatically at <http://127.0.0.1:8000>. If it does not,
open that address manually. If port 8000 is busy, the app uses the next free
port and prints the address in the terminal.

Keep the terminal window open while using the app. Closing it stops the local
server.

### Setup troubleshooting

| Problem | Solution |
| --- | --- |
| `Python was not found` | Install Python 3 and enable **Add Python to PATH**. |
| `Permission denied: ./start_web.sh` | Run `chmod +x start_web.sh` once, then start again. |
| Browser did not open | Open the URL printed in the terminal manually. |
| Port already in use | Use the new port printed in the terminal, or run `python3 webapp.py --port 8010`. |
| App does not load | Make sure the terminal running the app is still open. |

## How to use

1. Drop the registration **.csv** or **.xlsx** file onto the page.
2. Enter the batch code, for example `SCRYK-8001`.
3. Choose the contact name style.
4. Click **Generate contact file**.
5. Download the `.vcf` and import it into the phone's local contacts app.

The contact names look like `[SCRYK-8001] Ahmed Ali`, so searching the batch
code in WhatsApp shows only that batch's contacts.

## Project structure

```text
make_vcf.py        CSV/Excel -> VCF conversion logic and optional CLI
webapp.py          Local web server and upload/download API
start_web.sh       Linux/macOS launcher
start_web.bat      Windows launcher
static/            HTML, CSS, and JavaScript interface
```

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
