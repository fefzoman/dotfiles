#!/usr/bin/env bash
set -euo pipefail

export HOMEBREW_NO_REQUIRE_TAP_TRUST=1
export PATH="$HOME/.local/bin:$PATH"
DOTFILES_AUTO_APPROVE=${DOTFILES_AUTO_APPROVE:-0}
OS="$(uname -s)"

case "$OS" in
  Darwin) ;;
  Linux)
    [[ -r /etc/os-release ]] || { echo "Linux distribution cannot be identified." >&2; exit 1; }
    . /etc/os-release
    case "${ID:-}:${ID_LIKE:-}" in
      debian:*|ubuntu:*|*:debian*) ;;
      *) echo "Supported Linux distributions: Debian and Ubuntu." >&2; exit 1 ;;
    esac
    ;;
  *) echo "Unsupported operating system: $OS" >&2; exit 1 ;;
esac

run_root() {
  if (( EUID == 0 )); then
    "$@"
  elif ! command -v sudo >/dev/null 2>&1; then
    echo "sudo is required to install system packages." >&2
    return 1
  elif [[ "$DOTFILES_AUTO_APPROVE" == "1" ]]; then
    sudo -n "$@"
  else
    sudo "$@"
  fi
}

if [[ "$OS" == Darwin ]]; then
  echo "==> Installing Homebrew if missing..."
  if ! command -v brew >/dev/null 2>&1; then
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    for brew_bin in /opt/homebrew/bin/brew /usr/local/bin/brew; do
      [[ -x "$brew_bin" ]] || continue
      eval "$("$brew_bin" shellenv)"
      break
    done
  fi

  echo "==> Updating Homebrew..."
  brew update
fi

TARGET_PYTHON_MAJOR=3
TARGET_PYTHON_MINOR=13
TARGET_PYTHON_FORMULA="python@${TARGET_PYTHON_MAJOR}.${TARGET_PYTHON_MINOR}"
NODE_MAJOR=22
FORCE_REMOVE_PYTHON=${FORCE_REMOVE_PYTHON:-0}
ALACRITTY_VERSION=${ALACRITTY_VERSION:-0.17.0}
ALACRITTY_SHA256=${ALACRITTY_SHA256:-ad8d7de35fb38e43184776cac6dfee05ca325caa0b6639a06a55e54e4b026620}

python_version_at_least_target() {
  local version="$1"
  local major minor

  IFS=. read -r major minor _ <<<"$version"
  [[ -n "${major:-}" && -n "${minor:-}" ]] || return 1
  (( major > TARGET_PYTHON_MAJOR || major == TARGET_PYTHON_MAJOR && minor >= TARGET_PYTHON_MINOR ))
}

current_python_version() {
  local py_cmd
  for py_cmd in python python3; do
    command -v "$py_cmd" >/dev/null 2>&1 || continue
    "$py_cmd" --version 2>&1 | awk '{print $2}'
    return
  done
  return 1
}

