# CLAUDE.md

## About this project
netaudit: a Python tool that audits a Cisco network and its devices for configuration issues and security problems and suggests
fixes. It connects to switches and routers over SSH, collects their configuration and state,
checks them against best practices regarding security and performance (BPDU guard, port security, duplex, speed/bandwidth, native VLAN, DTP,
CDP on edge ports, SSH/SNMP hardening, ...) and reports what is wrong and how to fix it.
First goal is to create a strong structure of the program, with coherent classes and general design/architecture. Then comes features, like static scanning and finally live scanning of a network while its in use.

It is a learning project with two goals:
1. Reinforce what I learned for the CCNA + extra security.
2. Relearn Python, properly.

## Project model
- netaudit must be deployable to any Cisco network, so nothing in it is specific to one network.
- The user creates and loads projects. Each network is one project, stored on disk.
- Projects are password protected and encrypted on disk.
- netaudit is menu driven: on start, the user creates or loads a project.
- Creating requires a name, a location and a new password. Loading requires a path and the password.
- Recently used project paths are remembered in plain text (paths only, never passwords).
- My own lab is just another project. Nothing specific to it is committed to this public repo.

## How we work (follow this strictly)
This project is built the way a real developer works: small steps, each one understood,
tested and committed before the next.

1. **Plan before code.** For every task, first explain in plain language what you will do,
   which files you will create or change and why (one line each). Then STOP and wait for my OK.
2. **One small piece at a time.** Ideally one function or one class per step. Never more than
   one feature per change. Never bundle unrelated changes.
3. **Explain every change.** After writing code, explain what it does: what goes in, what
   comes out, what it affects (files, network, devices) and what happens on errors.
   Explain any Python construct I might not know in 2-3 sentences.
4. **Let me check my understanding.** After a step, ask me one short question about the code
   (e.g. "what happens if hosts.txt is empty?"). If I get it wrong, explain, don't just move on. (This is just an extra python learning thing)
5. **Run it.** Every step should be something I can run or test immediately. Show me how.
6. **No surprises.** Don't refactor, rename, restructure or "tidy up" anything I didn't ask
   for. If you think something should change, suggest it and wait.
7. **"My turn".** If I write "my turn", don't write the code: guide me with hints and let me
   write it, then review what I wrote.
8. **If I ask "why", explain the reasoning.** Don't just rewrite the code.

## Git workflow
- `main` must always work.
- Each feature gets its own branch (e.g. `feature/ssh-connect`). We will merge to main when it works.
- Small commits with clear messages describing what and why. Commit after each working step.
- Run the tests before every commit.

## Design principles
- **Start simple.** Only add files, classes and layers when they are actually needed. We need to avoid bloat as much as possible.
  Prefer a few clear modules over many small ones. No abstractions "for later".
- **A new audit rule should be easy to add,** ideally by adding one file, without touching
  the rest of the code. Keep this in mind when we get to rules.
- **Clear, readable code over clever code.** Descriptive names, short functions, type hints,
  a docstring on every function and class.
