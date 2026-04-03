# GradeAgent CLI

GradeAgent is now meant to be used from a real terminal.

You start it in PowerShell, Terminal, or iTerm.
Then it shows a simple command prompt.
From there, you start grading with:

```bash
start grading --instructions "YOUR GRADING RULES HERE"
```

The browser opens and GradeAgent uses the page that is already open there when you press Enter.
It does not intentionally jump to an exam list page first.

The grading browser now keeps its own persistent login profile.
That means:

- if you log in once in the GradeAgent browser, it should stay logged in next time,
- your normal everyday Chrome window stays separate,
- GradeAgent reuses its own saved login cookies and site data between runs.
- GradeAgent deletes per-run scratch files so disk usage does not keep growing forever.

If you want to bootstrap that GradeAgent login profile from your normal Chrome profile the first time, turn this on in `.env`:

```env
BROWSER_USE_SYSTEM_CHROME=true
BROWSER_CHROME_PROFILE_DIRECTORY=Default
```

Use `Default` for your main Chrome profile, or something like `Profile 1` if you use a second Chrome profile.
GradeAgent copies that Chrome profile once into its own persistent login profile, then keeps reusing the GradeAgent copy on later runs.

## What The Program Does

This program:

1. opens a browser,
2. waits for you to confirm the correct exam page is already open,
3. reads student answers from the website,
4. compares them to the model answer and your grading instructions,
5. types points into the correct point fields.

## The Website Workflow It Follows

The program is built around this exact grading flow:

- students are listed as rows,
- exercises are listed as boxes to the right,
- the same exercise stays in one vertical column for all students,
- the agent grades one whole exercise column first,
- then it moves to the next exercise column.

### Important page rules

- dark blue exercise box
  - already graded
  - skip it
- `Oppilaan vastaus`
  - this is the student's answer
- `Mallivastaus`
  - this is the model answer
- `Pistemäärä`
  - type the total points here when there is one total score
- `Pisteytys`
  - use this when there are many sub-answers and many point fields
- green rounded arrow buttons
  - move down to the next student in the same exercise
- `Poistu oppilaan vastauksista`
  - return to the main exam screen after finishing that exercise column
- purple rounded icon near an answer field
  - open the correct answer for that sub-answer if needed
- green overlays
  - usually already-correct auto-filled answers
  - do not overwrite them
- faded gray number inside a point box
  - maximum points for that sub-answer
  - do not exceed it

## Local Models Used

This project now uses:

- `qwen3:4b`
  - fast local grading for short and simple answers
- `qwen3:8b`
  - stronger local grading for longer or harder answers
- `qwen3-vl:4b`
  - local browser model for screenshots, OCR, and page navigation

Why:

- `qwen3:4b` is small and fast enough for a MacBook Air class machine,
- `qwen3:8b` is still realistic on Apple Silicon while giving better grading quality,
- `qwen3-vl:4b` is small enough to run locally and is built for GUI, OCR, and visual agent tasks.
- these defaults avoid API rate limits and ongoing API costs.

## Super Dumbed Down Setup Guide

### Windows PowerShell

