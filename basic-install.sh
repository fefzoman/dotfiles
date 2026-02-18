#!/usr/bin/env bash
set -euo pipefail

echo "==> Installing Homebrew (if missing)..."
if ! command -v brew >/dev/null 2>&1; then
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

  # Make brew available in this shell session (Apple Silicon vs Intel)
  if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [[ -x /usr/local/bin/brew ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
fi

echo "==> Updating Homebrew..."
brew update

echo "==> Installing tmux, neovim, git, curl..."
brew install tmux neovim git curl

echo "==> Installing vim-plug for Neovim..."
curl -fLo "${HOME}/.local/share/nvim/site/autoload/plug.vim" --create-dirs \
  https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim

echo "==> Writing Neovim config to ~/.config/nvim/init.vim ..."
mkdir -p "${HOME}/.config/nvim"

# Backup existing config if present
if [[ -f "${HOME}/.config/nvim/init.vim" ]]; then
  cp "${HOME}/.config/nvim/init.vim" "${HOME}/.config/nvim/init.vim.bak.$(date +%Y%m%d%H%M%S)"
fi

cat > "${HOME}/.config/nvim/init.vim" <<'VIMRC'
" ===== Basic settings (as requested) =====
set mouse=a
set number
set smarttab
set tabstop=2
set shiftwidth=2
set softtabstop=2
set autoindent

set termguicolors
syntax on

" ===== Plugins (vim-plug) =====
call plug#begin('~/.local/share/nvim/plugged')

Plug 'vim-airline/vim-airline'
Plug 'ashfinal/vim-colors-violet'
Plug 'preservim/nerdtree'
Plug 'ryanoasis/vim-devicons'

call plug#end()

" ===== Theme =====
if !empty(globpath(&rtp, 'colors/violet.vim'))
  colorscheme violet
endif
VIMRC

echo "==> Installing Neovim plugins (headless)..."
nvim --headless +'PlugInstall --sync' +qa

echo "==> Writing tmux config to ~/.tmux.conf ..."

# Backup existing tmux config if present
if [[ -f "${HOME}/.tmux.conf" ]]; then
  cp "${HOME}/.tmux.conf" "${HOME}/.tmux.conf.bak.$(date +%Y%m%d%H%M%S)"
fi

cat > "${HOME}/.tmux.conf" <<'TMUXCONF'
# ===== Windows on top (status bar at top) =====
set -g status-position top

# ===== Window numbering starts at 1 =====
set -g base-index 1
setw -g pane-base-index 1
set -g renumber-windows on

set -g mouse on

# ===== Remove green background color =====
# Force a neutral look for the status bar (no bright green).
set -g status-style "bg=default,fg=white"
setw -g window-status-style "bg=default,fg=white"
setw -g window-status-current-style "bg=default,fg=cyan"

# (Optional) make messages consistent too
set -g message-style "bg=default,fg=white"

# Vertical split (left/right) -> Prefix + ,
unbind '"'
bind , split-window -h

# Horizontal split (top/bottom) -> Prefix + .
unbind %
bind . split-window -v
TMUXCONF

echo ""
echo "✅ Done."
echo "To apply tmux config immediately in an existing tmux session, run:"
echo "  tmux source-file ~/.tmux.conf"
echo "Or restart tmux."

echo "Install the Codex CLI with Homebrew."
brew install codex
echo "✅ Done."

echo "Install the btop with Homebrew."
brew install btop
echo "✅ Done."
