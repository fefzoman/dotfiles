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

# --- Hex (#RRGGBB) -> GNOME Terminal rgb(r,g,b) ---
hex_to_rgb() {
  local h="${1#\#}"
  [[ ${#h} -eq 6 ]] || { echo "rgb(0,0,0)"; return 0; }
  local r="${h:0:2}" g="${h:2:2}" b="${h:4:2}"
  printf "rgb(%d,%d,%d)" "$((16#$r))" "$((16#$g))" "$((16#$b))"
}

# --- Import GNOME Terminal profiles from Basic.terminal (same directory as this script) ---
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BASIC_TERMINAL_FILE="$SCRIPT_DIR/Basic.terminal"

import_basic_terminal_profile() {
  local f="$1"
  [[ -f "$f" ]] || return 1
  have dconf || return 1
  have gsettings || return 1

  bold "Found: $f"
  bold "Backing up current GNOME Terminal profiles..."
  dconf dump /org/gnome/terminal/legacy/profiles:/ > "$BACKUP_DIR/gnome-terminal-profiles.before.dconf" 2>/dev/null || true

  bold "Importing GNOME Terminal profile(s) via: dconf load /org/gnome/terminal/legacy/profiles:/ < $f"
  dconf load /org/gnome/terminal/legacy/profiles:/ < "$f"

  # If the imported dump contains a profile with visible-name 'Basic', set it as default.
  local entry uuid name
  while read -r entry; do
    uuid="${entry#:}"; uuid="${uuid%/}"
    name="$(dconf read "/org/gnome/terminal/legacy/profiles:/:$uuid/visible-name" 2>/dev/null | tr -d "'")" || true
    if [[ "$name" == "Basic" ]]; then
      gsettings set org.gnome.Terminal.ProfilesList default "'$uuid'" || true
      ok "Set GNOME Terminal default profile to: Basic ($uuid)"
      return 0
    fi
  done < <(dconf list /org/gnome/terminal/legacy/profiles:/ 2>/dev/null || true)

  ok "Imported profile(s). (No visible-name='Basic' found to auto-set default.)"
  return 0
}

apply_gnome_terminal_colors_manual() {
  have gsettings || { warn "gsettings not found; skipping GNOME Terminal setup."; return 0; }
  have dconf     || { warn "dconf not found; skipping GNOME Terminal setup."; return 0; }

  local default_profile
  default_profile="$(gsettings get org.gnome.Terminal.ProfilesList default 2>/dev/null | tr -d "'")" || true
  if [[ -z "${default_profile:-}" || "${default_profile:-}" == "''" ]]; then
    warn "GNOME Terminal default profile not detected; skipping manual color setup."
    return 0
  fi

  bold "Applying GNOME Terminal colors to default profile: $default_profile"
  local base="/org/gnome/terminal/legacy/profiles:/:${default_profile}/"

  local bg_rgb fg_rgb bb_rgb cy_rgb mg_rgb
  bg_rgb="$(hex_to_rgb "$BG")"
  fg_rgb="$(hex_to_rgb "$FG")"
  bb_rgb="$(hex_to_rgb "$BB")"
  cy_rgb="$(hex_to_rgb "$CY")"
  mg_rgb="$(hex_to_rgb "$MG")"

  dconf write "${base}use-theme-colors" "false" || true
  dconf write "${base}use-theme-background" "false" || true
  dconf write "${base}background-color" "'$bg_rgb'" || true
  dconf write "${base}foreground-color" "'$fg_rgb'" || true
  dconf write "${base}bold-color-same-as-fg" "true" || true
  dconf write "${base}cursor-colors-set" "true" || true
  dconf write "${base}cursor-background-color" "'$fg_rgb'" || true
  dconf write "${base}cursor-foreground-color" "'$bg_rgb'" || true

  # 16-color palette as rgb(...) strings (GNOME Terminal expects rgb format)
  local palette
  palette="[
    '$bg_rgb', '$mg_rgb', '$cy_rgb', '$fg_rgb', '$cy_rgb', '$mg_rgb', '$cy_rgb', '$fg_rgb',
    '$bb_rgb', '$mg_rgb', '$cy_rgb', '$fg_rgb', '$cy_rgb', '$mg_rgb', '$cy_rgb', '$fg_rgb'
  ]"
  dconf write "${base}palette" "${palette}" || true

  ok "GNOME Terminal color profile updated (manual fallback)."
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

bold $'\n=== 2) Switch login shell to Bash (disable Zsh as default) ==='
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

bold $'\n=== 3) Install Oh My Bash + enable pure + apply prompt + install Nerd Font + import terminal colors ==='

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

# Persist silence deprecation warning (macOS) in bashrc (instead of exporting only in this script)
if ! grep -qE '^[[:space:]]*export[[:space:]]+BASH_SILENCE_DEPRECATION_WARNING=' "$HOME/.bashrc" 2>/dev/null; then
  printf '\nexport BASH_SILENCE_DEPRECATION_WARNING=1\n' >> "$HOME/.bashrc"
fi

# Set Oh My Bash theme to 'pure'
if grep -qE '^[[:space:]]*OSH_THEME=' "$HOME/.bashrc"; then
  sed -i.bak -E 's|^[[:space:]]*OSH_THEME=.*$|OSH_THEME="pure"|' "$HOME/.bashrc"
else
  printf '\nOSH_THEME="pure"\n' >> "$HOME/.bashrc"
fi

# Append our "Pure-style 2-line prompt" override (matches screenshot layout)
MARK_BEGIN="# >>> pure-screenshot-prompt (managed) >>>"
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

# --- Nerd Font install (moved BEFORE terminal theme import) ---
if [[ "$(uname -s)" == "Darwin" ]]; then
  if command -v brew >/dev/null 2>&1; then
    bold "Installing Nerd Font (JetBrainsMono Nerd Font) via Homebrew..."
    brew install --cask font-jetbrains-mono-nerd-font || true
  else
    warn "Homebrew not found. Install a Nerd Font manually (JetBrainsMono Nerd Font) on macOS."
  fi
fi

# 3a) Prefer importing GNOME Terminal colors from Basic.terminal (same folder as this script)
IMPORTED_BASIC_PROFILE=0
if import_basic_terminal_profile "$BASIC_TERMINAL_FILE"; then
  IMPORTED_BASIC_PROFILE=1
  ok "Basic.terminal imported. Close/reopen GNOME Terminal to see changes."
else
  warn "Basic.terminal not found (expected: $BASIC_TERMINAL_FILE) or dconf/gsettings missing."
  warn "Falling back to manual GNOME Terminal color setup."
fi

# 3b) Manual GNOME Terminal color setup (fallback only)
if (( IMPORTED_BASIC_PROFILE == 0 )); then
  apply_gnome_terminal_colors_manual
fi

bold $'\n=== Done ==='
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

