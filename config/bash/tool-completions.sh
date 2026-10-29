#! bash oh-my-bash.module

if [[ -r /opt/homebrew/etc/profile.d/bash_completion.sh ]]; then
  source /opt/homebrew/etc/profile.d/bash_completion.sh
elif [[ -r /usr/local/etc/profile.d/bash_completion.sh ]]; then
  source /usr/local/etc/profile.d/bash_completion.sh
fi

if declare -F _omb_module_require_completion >/dev/null 2>&1; then
  _omb_module_require_completion docker docker-compose awscli terraform kubectl helm minikube pip pip3 uv
fi
