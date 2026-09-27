#!/usr/bin/env bash
# Reproduction of the SIGPIPE assertion class (#537, fixed by #660) -- and the threshold that
# decides which sites can actually flip.
#
# THE MECHANISM. `tools/state/oc-ledger:140` sets `set -o pipefail`, while the selftest asserted with
# `printf '%s' "$out" | grep -q PAT`. `grep -q` exits at the FIRST match; `printf` still has bytes to
# write, takes SIGPIPE, and `pipefail` returns the PIPELINE non-zero DESPITE the match -- so a leg
# reports FAIL on a payload that visibly contains the pattern.
#
# THE CONTROLLING VARIABLE IS PAYLOAD SIZE, NOT MATCH POSITION. Two conditions are both necessary:
# the match must be early (so grep exits while printf is still writing) AND the payload must exceed
# what printf can hand to the pipe before grep is scheduled. That size is the kernel's 64 KiB pipe
# buffer. Below it printf completes in one write and SIGPIPE cannot fire; above it printf blocks on a
# full pipe and the failure becomes certain. Measured 2026-09-27, pattern first, 60 trials per row,
# TWO runs shown because the per-row RATE is load-dependent while the SHAPE is not:
#
#     payload     pipeline form (run 1 / run 2)      here-string form (both runs)
#      8 KiB       0/60        0/60   clean            0/60
#     32 KiB       0/60        2/60   clean-to-trace   0/60
#     56 KiB       7/60        4/60   probabilistic    0/60
#     64 KiB      33/60       48/60   probabilistic    0/60
#     72 KiB      36/60       36/60   probabilistic    0/60
#    128 KiB      60/60       60/60   DETERMINISTIC    0/60
#
# Quote the SHAPE and the BOUNDARY, never a single row's rate: the same script on the same box gave
# 1/60, 11/60, 2/60 and 48/60 for the same payload at different instants. The here-string form is
# 0/60 in every run -- that contrast, not any magnitude, is what identifies the class.
#
# WHICH SITES ARE AT RISK follows from that: a site whose payload is a few lines of tool output
# cannot flip today, however wrong its form -- the four reintroduced sites in `oc-ledger` (see
# 2026-09-27-review-rotation-donor-migration.md) sit there. A site whose payload is a corpus-wide
# linter's accumulated output CAN exceed the buffer, and `tools/audit/oc-lint-laws:179,180` pipes
# exactly that. So the form is worth removing on its own merits, and the threshold tells you the
# ORDER to remove it in.
#
# Usage:  bash 2026-09-27-sigpipe-repro.sh            # sweep the threshold (default, 60 trials/row)
#         bash 2026-09-27-sigpipe-repro.sh 60 64      # one row: TRIALS KiB

set -o pipefail                      # the guard under test; the defect needs BOTH this and a pipe
TRIALS="${1:-60}"
ONLY_KB="${2:-}"

# Build a payload of exactly SIZE bytes in-shell: the pattern FIRST, then filler. Built in-shell
# rather than passed as an argument: an earlier probe of this class passed the payload as an argv
# element and its 256 KiB row died with `OSError: [Errno 7] Argument list too long` -- an instrument
# limit of THAT harness, not a property of the defect, and this script avoids it by construction.
make_payload() {
  local size=$1
  printf 'TARGET_PATTERN_HERE\n'
  head -c "$(( size - 21 ))" /dev/zero | tr '\0' 'x'
  printf '\n'
}

run_row() {
  local kb=$1 bytes pipe_fail=0 hs_fail=0 i payload
  bytes=$(( kb * 1024 ))
  payload="$(make_payload "$bytes")"
  for (( i = 0; i < TRIALS; i++ )); do
    # The DEFECTIVE form, as it appeared in the donor's selftest.
    printf '%s' "$payload" | grep -q 'TARGET_PATTERN_HERE' || pipe_fail=$(( pipe_fail + 1 ))
    # The FIXED form, #660's replacement -- same pattern, same payload, no pipe.
    grep -q 'TARGET_PATTERN_HERE' <<< "$payload" || hs_fail=$(( hs_fail + 1 ))
  done
  local verdict
  if   (( pipe_fail == 0 ));      then verdict="clean (cannot flip at this size)"
  elif (( pipe_fail == TRIALS )); then verdict="DETERMINISTIC (every trial flips)"
  else                                 verdict="probabilistic"
  fi
  printf 'payload=%5s KiB  pipeline_form %2d/%d  here_string_form %2d/%d  %s\n' \
    "$kb" "$pipe_fail" "$TRIALS" "$hs_fail" "$TRIALS" "$verdict"
  if (( hs_fail != 0 )); then
    printf '  !! the here-string form failed too -- investigate before citing this run\n'
  fi
}

echo "instant_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)  shell=$BASH_VERSION  trials_per_row=$TRIALS"
echo "pipe_buffer=65536 bytes (kernel default; /proc/sys/fs/pipe-max-size=$(cat /proc/sys/fs/pipe-max-size 2>/dev/null || echo '?'))"
if [ -n "$ONLY_KB" ]; then
  run_row "$ONLY_KB"
else
  for kb in 8 32 56 64 72 128; do run_row "$kb"; done
fi
