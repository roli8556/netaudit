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

### Done
- Milestone 0: project skeleton (venv, .gitignore, main.py, pytest, tests folder).

### In progress: Milestone 1, encrypted projects
Goal: start netaudit, create or load an encrypted project from a menu, add and show devices.
- [ ] A. Project model: Project, ProjectConfig, log and hosts, validation, conversion for saving
- [ ] B. Encryption (`netaudit/encryption.py`): key from the password, encrypt and decrypt
- [ ] C. Project files (`netaudit/project.py`): keep them out of Git, check paths, create, save, load
- [ ] D. Menu (`netaudit/menu.py`): create, load, show and add devices
- [ ] E. Recent projects: remember paths, pick one when loading

### Decided
- A project is a folder with different kinds of files (config, device configs, topology, log, ...), all encrypted.
- JSON for most files, inside the encryption.
- `project.py` handles creating and loading projects.
- `host.py` defines Host: ip, hostname, SSH username, password and optional enable password.
- Hosts are saved in `hosts.enc` (JSON, encrypted), passwords included. Never save hosts unencrypted.
- Key from the password: Argon2id. Encryption: Fernet.
- Passwords: at least 12 characters, no recovery.

### Not decided yet
- Log classes in `netaudit/log.py` (proposed: LogEntry, and a ProjectLog attached to Project)

### Right now
- Branch: `feature/project-model`
- Last finished step: Project has a list of hosts
- Temporary: save writes plain JSON. It must be encrypted in part B, before it is used with a real network.
- Next step (proposed): part B, encryption, which hosts.enc depends on. The log and validation also remain.
