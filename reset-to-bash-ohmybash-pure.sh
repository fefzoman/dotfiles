#!/usr/bin/env bash
set -euo pipefail

# ====== Settings (the exact colors you requested) ======
BG="#2D2D2D"
FG="#EBE0BB"
BB="#767676"        # bright black (used for user@host)
CY="#68847F"        # cyan/teal (used for path)
MG="#A9758C"        # magenta/pink (used for prompt symbol)
# =======================================================

ts="$(date +%Y%m%d%H%M%S)"
BACKUP_DIR="$HOME/.shell-reset-backup/$ts"
mkdir -p "$BACKUP_DIR"

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
warn() { printf "\033[33m%s\033[0m\n" "$*"; }
ok()   { printf "\033[32m%s\033[0m\n" "$*"; }

move_to_backup() {
  local p="$1"
  if [[ -e "$p" || -L "$p" ]]; then
    mkdir -p "$BACKUP_DIR/$(dirname "${p#$HOME/}")" 2>/dev/null || true
    bold "Backing up: $p  ->  $BACKUP_DIR/"
    mv -f "$p" "$BACKUP_DIR/" || true
  fi
}

have() { command -v "$1" >/dev/null 2>&1; }

install_pkgs() {
  local pkgs=("$@")
  local sudo=""
  if [[ $EUID -ne 0 ]]; then
    have sudo && sudo="sudo" || sudo=""
  fi

  if have apt-get; then
    [[ -n "$sudo" ]] || warn "No sudo found; dependency install may fail."
    $sudo apt-get update -y || true
    $sudo apt-get install -y "${pkgs[@]}" || true
  elif have dnf; then
    [[ -n "$sudo" ]] || warn "No sudo found; dependency install may fail."
    $sudo dnf install -y "${pkgs[@]}" || true
  elif have pacman; then
    [[ -n "$sudo" ]] || warn "No sudo found; dependency install may fail."
    $sudo pacman -Sy --noconfirm "${pkgs[@]}" || true
  elif have zypper; then
    [[ -n "$sudo" ]] || warn "No sudo found; dependency install may fail."
    $sudo zypper install -y "${pkgs[@]}" || true
  elif have brew; then
    brew install "${pkgs[@]}" || true
  else
    warn "No supported package manager detected. Install dependencies manually: git curl wget dconf-cli"
  fi
}

bold "=== 1) Reset Bash/Zsh customizations (backup + clean start) ==="
# Bash dotfiles
move_to_backup "$HOME/.bashrc"
move_to_backup "$HOME/.bash_profile"
move_to_backup "$HOME/.bash_login"
move_to_backup "$HOME/.profile"
move_to_backup "$HOME/.inputrc"
move_to_backup "$HOME/.bash_aliases"

# Zsh dotfiles / frameworks
move_to_backup "$HOME/.zshrc"
move_to_backup "$HOME/.zprofile"
move_to_backup "$HOME/.zshenv"
move_to_backup "$HOME/.zlogin"
move_to_backup "$HOME/.zlogout"
move_to_backup "$HOME/.oh-my-zsh"
move_to_backup "$HOME/.zinit"
move_to_backup "$HOME/.antigen"
move_to_backup "$HOME/.p10k.zsh"
move_to_backup "$HOME/.config/starship.toml"

# Bash frameworks
move_to_backup "$HOME/.oh-my-bash"
move_to_backup "$HOME/.bash_it"

ok "Backups stored in: $BACKUP_DIR"
warn "If you use chezmoi (or similar), it may re-apply old dotfiles after this."

bold "\n=== 2) Switch login shell to Bash (disable Zsh as default) ==="
BASH_PATH="$(command -v bash || true)"
if [[ -z "${BASH_PATH}" ]]; then
  warn "bash not found in PATH. Aborting."
  exit 1
fi

if [[ "${SHELL:-}" != "$BASH_PATH" ]]; then
  if have chsh; then
    bold "Attempting: chsh -s $BASH_PATH"
    if chsh -s "$BASH_PATH" >/dev/null 2>&1; then
      ok "Login shell set to bash. (You must log out/in for it to fully take effect.)"
    else
      warn "chsh failed (often needs your password or admin policy). Run manually:"
      warn "  chsh -s $BASH_PATH"
    fi
  else
    warn "chsh not available. Set your default shell to bash manually."
  fi
else
  ok "Your \$SHELL already points to bash."
fi

bold "\n=== 3) Install Oh My Bash + enable 'pure' + apply prompt + set terminal colors ==="

# Dependencies
bold "Installing dependencies (git, curl, wget, dconf-cli if possible)..."
install_pkgs git curl wget dconf-cli

# Install Oh My Bash (official installer)
if [[ ! -d "$HOME/.oh-my-bash" ]]; then
  bold "Installing Oh My Bash..."
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  curl -fsSL "https://raw.githubusercontent.com/ohmybash/oh-my-bash/master/tools/install.sh" -o "$tmp/install-omb.sh"
  bash "$tmp/install-omb.sh" --unattended
else
  ok "Oh My Bash already installed."
fi

# Ensure ~/.bashrc exists
touch "$HOME/.bashrc"

# Set Oh My Bash theme to 'pure'
if grep -qE '^[[:space:]]*OSH_THEME=' "$HOME/.bashrc"; then
  sed -i.bak -E 's|^[[:space:]]*OSH_THEME=.*$|OSH_THEME="pure"|' "$HOME/.bashrc"
else
  printf '\nOSH_THEME="pure"\n' >> "$HOME/.bashrc"
fi

# Append our "Pure-style 2-line prompt" override (matches screenshot layout)
# We do this AFTER Oh My Bash loads so it can't overwrite the prompt.
MARK_BEGIN="# >>> pure-screenshot-prompt (managed) >>>"
MARK_END="# <<< pure-screenshot-prompt (managed) <<<"
if ! grep -qF "$MARK_BEGIN" "$HOME/.bashrc"; then
  cat >> "$HOME/.bashrc" <<'EOF'

# >>> pure-screenshot-prompt (managed) >>>
# This overrides PS1 to match the 2-line Pure-style look:
#   user@host  ~/path (gitbranch)
#   ❯
__pureish_git_branch() {
  command -v git >/dev/null 2>&1 || return 0
  git rev-parse --is-inside-work-tree >/dev/null 2>&1 || return 0
  git branch --show-current 2>/dev/null || true
}

__pureish_prompt() {
  local exit_code=$?
  local c_reset="\[$(tput sgr0)\]"
  local c_bb="\[$(tput setaf 8)\]"     # bright black
  local c_cy="\[$(tput setaf 6)\]"     # cyan
  local c_mg="\[$(tput setaf 13)\]"    # bright magenta
  local c_rd="\[$(tput setaf 1)\]"     # red

  local userhost="${c_bb}\u@\h${c_reset}"
  local path="${c_cy}\w${c_reset}"

  local gitb="$(__pureish_git_branch)"
  local gitpart=""
  if [[ -n "$gitb" ]]; then
    gitpart=" ${c_bb}${gitb}${c_reset}"
  fi

  local sym_color="$c_mg"
  if [[ $exit_code -ne 0 ]]; then sym_color="$c_rd"; fi

  PS1="${userhost} ${path}${gitpart}\n${sym_color}❯${c_reset} "
}

# Chain after any existing PROMPT_COMMAND, and run our prompt last.
__PUREISH_OLD_PROMPT_COMMAND="${PROMPT_COMMAND-}"
if [[ -n "${__PUREISH_OLD_PROMPT_COMMAND}" ]]; then
  PROMPT_COMMAND="${__PUREISH_OLD_PROMPT_COMMAND}; __pureish_prompt"
else
  PROMPT_COMMAND="__pureish_prompt"
fi
# <<< pure-screenshot-prompt (managed) <<<
EOF
fi

# Apply GNOME Terminal color profile automatically (if possible)
if have gsettings && have dconf; then
  default_profile="$(gsettings get org.gnome.Terminal.ProfilesList default 2>/dev/null | tr -d "'")" || true
  if [[ -n "${default_profile:-}" && "${default_profile:-}" != "''" ]]; then
    bold "Applying GNOME Terminal colors to default profile: $default_profile"
    base="/org/gnome/terminal/legacy/profiles:/:${default_profile}/"

    dconf write "${base}use-theme-colors" "false" || true
    dconf write "${base}use-theme-background" "false" || true
    dconf write "${base}background-color" "'$BG'" || true
    dconf write "${base}foreground-color" "'$FG'" || true
    dconf write "${base}bold-color-same-as-fg" "true" || true
    dconf write "${base}cursor-colors-set" "true" || true
    dconf write "${base}cursor-background-color" "'$FG'" || true
    dconf write "${base}cursor-foreground-color" "'$BG'" || true

    # Full 16-color palette:
    # Exact-matched slots: background/foreground/cursor + brightBlack + cyan + magenta + whites
    # Other slots are conservative defaults (not visible in your screenshot).
    palette="[
      '$BG', '$MG', '$CY', '$FG', '$CY', '$MG', '$CY', '$FG',
      '$BB', '$MG', '$CY', '$FG', '$CY', '$MG', '$CY', '$FG'
    ]"
    dconf write "${base}palette" "${palette}" || true
    ok "GNOME Terminal color profile updated."
  else
    warn "GNOME Terminal profile not detected; skipping auto color setup."
  fi
else
  warn "gsettings/dconf not found; skipping GNOME Terminal auto color setup."
fi

bold "\n=== Done ==="
ok "1) Close ALL terminals and reopen."
ok "2) Log out/in to ensure your login shell is bash."
ok "3) Verify:"
echo "   echo \$SHELL"
echo "   bash --version"
echo
ok "Your backups are in: $BACKUP_DIR"
warn "If you want to restore: copy files back from that folder into \$HOME."

# That suppresses the “Last login” banner in new Terminal sessions.
touch ~/.hushlogin

export BASH_SILENCE_DEPRECATION_WARNING=1


# --- Nerd Font install ---
if [[ "$(uname -s)" == "Darwin" ]]; then
  if command -v brew >/dev/null 2>&1; then
    brew install --cask font-jetbrains-mono-nerd-font || true
  else
    echo "Homebrew not found. Install a Nerd Font manually (JetBrainsMono Nerd Font) on macOS."
  fi
fi