install_python_runtime_macos() {
  local current_version=""
  local python_prefix python_bin shim

  current_version="$(current_python_version 2>/dev/null || true)"

  if [[ -n "$current_version" ]] && python_version_at_least_target "$current_version"; then
    echo "==> Python $current_version meets the ${TARGET_PYTHON_MAJOR}.${TARGET_PYTHON_MINOR} target."
  else
    echo "==> Python ${current_version:-missing} is below the ${TARGET_PYTHON_MAJOR}.${TARGET_PYTHON_MINOR} target."
  fi

  echo "==> Installing Python ${TARGET_PYTHON_MAJOR}.${TARGET_PYTHON_MINOR}..."
  brew install "$TARGET_PYTHON_FORMULA"

  echo "==> Removing other user-managed Python installs..."

  if command -v pyenv >/dev/null 2>&1; then
    while IFS= read -r py_version; do
      [[ -n "$py_version" ]] || continue
      pyenv uninstall -f "$py_version" || true
    done < <(pyenv versions --bare 2>/dev/null | grep -v '^system$' || true)
  fi

  while IFS= read -r formula; do
    [[ -n "$formula" ]] || continue
    [[ "$formula" == "$TARGET_PYTHON_FORMULA" ]] && continue
    if [[ "$FORCE_REMOVE_PYTHON" == "1" ]]; then
      brew uninstall --ignore-dependencies "$formula" || true
      continue
    fi

    local local_dependents
    local_dependents="$(brew uses --installed --formula "$formula" 2>/dev/null || true)"
    if [[ -n "$local_dependents" ]]; then
      echo "==> Skipping $formula; required by: ${local_dependents//$'\n'/, }"
      continue
    fi

    brew uninstall "$formula" || true
  done < <(brew list --formula 2>/dev/null | grep -E '^python(@|$)' || true)

  python_prefix="$(brew --prefix "$TARGET_PYTHON_FORMULA")"
  python_bin="${python_prefix}/bin/python${TARGET_PYTHON_MAJOR}.${TARGET_PYTHON_MINOR}"

  [[ -x "$python_bin" ]] || { echo "Expected Python binary is missing: $python_bin" >&2; exit 1; }

  if ! "$python_bin" -c 'import platform, xml.parsers.expat; raise SystemExit(not platform.mac_ver()[0])' >/dev/null 2>&1; then
    echo "==> Homebrew Python is broken; using uv-managed Python ${TARGET_PYTHON_MAJOR}.${TARGET_PYTHON_MINOR}..."
    command -v uv >/dev/null 2>&1 || brew install uv
    uv python install "${TARGET_PYTHON_MAJOR}.${TARGET_PYTHON_MINOR}"
    python_bin="$(uv python find "${TARGET_PYTHON_MAJOR}.${TARGET_PYTHON_MINOR}")"
    uv pip install --python "$python_bin" --break-system-packages pip
  fi

  mkdir -p "${HOME}/.local/bin"
  for shim in python python3; do
    cat > "${HOME}/.local/bin/$shim" <<EOF
#!/usr/bin/env bash
exec "${python_bin}" "\$@"
EOF
  done
  for shim in pip pip3; do
    cat > "${HOME}/.local/bin/$shim" <<EOF
#!/usr/bin/env bash
exec env PIP_BREAK_SYSTEM_PACKAGES=1 "${python_bin}" -m pip "\$@"
EOF
  done
  chmod +x "${HOME}/.local/bin/"{python,python3,pip,pip3}

  mkdir -p "${HOME}/.config/pip" "${HOME}/.pip"
  cat > "${HOME}/.config/pip/pip.conf" <<'EOF'
[global]
break-system-packages = true
EOF
  cp "${HOME}/.config/pip/pip.conf" "${HOME}/.pip/pip.conf"

  echo "==> Python shims installed: python, pip, python3, pip3 -> ${TARGET_PYTHON_MAJOR}.${TARGET_PYTHON_MINOR}"
}

linux_arch() {
  case "$(uname -m)" in
    x86_64|amd64) printf 'x86_64\n' ;;
    arm64|aarch64) printf 'arm64\n' ;;
    *) echo "Unsupported Linux architecture: $(uname -m)" >&2; return 1 ;;
  esac
}

install_linux_system_packages() {
  echo "==> Installing Debian/Ubuntu packages..."
  run_root env DEBIAN_FRONTEND=noninteractive apt-get update -y
  run_root env DEBIAN_FRONTEND=noninteractive apt-get install -y \
    alacritty bash build-essential ca-certificates clangd curl dconf-cli fd-find fontconfig \
    git ripgrep tmux unzip wget xclip xz-utils
  run_root env DEBIAN_FRONTEND=noninteractive apt-get install -y btop || true
}

