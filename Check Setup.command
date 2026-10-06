#!/bin/zsh
set -u
task_dir="${0:A:h}"
cd -- "$task_dir" || exit 1
python3 -B -m dsr_mw2.doctor
check_result=$?
print ""
print "Use Play DSR + MW2.command for the current owner test. Its M9 armory is inside the game."
if [[ -t 0 ]]; then
  read -r "?Press Return to close this setup check. "
fi
exit "$check_result"
