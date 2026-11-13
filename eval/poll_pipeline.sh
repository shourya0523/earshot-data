#!/usr/bin/env bash
# Poll every remote branch for docs/PIPELINE_READY.md; exit 0 with the branch name when found.
cd "$(dirname "$0")/.."
while true; do
  git fetch --quiet origin "+refs/heads/*:refs/remotes/origin/*" 2>/dev/null; git fetch --quiet data "+refs/heads/*:refs/remotes/data/*" 2>/dev/null
  for b in $(git for-each-ref --format='%(refname:short)' refs/remotes/origin refs/remotes/data); do
    if git cat-file -e "$b:docs/PIPELINE_READY.md" 2>/dev/null; then echo "READY on $b"; exit 0; fi
  done
  echo "$(date -u +%H:%M) not ready; branches: $(git for-each-ref --format='%(refname:short)' refs/remotes/origin | tr '\n' ' ')"
  git pull -q --rebase data claude/eager-volta-za1pmi 2>/dev/null; git push -q data claude/eager-volta-za1pmi 2>/dev/null && echo "push ok"
  sleep 1500
done
