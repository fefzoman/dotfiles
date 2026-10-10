#!/usr/bin/env bash
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/base-common.sh"

NODE_MAJOR=22
[[ -r /etc/os-release ]] || die "Linux distribution cannot be identified."
. /etc/os-release
case "${ID:-}:${ID_LIKE:-}" in
  debian:*|ubuntu:*|*:debian*) ;;
  *) die "Supported Linux distributions: Debian and Ubuntu." ;;
esac

run_root() {
  if (( EUID == 0 )); then
    "$@"
  elif ! have sudo; then
    die "sudo is required to install system packages."
  elif [[ $DOTFILES_AUTO_APPROVE == 1 ]]; then
    sudo -n "$@"
  else
    sudo "$@"
  fi
}

apt_get() { run_root env DEBIAN_FRONTEND=noninteractive apt-get "$@"; }

gh_latest() {
  curl -fsSL "https://api.github.com/repos/$1/releases/latest" |
    sed -n 's/.*"tag_name": "v\([^"]*\)".*/\1/p' | head -n 1
}

# Usage: verify_sha <file> <sums file listing "hash  name">
verify_sha() {
  local expected
  expected="$(awk -v f="${1##*/}" '$2 == f { print $1 }' "$2")"
  [[ -n $expected ]] || die "Checksum for ${1##*/} is missing."
  printf '%s  %s\n' "$expected" "$1" | sha256sum --check --status
}

linux_arch() {
  case "$(uname -m)" in
    x86_64|amd64) echo x86_64 ;;
    arm64|aarch64) echo arm64 ;;
    *) die "Unsupported Linux architecture: $(uname -m)" ;;
  esac
}

install_python_linux() {
  save_python_packages
  if [[ ! -x $BIN/uv ]]; then
    echo "==> Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | env UV_UNMANAGED_INSTALL="$BIN" sh
  fi
  echo "==> Installing Python $PY_VERSION with uv..."
  install_uv_python "$BIN/uv"
  restore_python_packages
}

install_node_linux() {
  local arch version archive b
  arch="$(linux_arch)"
  [[ $arch == x86_64 ]] && arch=x64
  version="$(curl -fsSL https://nodejs.org/dist/index.tab |
    awk -v p="v$NODE_MAJOR." 'NR > 1 && index($1, p) == 1 { print $1; exit }')"
  [[ -n $version ]] || die "Cannot determine the latest Node $NODE_MAJOR version."
  archive="node-$version-linux-$arch.tar.xz"
  curl -fsSL -o "$WORK/$archive" "https://nodejs.org/dist/$version/$archive"
  curl -fsSL -o "$WORK/node-sums" "https://nodejs.org/dist/$version/SHASUMS256.txt"
  verify_sha "$WORK/$archive" "$WORK/node-sums"
  tar -xJf "$WORK/$archive" -C "$WORK"
  backup "$OPT/node"
  mv "$WORK/${archive%.tar.xz}" "$OPT/node"
  for b in node npm npx corepack; do
    [[ ! -x $OPT/node/bin/$b ]] || ln -sfn "$OPT/node/bin/$b" "$BIN/$b"
  done
}

install_neovim_linux() {
  local arch
  arch="$(linux_arch)"
  curl -fsSL "https://github.com/neovim/neovim/releases/latest/download/nvim-linux-$arch.tar.gz" | tar -xz -C "$WORK"
  backup "$OPT/nvim"
  mv "$WORK/nvim-linux-$arch" "$OPT/nvim"
  ln -sfn "$OPT/nvim/bin/nvim" "$BIN/nvim"
}

install_kubectl_linux() {
  local arch url
  arch="$(linux_arch)"
  [[ $arch == x86_64 ]] && arch=amd64
  url="https://dl.k8s.io/release/$(curl -fsSL https://dl.k8s.io/release/stable.txt)/bin/linux/$arch/kubectl"
  curl -fsSL -o "$WORK/kubectl" "$url"
  printf '%s  %s\n' "$(curl -fsSL "$url.sha256")" "$WORK/kubectl" | sha256sum --check --status
  install -m 0755 "$WORK/kubectl" "$BIN/kubectl"
}