1. Open PowerShell in this project folder.
2. Run:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .\apps\api[dev]
python -m playwright install chromium
Copy-Item .env.example .env
winget install Ollama.Ollama
```

3. Open `.env`
4. Make sure these lines exist:

```env
MODEL_ROUTER_PROVIDER=ollama
BROWSER_AGENT_PROVIDER=ollama
OLLAMA_HOST=http://127.0.0.1:11434
```

5. Start Ollama in a separate terminal:

```powershell
ollama serve
```

6. Pull the local models once:

```powershell
ollama pull qwen3:4b
ollama pull qwen3:8b
ollama pull qwen3-vl:4b
```

7. Start the CLI:

```powershell
gradeagent
```

7. Optional: if you want GradeAgent to import login state from your normal Chrome profile the first time, also add:

```env
BROWSER_USE_SYSTEM_CHROME=true
BROWSER_CHROME_PROFILE_DIRECTORY=Default
```

If you use a different Chrome profile, replace `Default` with `Profile 1`, `Profile 2`, and so on.
After that, GradeAgent keeps using its own saved login profile for later runs.

If the `gradeagent` command is not found, use:

```powershell
npm run cli
```

### Mac Terminal

1. Open Terminal in this project folder.
2. Run:

```bash
brew install ollama
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ./apps/api[dev]
python -m playwright install chromium
cp .env.example .env
```

3. Open `.env`
4. Make sure these lines exist:

```env
MODEL_ROUTER_PROVIDER=ollama
BROWSER_AGENT_PROVIDER=ollama
OLLAMA_HOST=http://127.0.0.1:11434
```

5. Start Ollama in a separate terminal:

```bash
ollama serve
```

6. Pull the local models once:

```bash
ollama pull qwen3:4b
ollama pull qwen3:8b
ollama pull qwen3-vl:4b
```

7. Start the CLI:

```bash
gradeagent
```

6. Optional: to import login state from your normal Chrome profile the first time, add this to `.env`:

```env
BROWSER_USE_SYSTEM_CHROME=true
BROWSER_CHROME_PROFILE_DIRECTORY=Default
```

## How To Use It

### Step 1

Start the program:

```bash
gradeagent
```

You will see a welcome screen in the terminal.

### Step 2

Start grading by typing:

```bash
start grading --instructions "Give full points for exact answers. Give partial points for answers that are close in meaning but have grammar mistakes."
```

### Step 3

A browser window opens.

GradeAgent assumes the correct exam page is already open in that managed browser.

If the browser restores the wrong page:

1. manually go to the correct exam page,
2. stop there,
3. come back to the terminal.

If this is your first run, do the login normally in the GradeAgent browser.
On later runs, the same GradeAgent browser profile should still have your login.

### Step 4

Come back to the terminal.

Press `Enter`.

The agent will begin grading from the current exam page.

## What The CLI Looks Like

When you start it, you get a terminal prompt like this:

```text
gradeagent>
```

Useful commands:

- `start grading --instructions "..."`  
  start a grading run
- `status`  
  show current models and the last grading result
- `help`  
  show the welcome/help screen again
- `quit`  
  close the program

## What Happens During Grading

When grading starts, the CLI shows simple steps:

1. launching browser
2. waiting for you to open the exam page
3. starting grading from the current page
4. grading finished
5. done

After that, it prints useful stats such as:

- how many answers were processed,
- how many dark blue boxes were skipped,
- how many exercise columns were completed,
- how many point fields were filled,
- current exercise name if available,
- current student name if available,
- screenshot file path,
- final summary from the agent.

The CLI also shows which persistent login profile it is using.
If old browser junk was cleaned up at startup or after a run, the CLI also prints how much space was freed.

## Example Instructions

You write the grading rules yourself.

Examples:

```bash
start grading --instructions "Use the model answer. Give full points only for correct Swedish. Give partial points for correct meaning with small grammar mistakes."
```

```bash
start grading --instructions "Use conservative scoring. If the answer is partly correct, give lower partial points. Never give more than the maximum shown in the point box."
```

```bash
start grading --instructions "For vocabulary tasks, score by meaning first and spelling second. Small spelling mistakes can still get partial points."
```

## Dry Run Mode

If you want to test safely first:

```bash
start grading --instructions "YOUR RULES" --dry-run
```

In dry run mode, the agent inspects the page and decides what it would do, but it should not type scores.

## Important Files

- [cli.py](C:/Users/emili/GradeAgent/apps/api/app/cli.py)
  - terminal program
- [browser_navigation.py](C:/Users/emili/GradeAgent/apps/api/app/services/browser_navigation.py)
  - browser automation
- [config.py](C:/Users/emili/GradeAgent/apps/api/app/config.py)
  - model and browser settings
- [.env](C:/Users/emili/GradeAgent/.env)
  - your local configuration

## Settings You Probably Care About

In `.env`:

```env
MODEL_ROUTER_PROVIDER=ollama
MODEL_ROUTER_SIMPLE_MODEL=qwen3:4b
MODEL_ROUTER_STANDARD_MODEL=qwen3:8b
MODEL_ROUTER_COMPLEX_MODEL=qwen3:8b

BROWSER_AGENT_PROVIDER=ollama
BROWSER_AGENT_MODEL=qwen3-vl:4b
OLLAMA_HOST=http://127.0.0.1:11434
OLLAMA_TIMEOUT_SECONDS=120

BROWSER_HEADLESS=false
BROWSER_USE_SYSTEM_CHROME=true
BROWSER_ENABLE_DEFAULT_EXTENSIONS=false
BROWSER_DIRECT_PERSISTENT_PROFILE=true
BROWSER_CHROME_PROFILE_DIRECTORY=Default
BROWSER_PERSISTENT_PROFILE_DIR=artifacts/browser/browser-use-user-data-dir-gradeagent
BROWSER_CLEANUP_STALE_AFTER_SECONDS=3600
BROWSER_MAX_SAVED_SCREENSHOTS=3
```

Important:

- `BROWSER_HEADLESS=false`
  - this keeps the browser visible
  - that is what you want for this terminal workflow
- `MODEL_ROUTER_PROVIDER=ollama`
  - text grading uses local models through Ollama
- `BROWSER_AGENT_PROVIDER=ollama`
  - browser navigation also uses local models through Ollama
- `MODEL_ROUTER_SIMPLE_MODEL=qwen3:4b`
  - fast default for short answers on a MacBook Air class machine
- `MODEL_ROUTER_STANDARD_MODEL=qwen3:8b`
  - stronger default for harder grading
- `BROWSER_AGENT_MODEL=qwen3-vl:4b`
  - local vision model for screenshots, OCR, and interface reading
- `OLLAMA_HOST=http://127.0.0.1:11434`
  - this is the local Ollama server
  - run `ollama serve` before starting GradeAgent
- `BROWSER_USE_SYSTEM_CHROME=true`
  - launches your installed Chrome instead of the bundled automation Chromium build
  - this is usually more stable if you manually use the browser window
