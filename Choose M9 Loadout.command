#!/bin/zsh
cd -- "${0:A:h}" || exit 1
python3 -B -m dsr_mw2.choose_loadout
result=$?
if [[ -t 0 ]]; then
  read -r '?Press Return to close. '
fi
exit "$result"
