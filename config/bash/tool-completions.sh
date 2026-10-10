#! bash oh-my-bash.module
#
# Extra completions for cloud, Terraform, Kubernetes, and Python tooling.
#

if declare -F _omb_module_require_completion >/dev/null 2>&1; then
  _omb_module_require_completion awscli terraform kubectl helm minikube pip pip3 uv
fi