- `BROWSER_ENABLE_DEFAULT_EXTENSIONS=false`
  - keeps browser-use from adding its own default automation extensions
  - this lowers the chance of browser freezes and odd site behavior
- `BROWSER_DIRECT_PERSISTENT_PROFILE=true`
  - tells GradeAgent to keep using its own profile directly instead of copying it to a new temp profile each run
  - this reduces disk churn and makes login persistence more reliable
- `BROWSER_CHROME_PROFILE_DIRECTORY=Default`
  - use `Default` for your main Chrome profile
  - use `Profile 1`, `Profile 2`, and so on for other Chrome profiles
- `BROWSER_PERSISTENT_PROFILE_DIR=artifacts/browser/browser-use-user-data-dir-gradeagent`
  - this is where GradeAgent keeps its own saved login state between runs
  - if you delete this folder, GradeAgent will forget the saved login and start fresh
- `BROWSER_CLEANUP_STALE_AFTER_SECONDS=3600`
  - old browser temp folders older than this are deleted automatically
  - the default is 1 hour
- `BROWSER_MAX_SAVED_SCREENSHOTS=3`
  - only the newest few screenshots are kept
  - older screenshots are deleted automatically
- saved passwords
  - GradeAgent now bootstraps mostly login/site data instead of copying a full Chrome profile
  - the reliable part here is saved login state, cookies, and site data
  - password autofill itself can still be unreliable in automation
  - the best flow is: log in once in the GradeAgent browser, then reuse that saved session later

## Disk Space

GradeAgent now tries to keep browser storage under control automatically.

It cleans up:

- per-run download folders,
- browser-use temp agent folders,
- old browser temp folders left from crashes,
- old screenshots beyond the saved screenshot limit.

It does not delete:

- your persistent GradeAgent login profile,
- your normal Chrome profile.

## If Something Does Not Work

### `gradeagent` command not found

Windows:

```powershell
npm run cli
```

Mac:

Make sure the virtual environment is active first:

```bash
source .venv/bin/activate
gradeagent
```

### Browser opens but agent says it is not on the exam page

That means you pressed `Enter` too early.

Fix:

1. start grading again,
2. make sure the browser is already on the real exam main screen,
3. then press `Enter` in the terminal.

### Browser does not reuse my normal Chrome login

Try this:

1. set `BROWSER_USE_SYSTEM_CHROME=true`
2. set `BROWSER_CHROME_PROFILE_DIRECTORY=Default`
3. start `gradeagent`
4. log in once inside the GradeAgent browser
5. close GradeAgent
6. start `gradeagent` again

If the second run is still logged out, delete the folder in `BROWSER_PERSISTENT_PROFILE_DIR`, then repeat the login once more.

### Browser agent feels too slow locally

Try this:

1. make sure Ollama is running,
2. keep `qwen3:4b` for grading,
3. if browser accuracy is fine, stay on `qwen3-vl:4b`,
4. if browser actions are too weak but your Mac has enough memory, switch to `qwen3-vl:8b`.

### Agent is grading too aggressively

Put stricter wording into `--instructions`.

Example:

```bash
start grading --instructions "Be conservative. If unsure, give the lower reasonable score."
```

## Testing

Backend tests:

```bash
python -m pytest apps/api/tests
```

## GitHub And Mac

Use this flow if you build on the Windows PC and then run the product on the Mac.

### What gets pushed

Push the source code and config template:

- `apps/`
- `README.md`
- `.env.example`
- `package.json`
- `docker-compose.yml`
- `.gitignore`
- `.gitattributes`

Do not push:

- `.env`
- `.venv/`
- `artifacts/`
- `gradeagent.db`
- browser login profiles

### Push from Windows

In PowerShell, from the project root:

```powershell
git init
git add .
git commit -m "Initial GradeAgent commit"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/YOUR-REPO.git
git push -u origin main
```

If you already created the GitHub repo in the browser, replace `YOUR-USERNAME` and `YOUR-REPO` with the real values.

### Pull on the Mac

In Terminal on the Mac:

```bash
git clone https://github.com/YOUR-USERNAME/YOUR-REPO.git
cd YOUR-REPO
cp .env.example .env
```

Then install and start the local runtime:

```bash
brew install ollama
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ./apps/api[dev]
python -m playwright install chromium
ollama serve
```

In another terminal on the Mac, pull the models once:

```bash
ollama pull qwen3:4b
ollama pull qwen3:8b
ollama pull qwen3-vl:4b
```

Then start the product:

```bash
source .venv/bin/activate
gradeagent
```

### Updating the Mac later

When you change code on Windows and push again:

```powershell
git add .
git commit -m "Update GradeAgent"
git push
```

Then on the Mac:

```bash
cd YOUR-REPO
git pull
source .venv/bin/activate
python -m pip install -e ./apps/api[dev]
```

## Notes

- The old API and web UI still exist in the repo, but the intended way to use the program is now the terminal CLI.
- The browser agent uses `browser-use` and Playwright.
- The default setup no longer needs Gemini, Claude, or OpenAI API keys.
