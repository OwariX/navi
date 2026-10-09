# NAVI on Windows

NAVI runs on macOS and Linux. On Windows it runs inside **WSL** (Windows Subsystem for Linux), which gives you a real
Linux next to Windows. Your browser stays the Windows one. Started natively on Windows, NAVI says so and points here:
it needs pseudo-terminals, file locks and process groups that Windows doesn't have.

*These steps follow Microsoft's WSL setup and haven't been run on a Windows machine by us yet. If one doesn't match what
you see, please [open an issue](https://github.com/OwariX/navi/issues).*

## 1. Install WSL

In PowerShell, as administrator:

```powershell
wsl --install
```

Restart when it asks, then open **Ubuntu** from the Start menu and pick a user name and password. That's your Linux
terminal; everything below runs there.

## 2. Install Python and git

```bash
sudo apt update && sudo apt install -y python3 git
python3 --version        # 3.9 or newer
```

## 3. Install an engine, inside WSL

NAVI drives an agent program, and it has to live where NAVI does: in WSL, not in Windows.

- **Claude Code:** `curl -fsSL https://claude.ai/install.sh | bash`, then run `claude` once to sign in.
- **Codex or Gemini CLI:** install Node.js (`sudo apt install -y nodejs npm`, or a newer one through nvm), then
  `npm i -g @openai/codex` or `npm i -g @google/gemini-cli`.
- **Local models:** see step 6.

## 4. Install NAVI

```bash
git clone https://github.com/OwariX/navi ~/navi && ~/navi/install.sh
```

The installer ends by asking which engine NAVI runs on (`navi engine` changes it later).

## 5. Use it

```bash
cd ~/code/your-project && navi
```

- **Keep projects in Linux** (`~/code/...`), not under `/mnt/c/...`: files there are many times slower for everything
  an agent does. VS Code's *WSL* extension opens them from Windows.
- **The browser:** NAVI prints its address (`http://127.0.0.1:<port>/`). WSL passes `localhost` through to Windows,
  so open it in your usual browser. To have NAVI open it for you: `sudo apt install -y wslu`, then add
  `export BROWSER=wslview` to `~/.bashrc`.
- `navi tui` runs the whole council in the Ubuntu terminal instead.

## 6. Local models (Ollama)

Either way works.

- **Ollama inside WSL:** `curl -fsSL https://ollama.com/install.sh | sh`. It uses an NVIDIA GPU through WSL's CUDA
  support. NAVI finds it at its usual address with nothing to set.
- **Ollama for Windows:** the Windows app, on the Windows side. WSL then has to reach it:
  - **Windows 11:** turn on mirrored networking, so `localhost` is shared. Put the following in
    `%UserProfile%\.wslconfig`, then run `wsl --shutdown`:
    ```ini
    [wsl2]
    networkingMode=mirrored
    ```
  - **Otherwise:** let Ollama listen on every interface (set `OLLAMA_HOST=0.0.0.0` in Windows' environment variables,
    then restart Ollama). In WSL, point NAVI at the Windows host:
    `navi engine use local --url http://$(ip route show default | awk '{print $3}'):11434`.

Then `navi engine` and pick **Local**.

## Taking it off again

`navi uninstall` in WSL. To remove WSL's Ubuntu entirely: `wsl --unregister Ubuntu` in PowerShell (this deletes
everything in it).