- **Add dependencies one at a time,** and explain why each one is needed.
- **Every code file has a test file:** `x.py` is tested by `tests/test_x.py` (empty `__init__.py` files don't need one).
- **Tests:** use pytest. Test parsers and rules with saved sample output from real devices,
  so tests don't need the lab running.

## Security requirements (this tool holds the keys to the network)
- Never store passwords in plain text on disk. Ask with getpass to start with.
- Read-only by default. Changing device config must always be explicit and confirmed.
- Validate all input that ends up in commands sent to devices (no command injection).
- Never commit device configs, inventories, logs or secrets to Git (.gitignore).

## Roadmap (one milestone at a time, each split into small steps)
0. Project skeleton: virtual environment, folder structure, .gitignore, pytest, a main.py that runs.
1. Projects: create/load a password-protected, encrypted project (config + list of devices). No plain-text passwords on disk.
2. Connect over SSH to ONE device and print `show version`.
3. Collect from all devices in a project and save the running configs in the project folder.
4. Parse ONE show command into Python objects.
5. The first audit rule (BPDU guard on access ports) and a Finding class.
6. A simple report: print findings and save them in the project folder.
7. More rules, one at a time.
8. CDP neighbours and link checks (both ends of a link must match).
9. Suggested fixes; later, applying them safely (revert timer, confirmation).
10. SNMP / traffic analysis.

## Current status
Update this section in the commit of every step.

### Start here next session
- Branch: `feature/project-model`. Milestone 1 is not merged to `main`.
- Activate the venv (`.\.venv\Scripts\Activate.ps1`), then run `python -m pytest`.
  Expected: 301 passed, 1 xfailed (the plain-text password test, until part B).
- Last finished step: menu step 5a, `accept_unknown_host_key` on Host, shown by show hosts.
- Next step: menu step 5b, the add host menu (IP, username, password, accept unknown host key). Then 6 remove host, 7 show log.

### Temporary exception to the security requirements (decided by me)
- Until part B, config, hosts and scans are saved as plain JSON, and `hosts.json` includes the passwords.
  Don't undo this and don't bring encryption forward: structure comes first.
- Don't use it with a real network until part B is done.
- These files are ignored by Git by name: `config.json`, `hosts.json`, their `.tmp`, `*.scan.json`, `configs/`.

### Done
- Milestone 0: project skeleton (venv, .gitignore, main.py, pytest, tests folder).

### In progress: Milestone 1, encrypted projects
Goal: start netaudit, create or load an encrypted project from a menu, add and show hosts.
Order: A, C, D (structure), then B (encryption), then E.
- [ ] A. Project model
  - [x] Project, ProjectConfig, Host, Scan base class
  - [x] Validation
  - [x] Log
- [x] C. Project files
  - [x] Create without overwriting, save and load config and hosts, write and load scans
  - [x] Check paths, clear errors for damaged files
- [ ] D. Menu (`netaudit/menu.py`): create, load, show, add and remove hosts, show log
  - [x] Start menu, create project, load project (with the missing-folders question)
  - [x] Show hosts
  - [ ] Add host, remove host, show log
- [ ] B. Encryption (`netaudit/encryption.py`, doesn't exist yet): key from the password, encrypt and decrypt
- [ ] E. Recent projects: remember paths, pick one when loading

### The code today
- `main.py`: starts the menu, and ends cleanly on Ctrl+C or end of input.
- `netaudit/menu.py`: Menu, the text menu (start menu, create and load project, project menu with show hosts and close),
  and `is_safe_folder_name`.
- `netaudit/project.py`: ProjectConfig (settings) and Project (path, config, hosts, scans, log, issues; create,
  load, add and remove hosts).
- `netaudit/host.py`: Host, one device with its SSH login, privilege level and available commands.
- `netaudit/scans/scans.py`: Scan, the base class of all scans, and SCAN_TYPES.
- `netaudit/log.py`: LogLevel, LogCategory, LogEntry (one event) and ProjectLog (all entries, in memory and file,
  `find` to filter them, `sort_entries` to sort any list of them).

### A project on disk (can be anywhere)
- `config.json`: the project's own settings.
- `hosts.json`: the hosts, becomes `hosts.enc`.
- `configs/`: running configs of the devices. Not the project's settings.
- `scans/`: one file per scan, named `<date>_<time>-<microseconds>_<class>.scan.json`, never overwritten.
- `logs/project.log`: the log, one JSON object per line (ignored by Git through `*.log`).
- Later more, for example topology.

### Decided
- All project files will be encrypted. JSON for most of them, inside the encryption.
- Key from the password: Argon2id. Encryption: Fernet. One salt per project.
- Passwords: at least 12 characters, no recovery. Keep the key in memory, never the project password.
- Only the menu uses input() and print(). Project never asks the user anything.
- Menu is a class (decided by me): `self.project` is the open project, one method per menu and action.
  Each menu prints its own options, reads the choice with `ask`, and calls a method per choice
  (e.g. `create_project_menu`). `q` (or `Q`) exits or goes back. `ask` handles all typed input. `run` shows ValueError and OSError as `Error: ...` on stderr.
  Passwords with getpass. Port and timeout are asked with the default shown. Until part B, create and load
  warn that the project isn't encrypted. Device text is made printable before it is shown.
- A new project's folder is location/name, so the menu only accepts names that are safe folder names
  (`is_safe_folder_name`: letters, digits, spaces, - and _, no reserved Windows names). The location must exist.
  A bad answer while creating goes back to the start menu with an error; nothing is created.
- `hostname` and `privilege_level` are read from the device after login, not typed in. None = not read yet.
  `privilege_level` is the SSH user's level at login (0-15, checked when set). It is not a write protection.
- Device output is parsed by a parser class (Milestone 2), not by Host. Host only checks the values it gets.
- `__post_init__` only runs when a Host is created, not when a field is assigned later. The parser must check
  values before assigning them, with the same functions (like `is_valid_hostname`) so each rule exists once.
- `add_host` and `remove_host` save hosts.json right away. If saving fails, the change is undone in memory.
  No two hosts share an IP, also checked when loading hosts.json.
- ProjectConfig: name 1-64 printable characters (any language), port 1-65535, timeout 1-300 seconds.
- Usernames and passwords can't contain control characters: a line break in a password typed into the CLI
  could send a second command. Error messages never show a password.
- `available_commands` is a list, None = not checked (test with `is None`). It is information only: the commands
  netaudit sends come from a fixed list in the code, never from a project file.
- SSH uses host keys, not certificates. `Host.accept_unknown_host_key` (default False, decided by me): when SSH
  (Milestone 2) meets a key it has never stored for that host, True answers yes by itself, False asks the user.
  A key that changed since it was stored is always refused, whatever the setting (could be a MITM).
- SCAN_TYPES is a plain dict on purpose (easy to read). Each new scan class gets a line, key = class name.
- A scan stores host IPs, never Host objects (they contain passwords).
- `Project.create(path, config)` and `Project.load(path)` are classmethods that return a complete Project.
  The constructor stays plain (no disk access). `load_hosts` and `load_scans` refresh parts of an existing project.
- The log is our own class, not the `logging` module (encryption in part B, reading it back in the menu).
  An entry has a category (PROJECT, HOST, SCAN, CHECK, MISC) and a level (INFO, WARNING, ERROR, SECURITY).
  SCAN = collecting data from devices, CHECK = checking it for problems.
- Findings are not log entries: they are stored with the scan. The log only gets a summary line per scan.
  Finding severity will be its own enum on the Finding class (Milestone 5).
- ProjectLog keeps all entries in memory. `write(entry)` writes to the file first, then to the list.
  Create a LogEntry right before writing it, so its time is when it happened.
  `write` gives each entry its number: `_last_number` + 1 (not len + 1). `load` sets `_last_number` to the
  highest number in the file (max, so moved lines can't cause a repeat), `write` updates it after writing. None = not in the file, as for
  the in-memory warnings about damaged lines. A failed write leaves the entry without a number.
  A damaged line is skipped on load, with a warning in memory only (loading never changes the file).
  `write` adds a line break first if the file ends with a half-written line.
- `log.entries` always stays in file order. `find` and `sort_entries` return new lists and never write.
- Only one netaudit per open project: two would each have their own entries and hosts in memory.
- PROJECT_FOLDERS lists the project folders. Load creates a missing `logs/` itself and logs a warning for
  every missing folder. The others are only created when the user chooses to (asked by the menu).
- `project.issues`: dict from ProjectIssue (a fixed Enum) to details, for problems found by load that the menu
  must handle. The log is the history, `issues` the current state. Each fix removes its issue.
  Added early on purpose (decided by me), with one kind so far. Damaged scans may become the next kind.
- Every kind of damage in config.json, hosts.json or a scan file is a ValueError "<file> is damaged: ...",
  so the menu only has to catch ValueError and OSError. A missing config.json stays FileNotFoundError.
- Never log secrets. JSON lines escape line breaks, so device text can't fake log entries.
- Host checks its data in `__post_init__`, so a bad Host can't exist, from the menu or from hosts.json.
  IPv4 only for now (decided by me). Type checks come before value checks.
- `repr=False` only protects printing. `asdict()` includes passwords, so never print or log its result.

### Not decided yet
- Whether one damaged scan should stop the whole project from loading, as it does now.
- Whether device names may show in file names under `configs/` once files are encrypted (Milestone 3).
- Deleting projects: in the project.py docstring, not planned yet.

### Known gaps (all reproduced)
- An interrupted `Scan.write` leaves a broken file, and then the project won't load.
- A failed `Project.create` leaves the folder behind, so trying again raises FileExistsError.
- `Project.create` doesn't save hosts, only the config. Call `save_hosts` after.
- `Scan.write` can't save datetime or Path fields of subclasses, and tuples load back as lists.

### Notes for part B
- Gaps in log numbers mean deleted lines. A later check could report them as a SECURITY warning.
- Bind each encrypted file to its path, as Fernet can't detect two swapped files.
- A plain `project.salt` file was proposed for the salt.
- Ignore `*.enc` and `*.enc.tmp` in Git. Remove the xfail marker when the plain-text test passes.

### Notes for Milestone 2
- Privilege level: `show privilege` prints "Current privilege level is N". It is refused at level 0, so treat a
  refusal as level 0 or restricted. The prompt hints too: `>` = 0-1, `#` = 2-15.
- Hostname: device output is untrusted. Check it against Cisco's rules (starts with a letter, letters, digits and
  `-`, at most 63 characters) before storing it, and again before using it in file names (Milestone 3).
- Fill `available_commands` by reading `show ?`. Never test a command by running it if it could change something.
- With AAA command authorization a listed command can still be refused, so handle refusals when running it.
- Below privilege 15 `show running-config` can be incomplete. Never report "passed" from incomplete data.
- How `?` behaves inside CLI views is unverified: test it in a lab.
