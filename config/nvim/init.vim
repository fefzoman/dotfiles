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
