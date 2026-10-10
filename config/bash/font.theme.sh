#! bash oh-my-bash.module
#
# Minimal two-line variant of the built-in font theme.
# Keeps timestamp, user, host, and path on the first line.
# Places only the prompt arrow on its own line.

CLOCK_THEME_PROMPT_PREFIX=''
CLOCK_THEME_PROMPT_SUFFIX=' '
THEME_SHOW_CLOCK=${THEME_SHOW_CLOCK:-"true"}
THEME_CLOCK_COLOR=${THEME_CLOCK_COLOR:-"$_omb_prompt_gray"}
THEME_CLOCK_FORMAT=${THEME_CLOCK_FORMAT:-"%I:%M:%S"}
OMB_PROMPT_VIRTUALENV_FORMAT='(%s) '
OMB_PROMPT_SHOW_PYTHON_VENV=${OMB_PROMPT_SHOW_PYTHON_VENV:=true}

function _omb_theme_git_branch_suffix() {
  local branch

  if ! command -v git >/dev/null 2>&1; then
    return
  fi

  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    return
  fi

  branch="$(git symbolic-ref --quiet --short HEAD 2>/dev/null || git rev-parse --short HEAD 2>/dev/null || true)"

  if [[ -n "$branch" ]]; then
    printf '%s' "$branch"
  fi
}

function _omb_theme_PROMPT_COMMAND() {
  local RC="$?"
  local hostname="${_omb_prompt_gray}\u@\h"
  local python_venv
  _omb_prompt_get_python_venv python_venv=$_omb_prompt_white$python_venv
  local git_branch
  git_branch="$(_omb_theme_git_branch_suffix)"
  if [[ -n "$git_branch" ]]; then
    git_branch=" \[\e[38;5;240m\] ${git_branch}\[\e[0m\]"
  fi
  local ret_status

  if [[ ${RC} == 0 ]]; then
    ret_status="${_omb_prompt_gray}❯"
  else
    ret_status="${_omb_prompt_brown}❯"
  fi

  history -a
  # Keep the prompt and command output thin, but type commands at medium weight.
  PS1="$(clock_prompt)$python_venv${hostname} ${_omb_prompt_teal}\W${git_branch}\n${ret_status} ${_omb_prompt_normal}\[\e[1m\]"
  PS0='\[\e[0m\]'
}

_omb_util_add_prompt_command _omb_theme_PROMPT_COMMAND
