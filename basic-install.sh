#!/usr/bin/env bash
set -euo pipefail

export HOMEBREW_NO_REQUIRE_TAP_TRUST=1

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

TARGET_PYTHON_MAJOR=3
TARGET_PYTHON_MINOR=13
TARGET_PYTHON_FORMULA="python@${TARGET_PYTHON_MAJOR}.${TARGET_PYTHON_MINOR}"
FORCE_REMOVE_PYTHON=${FORCE_REMOVE_PYTHON:-0}

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

install_python_runtime() {
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

install_python_runtime

echo "==> Installing CLI tools..."
brew tap hashicorp/tap
brew install bash tmux neovim git curl btop codex kubectl lazygit ripgrep fd \
  basedpyright llvm rust-analyzer hashicorp/tap/terraform
brew upgrade bash || true

echo "==> Installing Alacritty and JetBrainsMono Nerd Font..."
brew install --cask --force alacritty
brew install --cask font-jetbrains-mono-nerd-font

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

cat > "${HOME}/.config/alacritty/alacritty.toml" <<ALACRITTY
[general]
import = ["~/.config/alacritty/themes/themes/gruvbox_dark.toml"]

[window]
decorations = "Buttonless"
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
thickness = 0.45
unfocused_hollow = false

[terminal]
shell = { program = "${TMUX_BIN}", args = ["new-session", "-A", "-s", "main"] }
ALACRITTY

echo "==> Setting Alacritty as main terminal helper..."

mkdir -p "${HOME}/.local/bin"
ln -sf "$(brew --prefix llvm)/bin/clangd" "${HOME}/.local/bin/clangd"

cat > "${HOME}/.local/bin/alacritty" <<'ALACRITTY_WRAPPER'
#!/usr/bin/env bash
open -na "Alacritty" --args "$@"
ALACRITTY_WRAPPER

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

call plug#end()

let mapleader = " "
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
    vim.keymap.set('i', '<S-Tab>', completion_key('<C-p>', '<C-x><C-o>'), insert_opts)
    vim.keymap.set('i', '<Down>', completion_key('<C-n>', '<Down>'), insert_opts)
    vim.keymap.set('i', '<Up>', completion_key('<C-p>', '<Up>'), insert_opts)
    vim.keymap.set('i', '<CR>', completion_key('<C-y>', '<CR>'), insert_opts)
  end,
})

local servers = { 'basedpyright', 'clangd', 'rust_analyzer' }
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

echo "==> Writing tmux config to ~/.tmux.conf ..."
backup_file "${HOME}/.tmux.conf"

cat > "${HOME}/.tmux.conf" <<'TMUXCONF'
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
