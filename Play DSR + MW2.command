#!/bin/zsh
cd -- "${0:A:h}" || exit 1
/opt/homebrew/bin/python3 -B -m dsr_mw2.owner_test
status_code=$?
if (( status_code != 0 )); then
  print '\nThe private launcher has exited. Details are above.'
  if [[ -t 0 ]]; then
    read -r '?Press Return to close.'
  fi
fi
exit "$status_code"