install_node_runtime_linux() {
  local arch archive expected target version work_dir

  arch="$(linux_arch)"
  [[ "$arch" == x86_64 ]] && arch=x64
  version="$(curl -fsSL https://nodejs.org/dist/index.tab |
    awk -v prefix="v${NODE_MAJOR}." 'NR > 1 && index($1, prefix) == 1 { print $1; exit }')"
  [[ -n "$version" ]] || { echo "Cannot determine the latest Node ${NODE_MAJOR} version." >&2; return 1; }

  archive="node-${version}-linux-${arch}.tar.xz"
  work_dir="$(mktemp -d "${TMPDIR:-/tmp}/node-install.XXXXXX")"
  target="$HOME/.local/opt/node"
  curl -fsSL -o "$work_dir/$archive" "https://nodejs.org/dist/$version/$archive"
  curl -fsSL -o "$work_dir/SHASUMS256.txt" "https://nodejs.org/dist/$version/SHASUMS256.txt"
  expected="$(awk -v file="$archive" '$2 == file { print $1 }' "$work_dir/SHASUMS256.txt")"
  [[ -n "$expected" ]] || { echo "Node checksum is missing." >&2; return 1; }
  printf '%s  %s\n' "$expected" "$work_dir/$archive" | sha256sum --check --status
  tar -xJf "$work_dir/$archive" -C "$work_dir"

  mkdir -p "$HOME/.local/opt" "$HOME/.local/bin"
  [[ ! -e "$target" ]] || mv "$target" "${target}.bak.$(date +%Y%m%d%H%M%S)"
  mv "$work_dir/node-${version}-linux-${arch}" "$target"
  for binary in node npm npx corepack; do
    [[ -x "$target/bin/$binary" ]] || continue
    ln -sfn "$target/bin/$binary" "$HOME/.local/bin/$binary"
  done
  rm -rf "$work_dir"
}

install_python_runtime_linux() {
  local uv_bin="$HOME/.local/bin/uv" python_bin shim

  mkdir -p "$HOME/.local/bin"
  if [[ ! -x "$uv_bin" ]]; then
    echo "==> Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | env UV_UNMANAGED_INSTALL="$HOME/.local/bin" sh
  fi

  echo "==> Installing Python ${TARGET_PYTHON_MAJOR}.${TARGET_PYTHON_MINOR} with uv..."
  "$uv_bin" python install "${TARGET_PYTHON_MAJOR}.${TARGET_PYTHON_MINOR}"
  python_bin="$("$uv_bin" python find "${TARGET_PYTHON_MAJOR}.${TARGET_PYTHON_MINOR}")"
  "$uv_bin" pip install --python "$python_bin" --break-system-packages pip

  for shim in python python3; do
    cat > "$HOME/.local/bin/$shim" <<EOF
#!/usr/bin/env bash
exec "${python_bin}" "\$@"
EOF
  done
  for shim in pip pip3; do
    cat > "$HOME/.local/bin/$shim" <<EOF
#!/usr/bin/env bash
exec env PIP_BREAK_SYSTEM_PACKAGES=1 "${python_bin}" -m pip "\$@"
EOF
  done
  chmod +x "$HOME/.local/bin/"{python,python3,pip,pip3}

  mkdir -p "$HOME/.config/pip" "$HOME/.pip"
  printf '[global]\nbreak-system-packages = true\n' > "$HOME/.config/pip/pip.conf"
  cp "$HOME/.config/pip/pip.conf" "$HOME/.pip/pip.conf"
}

install_neovim_linux() {
  local arch archive_name work_dir target

  arch="$(linux_arch)"
  archive_name="nvim-linux-${arch}.tar.gz"
  work_dir="$(mktemp -d "${TMPDIR:-/tmp}/neovim-install.XXXXXX")"
  target="$HOME/.local/opt/nvim"
  curl -fsSL -o "$work_dir/$archive_name" \
    "https://github.com/neovim/neovim/releases/latest/download/$archive_name"
  tar -xzf "$work_dir/$archive_name" -C "$work_dir"
  mkdir -p "$HOME/.local/opt" "$HOME/.local/bin"
  [[ ! -e "$target" ]] || mv "$target" "${target}.bak.$(date +%Y%m%d%H%M%S)"
  mv "$work_dir/nvim-linux-${arch}" "$target"
  ln -sfn "$target/bin/nvim" "$HOME/.local/bin/nvim"
  rm -rf "$work_dir"
}

install_kubectl_linux() {
  local arch version work_dir binary checksum

  arch="$(linux_arch)"
  [[ "$arch" == x86_64 ]] && arch=amd64
  version="$(curl -fsSL https://dl.k8s.io/release/stable.txt)"
  work_dir="$(mktemp -d "${TMPDIR:-/tmp}/kubectl-install.XXXXXX")"
  binary="$work_dir/kubectl"
  curl -fsSL -o "$binary" "https://dl.k8s.io/release/$version/bin/linux/$arch/kubectl"
  checksum="$(curl -fsSL "https://dl.k8s.io/release/$version/bin/linux/$arch/kubectl.sha256")"
  printf '%s  %s\n' "$checksum" "$binary" | sha256sum --check --status
  install -m 0755 "$binary" "$HOME/.local/bin/kubectl"
  rm -rf "$work_dir"
}

