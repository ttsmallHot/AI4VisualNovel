#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
  read -r -s -p "DeepSeek API key: " DEEPSEEK_API_KEY
  printf '\n'
fi
if [[ -z "${DEEPSEEK_API_KEY:-}" ]]; then
  printf 'DeepSeek API key 不能为空。\n' >&2
  exit 2
fi

export TEXT_PROVIDER=openai
export OPENAI_BASE_URL=https://api.deepseek.com
export OPENAI_API_KEY="$DEEPSEEK_API_KEY"
export MODEL=deepseek-v4-flash
export DEEPSEEK_THINKING=disabled
export JSON_MAX_TOKENS=8192

python main.py \
  --mode evolve \
  --project campus_murder_node_goals_5 \
  --max-nodes 5 \
  --max-revisions 4 \
  --character-count 4 \
  --ending-mode closed \
  --requirements-file examples/campus_murder_5_nodes.txt

python -m pytest -q
python experiment/audit_rolling_story.py \
  data/campus_murder_node_goals_5/rolling_state.json
