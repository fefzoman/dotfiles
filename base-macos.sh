#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/base-common.sh"

FORCE_REMOVE_PYTHON=${FORCE_REMOVE_PYTHON:-0}
ALACRITTY_VERSION=${ALACRITTY_VERSION:-0.17.0}
ALACRITTY_SHA256=${ALACRITTY_SHA256:-ad8d7de35fb38e43184776cac6dfee05ca325caa0b6639a06a55e54e4b026620}
[[ "$(uname -s)" == Darwin ]] || die "base-macos.sh runs only on macOS."

install_python_macos() {
  local formula="python@$PY_VERSION" python_bin v f deps

  save_python_packages
  echo "==> Installing Python $PY_VERSION and removing other user-managed Pythons..."
  brew install "$formula"
  if have pyenv; then
    while read -r v; do
      pyenv uninstall -f "$v" || true
    done < <(pyenv versions --bare 2>/dev/null | grep -v '^system$' || true)
  fi
  while read -r f; do
    [[ $f != "$formula" ]] || continue
    if [[ $FORCE_REMOVE_PYTHON == 1 ]]; then
      brew uninstall --ignore-dependencies "$f" || true
    elif deps="$(brew uses --installed --formula "$f" 2>/dev/null)" && [[ -n $deps ]]; then
      echo "==> Skipping $f; required by: ${deps//$'\n'/, }"
    else
      brew uninstall "$f" || true
    fi
  done < <(brew list --formula 2>/dev/null | grep -E '^python(@|$)' || true)

  python_bin="$(brew --prefix "$formula")/bin/python$PY_VERSION"
  [[ -x $python_bin ]] || die "Expected Python binary is missing: $python_bin"
  if "$python_bin" -c 'import platform, xml.parsers.expat; raise SystemExit(not platform.mac_ver()[0])' >/dev/null 2>&1; then
    write_python_shims "$python_bin"
  else
    echo "==> Homebrew Python is broken; using uv-managed Python $PY_VERSION..."
    have uv || brew install uv
    install_uv_python uv
  fi
  restore_python_packages
  echo "==> Python shims installed: python, pip, python3, pip3 -> $PY_VERSION"
}

install_alacritty_macos() {
  local app=/Applications/Alacritty.app dmg="$WORK/Alacritty.dmg" mnt="$WORK/alacritty-mount" sha

  if [[ "$(defaults read "$app/Contents/Info" CFBundleShortVersionString 2>/dev/null)" == "$ALACRITTY_VERSION" ]] &&
    ! xattr -p com.apple.quarantine "$app" >/dev/null 2>&1 &&
    codesign --verify --deep --strict "$app" >/dev/null 2>&1; then
    echo "==> Alacritty $ALACRITTY_VERSION is already installed."
    return
  fi

  echo "==> Installing checksum-verified Alacritty $ALACRITTY_VERSION..."
  curl -fsSL -o "$dmg" \
    "https://github.com/alacritty/alacritty/releases/download/v$ALACRITTY_VERSION/Alacritty-v$ALACRITTY_VERSION.dmg"
  sha="$(shasum -a 256 "$dmg" | awk '{print $1}')"
  [[ $sha == "$ALACRITTY_SHA256" ]] || die "Alacritty checksum mismatch: expected $ALACRITTY_SHA256, got $sha"

  mkdir -p "$mnt"
  hdiutil attach "$dmg" -nobrowse -readonly -mountpoint "$mnt" >/dev/null
  if brew list --cask alacritty >/dev/null 2>&1; then
    brew uninstall --cask --force alacritty
  fi
  backup "$app"
  ditto "$mnt/Alacritty.app" "$app"
  hdiutil detach "$mnt" >/dev/null

  mkdir -p "$HOME/.terminfo/61"
  cp -f "$app/Contents/Resources/61/"{alacritty,alacritty-direct} "$HOME/.terminfo/61/"
  codesign --verify --deep --strict "$app"
  if xattr -p com.apple.quarantine "$app" >/dev/null 2>&1; then
    die "Alacritty unexpectedly has a quarantine attribute; refusing to bypass Gatekeeper."
  fi
}

install_macos() {
  if ! have brew; then
    echo "==> Installing Homebrew..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    for b in /opt/homebrew/bin/brew /usr/local/bin/brew; do
      [[ -x $b ]] || continue
      eval "$("$b" shellenv)"
      break
    done
  fi
  brew update

  install_python_macos
  echo "==> Installing CLI tools..."
  brew tap hashicorp/tap
  brew trust --formula hashicorp/tap/terraform
  brew install bash bash-completion@2 tmux neovim git curl btop kubectl lazygit ripgrep fd broot fzf navi node \
    basedpyright llvm tree-sitter-cli hashicorp/tap/terraform
  if brew list --formula tlrc >/dev/null 2>&1; then brew uninstall tlrc; fi
  brew upgrade bash || true

  echo "==> Installing Alacritty and JetBrainsMono Nerd Font..."
  install_alacritty_macos
  brew install --cask font-jetbrains-mono-nerd-font
}

install_macos
finish_setup Buttonless "$(brew --prefix llvm)/bin/clangd" "$(brew --prefix bash)/bin/bash" \
  'open -na "Alacritty" --args "$@"'