install_terraform_linux() {
  local arch version work_dir archive expected

  arch="$(linux_arch)"
  [[ "$arch" == x86_64 ]] && arch=amd64
  version="$(curl -fsSL https://checkpoint-api.hashicorp.com/v1/check/terraform | sed -n 's/.*"current_version":"\([^"]*\)".*/\1/p')"
  [[ -n "$version" ]] || { echo "Cannot determine the latest Terraform version." >&2; return 1; }
  work_dir="$(mktemp -d "${TMPDIR:-/tmp}/terraform-install.XXXXXX")"
  archive="terraform_${version}_linux_${arch}.zip"
  curl -fsSL -o "$work_dir/$archive" "https://releases.hashicorp.com/terraform/$version/$archive"
  curl -fsSL -o "$work_dir/SHA256SUMS" \
    "https://releases.hashicorp.com/terraform/$version/terraform_${version}_SHA256SUMS"
  expected="$(awk -v file="$archive" '$2 == file { print $1 }' "$work_dir/SHA256SUMS")"
  [[ -n "$expected" ]] || { echo "Terraform checksum is missing." >&2; return 1; }
  printf '%s  %s\n' "$expected" "$work_dir/$archive" | sha256sum --check --status
  unzip -oq "$work_dir/$archive" -d "$HOME/.local/bin"
  chmod +x "$HOME/.local/bin/terraform"
  rm -rf "$work_dir"
}

install_lazygit_linux() {
  local arch version work_dir archive expected

  arch="$(linux_arch)"
  version="$(curl -fsSL https://api.github.com/repos/jesseduffield/lazygit/releases/latest | sed -n 's/.*"tag_name": "v\([^"]*\)".*/\1/p' | head -n 1)"
  [[ -n "$version" ]] || { echo "Cannot determine the latest LazyGit version." >&2; return 1; }
  work_dir="$(mktemp -d "${TMPDIR:-/tmp}/lazygit-install.XXXXXX")"
  archive="lazygit_${version}_linux_${arch}.tar.gz"
  curl -fsSL -o "$work_dir/$archive" \
    "https://github.com/jesseduffield/lazygit/releases/download/v$version/$archive"
  curl -fsSL -o "$work_dir/checksums.txt" \
    "https://github.com/jesseduffield/lazygit/releases/download/v$version/checksums.txt"
  expected="$(awk -v file="$archive" '$2 == file { print $1 }' "$work_dir/checksums.txt")"
  [[ -n "$expected" ]] || { echo "LazyGit checksum is missing." >&2; return 1; }
  printf '%s  %s\n' "$expected" "$work_dir/$archive" | sha256sum --check --status
  tar -xzf "$work_dir/$archive" -C "$work_dir" lazygit
  install -m 0755 "$work_dir/lazygit" "$HOME/.local/bin/lazygit"
  rm -rf "$work_dir"
}

install_broot_linux() {
  local arch target work_dir

  arch="$(linux_arch)"
  [[ "$arch" == x86_64 ]] && target=x86_64-unknown-linux-musl || target=aarch64-unknown-linux-musl
  work_dir="$(mktemp -d "${TMPDIR:-/tmp}/broot-install.XXXXXX")"
  curl -fsSL -o "$work_dir/broot" "https://dystroy.org/broot/download/$target/broot"
  install -m 0755 "$work_dir/broot" "$HOME/.local/bin/broot"
  rm -rf "$work_dir"
}

install_nerd_font_linux() {
  local work_dir font_dir

  work_dir="$(mktemp -d "${TMPDIR:-/tmp}/font-install.XXXXXX")"
  font_dir="$HOME/.local/share/fonts/JetBrainsMonoNerdFont"
  mkdir -p "$font_dir"
  curl -fsSL -o "$work_dir/JetBrainsMono.zip" \
    https://github.com/ryanoasis/nerd-fonts/releases/latest/download/JetBrainsMono.zip
  unzip -oq "$work_dir/JetBrainsMono.zip" -d "$font_dir"
  fc-cache -f "$font_dir"
  rm -rf "$work_dir"
}

install_linux_user_tools() {
  mkdir -p "$HOME/.local/bin"
  ln -sfn "$(command -v fdfind)" "$HOME/.local/bin/fd"
  install_neovim_linux
  install_kubectl_linux
  install_terraform_linux
  install_lazygit_linux
  install_broot_linux
  npm install --global --prefix "$HOME/.local" tree-sitter-cli
  "$HOME/.local/bin/pip" install --upgrade basedpyright
  install_nerd_font_linux
}

install_broot_shell_function() {
  local launcher="$HOME/.config/broot/launcher/bash/br"

  # On macOS broot only uses ~/.config/broot when it already exists, otherwise
  # it falls back to ~/Library/Application Support. Create it so the launcher
  # lands in the same place on both platforms.
  mkdir -p "$HOME/.config/broot"
  # broot only patches shell rc files that already exist.
  touch "$HOME/.bashrc"
  # --install writes the br function and patches ~/.bashrc without prompting;
  # it skips files that already source the launcher, so re-runs are safe.
  broot --install
  [[ -f "$launcher" ]] || { echo "broot launcher is missing at $launcher" >&2; return 1; }
}

# Must run after install_broot_shell_function: until the br function is marked
# installed, broot's first launch tries to ask for permission to install it and
# gives up before it writes any configuration.
configure_broot() {
  local conf="$HOME/.config/broot/conf.hjson"

  mkdir -p "$HOME/.config/broot"
  # broot writes its default configuration files on its first launch. It cannot
  # start its interface without a terminal, so this headless run fails right
  # after writing them; check for the file rather than the exit status.
  [[ -f "$conf" ]] || broot --cmd ":quit" "$HOME/.config/broot" >/dev/null 2>&1 || true
  [[ -f "$conf" ]] || { echo "broot did not write $conf" >&2; return 1; }

  # The `g` flag shows the git status column, the current branch and the diff
  # stats on every launch. An existing setting is left alone.
  python - "$conf" <<'PY'
import re
import sys
from pathlib import Path

conf = Path(sys.argv[1])
text = conf.read_text(encoding="utf-8")
if re.search(r"(?m)^\s*default_flags:", text):
    raise SystemExit(0)
patched, count = re.subn(r"(?m)^#\s*default_flags:.*$", "default_flags: g", text, count=1)
if count == 0:
    patched = text.rstrip() + "\n\ndefault_flags: g\n"
conf.write_text(patched, encoding="utf-8")
PY
}

install_alacritty() {
  local app="/Applications/Alacritty.app"
  local installed_version="" quarantine="" work_dir dmg mount_dir actual_sha backup

  installed_version="$(defaults read "$app/Contents/Info" CFBundleShortVersionString 2>/dev/null || true)"
  quarantine="$(xattr -p com.apple.quarantine "$app" 2>/dev/null || true)"
  if [[ "$installed_version" == "$ALACRITTY_VERSION" && -z "$quarantine" ]] &&
    codesign --verify --deep --strict "$app" >/dev/null 2>&1; then
    echo "==> Alacritty $ALACRITTY_VERSION is already installed."
    return
  fi

  echo "==> Installing checksum-verified Alacritty $ALACRITTY_VERSION..."
  work_dir="$(mktemp -d "${TMPDIR:-/tmp}/alacritty-install.XXXXXX")"
  dmg="$work_dir/Alacritty.dmg"
  mount_dir="$work_dir/mount"
  mkdir -p "$mount_dir"
  curl -fsSL -o "$dmg" \
    "https://github.com/alacritty/alacritty/releases/download/v$ALACRITTY_VERSION/Alacritty-v$ALACRITTY_VERSION.dmg"
  actual_sha="$(shasum -a 256 "$dmg" | awk '{print $1}')"
  if [[ "$actual_sha" != "$ALACRITTY_SHA256" ]]; then
    echo "Alacritty checksum mismatch: expected $ALACRITTY_SHA256, got $actual_sha" >&2
    rm -rf "$work_dir"
    return 1
  fi
  hdiutil attach "$dmg" -nobrowse -readonly -mountpoint "$mount_dir" >/dev/null

  if brew list --cask alacritty >/dev/null 2>&1; then
    brew uninstall --cask --force alacritty
  fi
  if [[ -e "$app" ]]; then
    backup="${app}.bak.$(date +%Y%m%d%H%M%S)"
    echo "==> Preserving existing Alacritty app at $backup"
    mv "$app" "$backup"
  fi

  ditto "$mount_dir/Alacritty.app" "$app"
  hdiutil detach "$mount_dir" >/dev/null
  mkdir -p "$HOME/.terminfo/61"
  cp -f "$app/Contents/Resources/61/"{alacritty,alacritty-direct} "$HOME/.terminfo/61/"
  codesign --verify --deep --strict "$app"
  if xattr -p com.apple.quarantine "$app" >/dev/null 2>&1; then
    echo "Alacritty unexpectedly has a quarantine attribute; refusing to bypass Gatekeeper." >&2
    return 1
  fi
  rm -rf "$work_dir"
}

if [[ "$OS" == Darwin ]]; then
  install_python_runtime_macos
  echo "==> Installing CLI tools..."
  brew tap hashicorp/tap
  brew install bash tmux neovim git curl btop kubectl lazygit ripgrep fd broot \
    basedpyright llvm tree-sitter-cli hashicorp/tap/terraform
  brew upgrade bash || true

  echo "==> Installing Alacritty and JetBrainsMono Nerd Font..."
  install_alacritty
  brew install --cask font-jetbrains-mono-nerd-font
else
  install_linux_system_packages
  install_python_runtime_linux
  install_node_runtime_linux
  install_linux_user_tools
fi

echo "==> Installing the broot br shell function..."
install_broot_shell_function
echo "==> Writing broot configuration with git info enabled..."
configure_broot

BACKUP_TS="$(date +%Y%m%d%H%M%S)"
backup_file() { [[ ! -f $1 ]] || cp "$1" "$1.bak.$BACKUP_TS"; }

echo "==> Setting up Alacritty theme files..."
mkdir -p "${HOME}/.config/alacritty"

if [[ ! -d "${HOME}/.config/alacritty/themes" ]]; then
  git clone https://github.com/alacritty/alacritty-theme "${HOME}/.config/alacritty/themes"
else
  git -C "${HOME}/.config/alacritty/themes" pull --ff-only || true
fi

echo "==> Writing Alacritty config to ~/.config/alacritty/alacritty.toml ..."
backup_file "${HOME}/.config/alacritty/alacritty.toml"
TMUX_BIN="$(command -v tmux)"
[[ "$OS" == Darwin ]] && WINDOW_DECORATIONS=Buttonless || WINDOW_DECORATIONS=Full

cat > "${HOME}/.config/alacritty/alacritty.toml" <<ALACRITTY
[general]
import = ["~/.config/alacritty/themes/themes/gruvbox_dark.toml"]

[window]
decorations = "${WINDOW_DECORATIONS}"
padding = { x = 10, y = 10 }

[font]
size = 15

[colors.primary]
foreground = "#BAB7AD"

[font.normal]
family = "JetBrainsMono Nerd Font"
style = "Thin"

[font.bold]
family = "JetBrainsMono Nerd Font"
style = "Medium"

[cursor]
style = { shape = "Beam", blinking = "Off" }
thickness = 0.10
unfocused_hollow = false

[terminal]
shell = { program = "${TMUX_BIN}", args = ["new-session", "-A", "-s", "main"] }
ALACRITTY

echo "==> Setting Alacritty as main terminal helper..."

mkdir -p "${HOME}/.local/bin"
if [[ "$OS" == Darwin ]]; then
  ln -sf "$(brew --prefix llvm)/bin/clangd" "${HOME}/.local/bin/clangd"
  cat > "${HOME}/.local/bin/alacritty" <<'ALACRITTY_WRAPPER'
#!/usr/bin/env bash
open -na "Alacritty" --args "$@"
ALACRITTY_WRAPPER
else
  CLANGD_BIN="$(command -v clangd)"
  ALACRITTY_BIN="$(command -v alacritty)"
  ln -sf "$CLANGD_BIN" "${HOME}/.local/bin/clangd"
  cat > "${HOME}/.local/bin/alacritty" <<ALACRITTY_WRAPPER
#!/usr/bin/env bash
exec "${ALACRITTY_BIN}" "\$@"
ALACRITTY_WRAPPER
fi

chmod +x "${HOME}/.local/bin/alacritty"

echo "==> Installing vim-plug for Neovim..."
curl -fLo "${HOME}/.local/share/nvim/site/autoload/plug.vim" --create-dirs \
  https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim

echo "==> Writing Neovim config to ~/.config/nvim/init.vim ..."
mkdir -p "${HOME}/.config/nvim"
backup_file "${HOME}/.config/nvim/init.vim"

cat > "${HOME}/.config/nvim/init.vim" <<'VIMRC'
set mouse=a
set number
set smarttab
set tabstop=2
set shiftwidth=2
set softtabstop=2
set autoindent termguicolors
set guicursor=n-v-c-sm:block,i-ci-ve:ver10,r-cr-o:hor20,t:block-blinkon500-blinkoff500-TermCursor
syntax on

call plug#begin('~/.local/share/nvim/plugged')
Plug 'vim-airline/vim-airline'
Plug 'ashfinal/vim-colors-violet'
Plug 'ryanoasis/vim-devicons'
Plug 'nvim-lua/plenary.nvim'
Plug 'neovim/nvim-lspconfig'
Plug 'nvim-telescope/telescope.nvim', { 'tag': '*' }
Plug 'kdheepak/lazygit.nvim'
Plug 'MunifTanjim/nui.nvim'
Plug 'nvim-tree/nvim-web-devicons'
Plug 'nvim-neo-tree/neo-tree.nvim', { 'branch': 'v3.x' }
Plug 'stephpy/vim-yaml'
Plug 'andrewstuart/vim-kubernetes'
Plug 'towolf/vim-helm'
Plug 'hashivim/vim-terraform'
Plug 'nvim-mini/mini.pairs', { 'branch': 'stable' }
Plug 'nvim-mini/mini.surround', { 'branch': 'stable' }
Plug 'lukas-reineke/indent-blankline.nvim'
Plug 'nvim-treesitter/nvim-treesitter', { 'do': ':TSUpdate' }

call plug#end()

let mapleader = " "
lua << EOF
local function setup_plugin(name, config)
  local ok, plugin = pcall(require, name)
  if ok then
    plugin.setup(config or {})
  end
end

setup_plugin('mini.pairs')
setup_plugin('mini.surround')
setup_plugin('ibl')

local ok_treesitter, treesitter = pcall(require, 'nvim-treesitter')
if ok_treesitter then
  treesitter.setup({})
  vim.treesitter.language.register('hcl', { 'hcl', 'terraform' })
  vim.api.nvim_create_autocmd('FileType', {
    pattern = { 'bash', 'c', 'cpp', 'hcl', 'lua', 'python', 'terraform', 'vim', 'vimdoc', 'yaml' },
    callback = function()
      pcall(vim.treesitter.start)
    end,
  })
end

local ok_telescope, builtin = pcall(require, 'telescope.builtin')
if ok_telescope then
  vim.keymap.set('n', '<leader>ff', builtin.find_files, { desc = 'Find files' })
  vim.keymap.set('n', '<leader>fg', builtin.live_grep, { desc = 'Search text' })
  vim.keymap.set('n', '<leader>fb', builtin.buffers, { desc = 'Find buffers' })
  vim.keymap.set('n', '<leader>fh', builtin.help_tags, { desc = 'Find help' })
end

local ok_neotree, neotree = pcall(require, 'neo-tree')
if ok_neotree then
  neotree.setup({})
end

vim.diagnostic.config({ virtual_text = true, signs = true, underline = true })

vim.api.nvim_create_autocmd('LspAttach', {
  callback = function(args)
    local opts = { buffer = args.buf }
    local function map(lhs, rhs, desc)
      vim.keymap.set('n', lhs, rhs, vim.tbl_extend('force', opts, { desc = desc }))
    end

    map('gd', vim.lsp.buf.definition, 'Go to definition')
    map('gr', vim.lsp.buf.references, 'Show references')
    map('K', vim.lsp.buf.hover, 'Show documentation')
    map('<leader>rn', vim.lsp.buf.rename, 'Rename symbol')
    map('<leader>ca', vim.lsp.buf.code_action, 'Code action')
    map('<leader>f', function() vim.lsp.buf.format({ async = true }) end, 'Format buffer')
    map('[d', function() vim.diagnostic.jump({ count = -1, float = true }) end, 'Previous diagnostic')
    map(']d', function() vim.diagnostic.jump({ count = 1, float = true }) end, 'Next diagnostic')
    vim.bo[args.buf].omnifunc = 'v:lua.vim.lsp.omnifunc'

    local function completion_key(menu_key, fallback)
      return function()
        return vim.fn.pumvisible() == 1 and menu_key or fallback
      end
    end
    local insert_opts = { buffer = args.buf, expr = true, silent = true }
    vim.keymap.set('i', '<Tab><Tab>', completion_key('<C-n>', '<C-x><C-o>'), insert_opts)
    vim.keymap.set('i', '<Down>', completion_key('<C-n>', '<Down>'), insert_opts)
    vim.keymap.set('i', '<Up>', completion_key('<C-p>', '<Up>'), insert_opts)
    vim.keymap.set('i', '<CR>', completion_key('<C-y>', '<CR>'), insert_opts)
  end,
})

local servers = { 'basedpyright', 'clangd' }
local clangd = { cmd = { 'clangd', '--background-index', '--clang-tidy' } }

if vim.lsp.config and vim.lsp.enable then
  vim.lsp.config('clangd', clangd)
  vim.lsp.enable(servers)
else
  local ok_lsp, lspconfig = pcall(require, 'lspconfig')
  if ok_lsp then
    for _, server in ipairs(servers) do
      lspconfig[server].setup(server == 'clangd' and clangd or {})
    end
  end
end
EOF

nnoremap <leader>e :Neotree toggle<CR>
nnoremap <leader>lg :LazyGit<CR>
nnoremap <leader>t :tabedit<Space>
nnoremap <leader>tw :tabclose<CR>
nnoremap <leader>tn :tabnew<CR>
nnoremap gh :tabnext<CR>
nnoremap gj :tabprevious<CR>

let g:terraform_fmt_on_save = 1
let g:terraform_align = 1
autocmd BufRead,BufNewFile *.tf,*.tfvars set filetype=terraform
autocmd BufRead,BufNewFile *.hcl set filetype=hcl
autocmd BufRead,BufNewFile Chart.yaml,values.yaml,*.yaml,*.yml set filetype=yaml

if !empty(globpath(&rtp, 'colors/violet.vim'))
  colorscheme violet
endif
VIMRC

echo "==> Installing Neovim plugins headlessly..."
nvim --headless +'PlugInstall --sync' +qa
nvim --headless +"lua require('nvim-treesitter').install({ 'bash', 'c', 'cpp', 'hcl', 'lua', 'python', 'vim', 'vimdoc', 'yaml' }):wait(300000)" +qa

echo "==> Writing tmux config to ~/.tmux.conf ..."
backup_file "${HOME}/.tmux.conf"

TMUX_SHELL="$(command -v bash)"
if [[ "$OS" == Darwin ]]; then
  TMUX_SHELL="$(brew --prefix bash)/bin/bash"
fi
printf 'set -g default-shell "%s"\n' "$TMUX_SHELL" > "${HOME}/.tmux.conf"
cat >> "${HOME}/.tmux.conf" <<'TMUXCONF'
set -g status-position top
set -g base-index 1
setw -g pane-base-index 1
set -g renumber-windows on
set -g mouse on

set -g status-style "bg=default,fg=white"
setw -g window-status-style "bg=default,fg=white"
setw -g window-status-current-style "bg=default,fg=cyan"
set -g message-style "bg=default,fg=white"
set -g status-right ""

bind-key -r Left  select-pane -L
bind-key -r Right select-pane -R
bind-key -r Up    select-pane -U
bind-key -r Down  select-pane -D

bind-key , split-window -h
bind-key . split-window -v

unbind-key &
bind q confirm-before -p "kill window #W? (y/n)" kill-window
bind k confirm-before -p "kill session #S? (y/n)" kill-session
TMUXCONF

echo "==> Basic installation complete."
