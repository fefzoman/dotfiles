#!/usr/bin/env bash
set -euo pipefail

echo "==> Installing Homebrew if missing..."
if ! command -v brew >/dev/null 2>&1; then
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

  # Make brew available in this shell session: Apple Silicon vs Intel
  if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [[ -x /usr/local/bin/brew ]]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
fi

echo "==> Updating Homebrew..."
brew update

echo "==> Installing CLI tools..."
brew install tmux neovim git curl btop codex

echo "==> Installing Terraform..."
brew tap hashicorp/tap
brew install hashicorp/tap/terraform

echo "==> Installing Alacritty..."
brew install --cask --force alacritty

echo "==> Installing Lazygit ..."
brew install lazygit ripgrep fd

echo "==> Installing JetBrainsMono Nerd Font..."
brew install --cask font-jetbrains-mono-nerd-font

echo "==> Setting up Alacritty theme files..."
mkdir -p "${HOME}/.config/alacritty"

if [[ ! -d "${HOME}/.config/alacritty/themes" ]]; then
  git clone https://github.com/alacritty/alacritty-theme "${HOME}/.config/alacritty/themes"
else
  git -C "${HOME}/.config/alacritty/themes" pull --ff-only || true
fi

echo "==> Writing Alacritty config to ~/.config/alacritty/alacritty.toml ..."

if [[ -f "${HOME}/.config/alacritty/alacritty.toml" ]]; then
  cp "${HOME}/.config/alacritty/alacritty.toml" "${HOME}/.config/alacritty/alacritty.toml.bak.$(date +%Y%m%d%H%M%S)"
fi

TMUX_BIN="$(command -v tmux)"

if [[ -z "${TMUX_BIN}" ]]; then
  echo "tmux was not found. Install tmux first."
  exit 1
fi

cat > "${HOME}/.config/alacritty/alacritty.toml" <<ALACRITTY
[general]
import = [
  "~/.config/alacritty/themes/themes/gruvbox_dark.toml"
]

[window]
decorations = "Buttonless"
padding = { x = 10, y = 10 }

[font]
size = 16

[colors.primary]
foreground = "#BAB7AD"

[font.normal]
family = "JetBrainsMono Nerd Font"

[cursor]
style = "Beam"
thickness = 0.45

[terminal]
shell = { program = "${TMUX_BIN}", args = ["new-session", "-A", "-s", "main"] }
ALACRITTY

echo "==> Setting Alacritty as main terminal helper..."

mkdir -p "${HOME}/.local/bin"

cat > "${HOME}/.local/bin/alacritty" <<'ALACRITTY_WRAPPER'
#!/usr/bin/env bash
open -na "Alacritty" --args "$@"
ALACRITTY_WRAPPER

chmod +x "${HOME}/.local/bin/alacritty"

# Prefer zsh on macOS, but fall back safely.
if [[ -n "${ZSH_VERSION:-}" ]] || [[ "${SHELL:-}" == */zsh ]]; then
  SHELL_RC="${HOME}/.zshrc"
else
  SHELL_RC="${HOME}/.bashrc"
fi

touch "${SHELL_RC}"

if ! grep -q "BEGIN MAIN TERMINAL SETUP" "${SHELL_RC}"; then
  cat >> "${SHELL_RC}" <<'SHELLCONFIG'

# BEGIN MAIN TERMINAL SETUP
export PATH="$HOME/.local/bin:$PATH"
export TERMINAL="alacritty"

alias term="alacritty"
alias terminal="alacritty"
alias alac="alacritty"
# END MAIN TERMINAL SETUP
SHELLCONFIG
fi

echo "==> Installing vim-plug for Neovim..."
curl -fLo "${HOME}/.local/share/nvim/site/autoload/plug.vim" --create-dirs \
  https://raw.githubusercontent.com/junegunn/vim-plug/master/plug.vim

echo "==> Writing Neovim config to ~/.config/nvim/init.vim ..."
mkdir -p "${HOME}/.config/nvim"

if [[ -f "${HOME}/.config/nvim/init.vim" ]]; then
  cp "${HOME}/.config/nvim/init.vim" "${HOME}/.config/nvim/init.vim.bak.$(date +%Y%m%d%H%M%S)"
fi

cat > "${HOME}/.config/nvim/init.vim" <<'VIMRC'
" ===== Basic settings =====
set mouse=a
set number
set smarttab
set tabstop=2
set shiftwidth=2
set softtabstop=2
set autoindent

set termguicolors
syntax on

" ===== Plugins =====
call plug#begin('~/.local/share/nvim/plugged')

Plug 'vim-airline/vim-airline'
Plug 'ashfinal/vim-colors-violet'
Plug 'ryanoasis/vim-devicons'

" = Telescope =
Plug 'nvim-lua/plenary.nvim'
Plug 'nvim-telescope/telescope.nvim', { 'tag': '*' }

" = LazyGit inside Neovim =
Plug 'kdheepak/lazygit.nvim'

" = Neo-tree =
Plug 'MunifTanjim/nui.nvim'
Plug 'nvim-tree/nvim-web-devicons'
Plug 'nvim-neo-tree/neo-tree.nvim', { 'branch': 'v3.x' }

call plug#end()

let mapleader = " "

" ===== Telescope / Neo-tree / LazyGit config =====
lua << EOF
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
EOF

" ===== Neo-tree keymap =====
nnoremap <leader>e :Neotree toggle<CR>

" ===== LazyGit keymap =====
nnoremap <leader>lg :LazyGit<CR>

" ===== Theme =====
if !empty(globpath(&rtp, 'colors/violet.vim'))
  colorscheme violet
endif
VIMRC

echo "==> Installing Neovim plugins headlessly..."
nvim --headless +'PlugInstall --sync' +qa

echo "==> Writing tmux config to ~/.tmux.conf ..."

if [[ -f "${HOME}/.tmux.conf" ]]; then
  cp "${HOME}/.tmux.conf" "${HOME}/.tmux.conf.bak.$(date +%Y%m%d%H%M%S)"
fi

cat > "${HOME}/.tmux.conf" <<'TMUXCONF'
# ===== Windows on top =====
set -g status-position top

# ===== Window numbering starts at 1 =====
set -g base-index 1
setw -g pane-base-index 1
set -g renumber-windows on

set -g mouse on

# ===== Neutral status bar =====
set -g status-style "bg=default,fg=white"
setw -g window-status-style "bg=default,fg=white"
setw -g window-status-current-style "bg=default,fg=cyan"
set -g message-style "bg=default,fg=white"
set -g status-right ""

# Vertical split: Prefix + ,
unbind '"'
bind , split-window -h

# Horizontal split: Prefix + .
unbind %
bind . split-window -v
TMUXCONF

echo ""
echo "✅ Done."
echo ""
echo "Restart your shell or run:"
echo "  source ${SHELL_RC}"
echo ""
echo "Open Alacritty with:"
echo "  alacritty"
echo ""
echo "To apply tmux config immediately in an existing tmux session, run:"
echo "  tmux source-file ~/.tmux.conf"
