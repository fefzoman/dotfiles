#!/usr/bin/env bash
set -euo pipefail

DOTFILES_AUTO_APPROVE=${DOTFILES_AUTO_APPROVE:-0}
CONFIG_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/config/bash"
BACKUP_DIR="$HOME/.shell-reset-backup/$(date +%Y%m%d%H%M%S)"
LOGIN_USER="${SUDO_USER:-${USER:-$(id -un)}}"
OS="$(uname -s)"
mkdir -p "$BACKUP_DIR"

bold() { printf "\033[1m%s\033[0m\n" "$*"; }
warn() { printf "\033[33m%s\033[0m\n" "$*"; }
ok()   { printf "\033[32m%s\033[0m\n" "$*"; }
have() { command -v "$1" >/dev/null 2>&1; }

run_root() {
  if (( EUID == 0 )); then
    "$@"
  elif ! have sudo; then
    warn "sudo is unavailable; skipped: $*"
    return 1
  elif [[ $DOTFILES_AUTO_APPROVE == 1 ]]; then
    sudo -n "$@"
  else
    sudo "$@"
  fi
}

install_pkgs() {
  if have apt-get; then
    run_root env DEBIAN_FRONTEND=noninteractive apt-get update -y || true
    run_root env DEBIAN_FRONTEND=noninteractive apt-get install -y "$@" || true
  elif have dnf; then
    run_root dnf install -y "$@" || true
  elif have pacman; then
    run_root pacman -Sy --noconfirm "$@" || true
  elif have zypper; then
    run_root zypper install -y "$@" || true
  elif have brew; then
    brew install "$@" || true
  else
    warn "No supported package manager; install manually: $*"
  fi
}

latest_bash_path() {
  local prefix
  if have brew; then
    brew install bash >/dev/null 2>&1 || true
    brew upgrade bash >/dev/null 2>&1 || true
    prefix="$(brew --prefix bash 2>/dev/null || true)"
    if [[ -n $prefix && -x $prefix/bin/bash ]]; then echo "$prefix/bin/bash"; return; fi
  fi
  if [[ $OS == Linux && -x /bin/bash ]]; then echo /bin/bash; return; fi
  command -v bash || true
}

account_login_shell() {
  if [[ $OS == Darwin ]] && have dscl; then
    dscl . -read "/Users/$LOGIN_USER" UserShell 2>/dev/null | awk '{print $2}'
  elif have getent; then
    getent passwd "$LOGIN_USER" | awk -F: '{print $7}'
  else
    awk -F: -v user="$LOGIN_USER" '$1 == user { print $7 }' /etc/passwd
  fi
}

register_login_shell() {
  [[ -f /etc/shells ]] || return 0
  ! grep -Fxq "$1" /etc/shells || return 0
  bold "Registering login shell: $1"
  if [[ -w /etc/shells ]]; then
    echo "$1" >> /etc/shells
  elif ! echo "$1" | run_root tee -a /etc/shells >/dev/null; then
    warn "Cannot update /etc/shells; run: echo '$1' | sudo tee -a /etc/shells"
    return 1
  fi
}

change_login_shell() {
  if [[ $DOTFILES_AUTO_APPROVE == 1 ]]; then
    run_root chsh -s "$1" "$LOGIN_USER"
  else
    chsh -s "$1"
  fi
}

bold "=== 1) Switch login shell to Bash ==="
BASH_PATH="$(latest_bash_path)"
[[ -n $BASH_PATH ]] || { warn "bash not found in PATH."; exit 1; }
CURRENT_SHELL="$(account_login_shell)"

if [[ $CURRENT_SHELL == "$BASH_PATH" ]]; then
  ok "The account login shell already points to Bash: $BASH_PATH"
else
  register_login_shell "$BASH_PATH" || exit 1
  have chsh || { warn "chsh is unavailable; cannot set the login shell."; exit 1; }
  bold "Changing the login shell from ${CURRENT_SHELL:-unknown} to $BASH_PATH"
  if ! change_login_shell "$BASH_PATH"; then
    if [[ $DOTFILES_AUTO_APPROVE == 1 ]]; then
      warn "Could not change the login shell; auto-approve cannot supply credentials. Run: sudo chsh -s '$BASH_PATH' '$LOGIN_USER'"
    else
      warn "Could not change the login shell. Run manually: chsh -s '$BASH_PATH'"
    fi
    exit 1
  fi
  CURRENT_SHELL="$(account_login_shell)"
  [[ $CURRENT_SHELL == "$BASH_PATH" ]] || { warn "The login shell is still ${CURRENT_SHELL:-unknown}; expected $BASH_PATH."; exit 1; }
  ok "Login shell set to Bash. Log out and back in before checking \$SHELL."
fi

bold $'\n=== 2) Back up and remove Bash/Zsh customizations ==='
for path in \
  .bashrc .bash_profile .bash_login .profile .inputrc .bash_aliases \
  .zshrc .zprofile .zshenv .zlogin .zlogout .oh-my-zsh .zinit .antigen .p10k.zsh \
  .config/starship.toml .oh-my-bash .bash_it; do
  [[ -e $HOME/$path || -L $HOME/$path ]] || continue
  bold "Backing up: $HOME/$path"
  mkdir -p "$(dirname "$BACKUP_DIR/$path")"
  mv "$HOME/$path" "$BACKUP_DIR/$path"
done
warn "If you use chezmoi (or similar), it may re-apply old dotfiles after this."

bold $'\n=== 3) Install Oh My Bash, prompt and completions ==='
install_pkgs git curl wget dconf-cli

if [[ -d $HOME/.oh-my-bash ]]; then
  ok "Oh My Bash already installed."
else
  bold "Installing Oh My Bash..."
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  curl -fsSL https://raw.githubusercontent.com/ohmybash/oh-my-bash/master/tools/install.sh -o "$tmp/install-omb.sh"
  bash "$tmp/install-omb.sh" --unattended
fi

# Activation updates Oh My Bash itself; parallel tmux shells racing on auto-update leave a stale lock.
sed -i.bak 's/^# DISABLE_AUTO_UPDATE="true"$/DISABLE_AUTO_UPDATE="true"/' "$HOME/.bashrc"
rm -f "$HOME/.bashrc.bak"

mkdir -p "$HOME/.oh-my-bash/custom/themes/font"
cp "$CONFIG_DIR/font.theme.sh" "$HOME/.oh-my-bash/custom/themes/font/font.theme.sh"
cp "$CONFIG_DIR/tool-completions.sh" "$HOME/.oh-my-bash/custom/tool-completions.sh"
cp "$CONFIG_DIR/bash_profile" "$HOME/.bash_profile"
if ! grep -qx '# BEGIN DOTFILES' "$HOME/.bashrc"; then
  { echo; cat "$CONFIG_DIR/bashrc"; } >> "$HOME/.bashrc"
fi

# Replacing ~/.bashrc dropped the line that sources broot's br function.
if have broot; then
  bold "Restoring the broot br shell function..."
  broot --install || warn "broot --install failed; the br function is unavailable."
fi

if [[ $OS == Darwin ]]; then
  if have brew; then
    bold "Installing JetBrainsMono Nerd Font via Homebrew..."
    brew install --cask font-jetbrains-mono-nerd-font || true
  else
    warn "Homebrew not found. Install JetBrainsMono Nerd Font manually."
  fi
fi

touch "$HOME/.hushlogin"

bold $'\n=== Done ==='
ok "Close all terminals, log out and back in, then verify with: echo \$SHELL; bash --version"
ok "Backups are in $BACKUP_DIR; copy files back into \$HOME to restore."