install_terraform_linux() {
  local arch version url archive
  arch="$(linux_arch)"
  [[ $arch == x86_64 ]] && arch=amd64
  version="$(curl -fsSL https://checkpoint-api.hashicorp.com/v1/check/terraform |
    sed -n 's/.*"current_version":"\([^"]*\)".*/\1/p')"
  [[ -n $version ]] || die "Cannot determine the latest Terraform version."
  url="https://releases.hashicorp.com/terraform/$version"
  archive="terraform_${version}_linux_$arch.zip"
  curl -fsSL -o "$WORK/$archive" "$url/$archive"
  curl -fsSL -o "$WORK/terraform-sums" "$url/terraform_${version}_SHA256SUMS"
  verify_sha "$WORK/$archive" "$WORK/terraform-sums"
  unzip -oq "$WORK/$archive" -d "$BIN"
  chmod +x "$BIN/terraform"
}

install_lazygit_linux() {
  local version url archive
  version="$(gh_latest jesseduffield/lazygit)"
  [[ -n $version ]] || die "Cannot determine the latest LazyGit version."
  url="https://github.com/jesseduffield/lazygit/releases/download/v$version"
  archive="lazygit_${version}_linux_$(linux_arch).tar.gz"
  curl -fsSL -o "$WORK/$archive" "$url/$archive"
  curl -fsSL -o "$WORK/lazygit-sums" "$url/checksums.txt"
  verify_sha "$WORK/$archive" "$WORK/lazygit-sums"
  tar -xzf "$WORK/$archive" -C "$WORK" lazygit
  install -m 0755 "$WORK/lazygit" "$BIN/lazygit"
}

install_broot_linux() {
  local target=aarch64-unknown-linux-musl
  [[ $(linux_arch) != x86_64 ]] || target=x86_64-unknown-linux-musl
  curl -fsSL -o "$WORK/broot" "https://dystroy.org/broot/download/$target/broot"
  install -m 0755 "$WORK/broot" "$BIN/broot"
}

install_navi_linux() {
  local target=aarch64-unknown-linux-gnu version
  [[ $(linux_arch) != x86_64 ]] || target=x86_64-unknown-linux-musl
  version="$(gh_latest denisidoro/navi)"
  [[ -n $version ]] || die "Cannot determine the latest Navi version."
  curl -fsSL "https://github.com/denisidoro/navi/releases/download/v$version/navi-v$version-$target.tar.gz" |
    tar -xz -C "$WORK" navi
  install -m 0755 "$WORK/navi" "$BIN/navi"
}

install_nerd_font_linux() {
  local font_dir="$HOME/.local/share/fonts/JetBrainsMonoNerdFont"
  mkdir -p "$font_dir"
  curl -fsSL -o "$WORK/JetBrainsMono.zip" \
    https://github.com/ryanoasis/nerd-fonts/releases/latest/download/JetBrainsMono.zip
  unzip -oq "$WORK/JetBrainsMono.zip" -d "$font_dir"
  fc-cache -f "$font_dir"
}

install_linux() {
  echo "==> Installing Debian/Ubuntu packages..."
  apt_get update -y
  apt_get install -y alacritty bash build-essential ca-certificates clangd curl dconf-cli \
    fd-find fontconfig fzf git ripgrep tmux unzip wget xclip xz-utils
  apt_get install -y btop || true

  install_python_linux
  install_node_linux
  ln -sfn "$(command -v fdfind)" "$BIN/fd"
  install_neovim_linux
  install_kubectl_linux
  install_terraform_linux
  install_lazygit_linux
  install_broot_linux
  install_navi_linux
  npm install --global --prefix "$HOME/.local" tree-sitter-cli
  "$BIN/pip" install --upgrade basedpyright
  install_nerd_font_linux
}

install_linux
finish_setup Full "$(command -v clangd)" "$(command -v bash)" "exec \"$(command -v alacritty)\" \"\$@\""
