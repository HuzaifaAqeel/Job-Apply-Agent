# Job-Apply-Agent

A profile-driven CLI agent that fills online job applications for you. Point it at an application form, and it discovers every field, maps it to your profile, generates a tailored cover letter and screening answers with an LLM — and in **dry-run mode** shows you exactly what it would fill before anything is typed or submitted.

## How it works

```
profile.yaml ──┐
               ├─▶ discover fields (Playwright) ─▶ map to profile ─▶ fill plan
LLM (Gemini) ──┘        │                                    │
                        ▼                                    ▼
                 cover letters + screening answers     dry-run log / live fill
                                                        │
                                                        ▼
                                              applications.db (SQLite)
```

1. **Profile-driven** — one `profile.yaml` (name, experience, skills, pre-baked answers) feeds every form.
2. **Smart field mapping** — label/name/placeholder heuristics map fields to profile values; file uploads are flagged, never auto-submitted blindly.
3. **LLM-written text** — cover letters and open-ended screening questions are generated with Gemini (`GOOGLE_API_KEY`), falling back to profile pre-baked answers for common questions (salary, sponsorship, notice period) answered directly from your profile.
4. **Dry-run first** — the default mode logs the complete fill plan without touching the page.
5. **Blocker detection** — pauses on CAPTCHAs and login walls instead of failing silently.
6. **Application log** — every run (dry or live) is recorded in SQLite: URL, mode, status, fields filled.

## Setup

```bash
pip install -r requirements.txt
pip install -e .            # installs the `job-apply-agent` console command
playwright install chromium
cp profile.yaml.example profile.yaml   # fill in your details
cp .env.example .env                   # add GOOGLE_API_KEY
```

API keys are read from environment variables only — never hardcoded, never committed.

## Usage

```bash
# Always dry-run first: see the full fill plan, nothing typed
job-apply-agent apply "https://jobs.example.com/apply/123" --dry-run

# Actually fill the form in the browser (asks before submitting)
job-apply-agent apply "https://jobs.example.com/apply/123" --live

# Fill + submit without the confirmation prompt
job-apply-agent apply "https://jobs.example.com/apply/123" --live --yes

# Review past runs
job-apply-agent log
job-apply-agent log --limit 20

# Validate your profile
job-apply-agent profile check
```

No API key? Pass `--mock-llm` to run end-to-end with template-generated text (clearly marked).

## Project layout

```
src/job_apply_agent/
  cli.py        # apply | log | profile commands
  agent.py      # navigate -> discover -> plan -> dry-run/fill orchestration
  forms.py      # Playwright field discovery + profile mapping heuristics
  llm.py        # Gemini client (env-var key) + cover letter / answer generators
  profile.py    # profile.yaml loading + validation
  store.py      # SQLite application log
demo/demo_application.html   # sample form used by the demo
tests/test_core.py           # unit tests (no browser needed)
```

## Tests

```bash
pytest tests/ -v
```

## Safety notes

- Dry-run is the default; live submission always asks for confirmation unless `--yes`.
- The agent never bypasses CAPTCHAs or login walls — it reports them as blockers.
- Automating applications may violate a site's terms of service; use responsibly and always review the fill plan before submitting.

## License

MIT — see `LICENSE`.
