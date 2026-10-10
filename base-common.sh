# Sourced by base-macos.sh and base-linux.sh.
export PATH="$HOME/.local/bin:$PATH"
DOTFILES_AUTO_APPROVE=${DOTFILES_AUTO_APPROVE:-0}
PY_VERSION=3.13
CONFIG_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/config"
BIN="$HOME/.local/bin"
OPT="$HOME/.local/opt"
STAMP="$(date +%Y%m%d%H%M%S)"
PY_PACKAGES="$HOME/.local/state/dotfiles/python-packages.txt"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dotfiles-install.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$BIN" "$OPT"

have() { command -v "$1" >/dev/null 2>&1; }
die() { echo "$*" >&2; exit 1; }
backup() { [[ ! -e $1 ]] || mv "$1" "$1.bak.$STAMP"; }

write_python_shims() {
  local shim
  for shim in python python3; do
    printf '#!/usr/bin/env bash\nexec "%s" "$@"\n' "$1" > "$BIN/$shim"
  done
  for shim in pip pip3; do
    printf '#!/usr/bin/env bash\nexec env PIP_BREAK_SYSTEM_PACKAGES=1 "%s" -m pip "$@"\n' "$1" > "$BIN/$shim"
  done
  chmod +x "$BIN/"{python,python3,pip,pip3}
  mkdir -p "$HOME/.config/pip" "$HOME/.pip"
  cp "$CONFIG_DIR/pip/pip.conf" "$HOME/.config/pip/pip.conf"
  cp "$CONFIG_DIR/pip/pip.conf" "$HOME/.pip/pip.conf"
}

# Records top-level packages of the active non-system Python so a version change can reinstall them.
save_python_packages() {
  local py prefix pkgs
  py="$(command -v python3 || true)"
  [[ -n $py ]] || return 0
  prefix="$("$py" -c 'import sys; print(sys.base_prefix)' 2>/dev/null)" || return 0
  case $prefix in /usr|/usr/*|/System/*|/Library/Developer/*) return 0 ;; esac
  pkgs="$("$py" -m pip list --not-required --exclude-editable --format=freeze 2>/dev/null |
    sed 's/==.*//' | grep -vixE 'pip|setuptools|wheel')" || return 0
  mkdir -p "${PY_PACKAGES%/*}"
  echo "$pkgs" > "$PY_PACKAGES"
}

restore_python_packages() {
  local pkg
  [[ -s $PY_PACKAGES ]] || return 0
  echo "==> Installing and upgrading saved Python packages..."
  "$BIN/pip" install --upgrade -r "$PY_PACKAGES" && return
  while read -r pkg; do
    "$BIN/pip" install --upgrade "$pkg" || echo "warning: could not install Python package $pkg" >&2
  done < "$PY_PACKAGES"
}

install_uv_python() {
  local uv="$1" python_bin
  "$uv" python install "$PY_VERSION"
  python_bin="$("$uv" python find "$PY_VERSION")"
  "$uv" pip install --python "$python_bin" --break-system-packages pip
  write_python_shims "$python_bin"
}

configure_broot() {
  local dir="$HOME/.config/broot"

  # On macOS broot only uses ~/.config/broot if it exists; --install only patches an existing ~/.bashrc.
  mkdir -p "$dir"
  touch "$HOME/.bashrc"
  broot --install
  [[ -f $dir/launcher/bash/br ]] || die "broot launcher is missing at $dir/launcher/bash/br"
  # The first launch writes the default config (only after --install), then fails without a TTY.
  [[ -f $dir/conf.hjson ]] || broot --cmd ":quit" "$dir" >/dev/null 2>&1 || true
  [[ -f $dir/conf.hjson ]] || die "broot did not write $dir/conf.hjson"
  python "$CONFIG_DIR/broot/set-default-flags.py" "$dir/conf.hjson"
}

install_navi_cheatsheets() {
  local repo
  repo="$(navi info default-cheats-path 2>/dev/null || navi info cheats-path)/denisidoro__navi-tldr-pages"
  if [[ -d $repo/.git ]]; then
    git -C "$repo" pull --ff-only
  else
    git clone --depth 1 https://github.com/denisidoro/navi-tldr-pages.git "$repo"
  fi
}

# Usage: finish_setup <window decorations> <clangd path> <tmux shell> <alacritty launcher command>
finish_setup() {
  local decorations="$1" clangd="$2" tmux_shell="$3" wrapper="$4" themes="$HOME/.config/alacritty/themes" conf

  echo "==> Installing tldr, updating npm globals, broot shell function and Navi cheatsheets..."
  npm install --global --prefix "$HOME/.local" tldr
  npm update --global --prefix "$HOME/.local"
  configure_broot
  install_navi_cheatsheets

  ln -sf "$clangd" "$BIN/clangd"
  printf '#!/usr/bin/env bash\n%s\n' "$wrapper" > "$BIN/alacritty"
  chmod +x "$BIN/alacritty"

  echo "==> Writing Alacritty config..."
  mkdir -p "$HOME/.config/alacritty" "$HOME/.config/nvim"
  if [[ -d $themes ]]; then
    git -C "$themes" pull --ff-only || true
  else
    git clone https://github.com/alacritty/alacritty-theme "$themes"
  fi
  conf="$(<"$CONFIG_DIR/alacritty/alacritty.toml")"
  conf="${conf//@WINDOW_DECORATIONS@/$decorations}"
  backup "$HOME/.config/alacritty/alacritty.toml"
  printf '%s\n' "${conf//@TMUX_BIN@/$(command -v tmux)}" > "$HOME/.config/alacritty/alacritty.toml"

  echo "==> Writing Neovim config and installing plugins..."
  curl -fLo "$HOME/.local/share/nvim/site/autoload/plug.vim" --create-dirs \
    https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim
  backup "$HOME/.config/nvim/init.vim"
  cp "$CONFIG_DIR/nvim/init.vim" "$HOME/.config/nvim/init.vim"
  nvim --headless +'PlugInstall --sync' +qa
  nvim --headless +"lua require('nvim-treesitter').install({ 'bash', 'c', 'cpp', 'hcl', 'lua', 'python', 'vim', 'vimdoc', 'yaml' }):wait(300000)" +qa

  echo "==> Writing tmux config..."
  backup "$HOME/.tmux.conf"
  { printf 'set -g default-shell "%s"\n' "$tmux_shell"; cat "$CONFIG_DIR/tmux.conf"; } > "$HOME/.tmux.conf"
  echo "==> Basic installation complete."
}
