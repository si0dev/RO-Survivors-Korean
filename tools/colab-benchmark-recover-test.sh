#!/usr/bin/env bash
set -euo pipefail
source "$(dirname "$0")/colab-benchmark-recover.sh"
# Execute the actual recovery function with mock session and storage callbacks.
scenario_run() {
  scenario=$1
  saved=58 allocations=0 releases=0 active=0 session_rc=0
  restore_checkpoint() { [ "$active" = 0 ]; }
  checkpoint_count() { echo "$saved"; }
  run_session() {
    [ "$active" = 0 ]; active=1; allocations=$((allocations+1))
    case "$scenario" in
      progress) saved=$((saved+50)); if [ "$saved" -ge 200 ]; then saved=200; session_rc=0; else session_rc=75; fi ;;
      stall) session_rc=75 ;;
      quota) session_rc=1 ;;
      ceiling) saved=$((saved+1)); session_rc=75 ;;
      complete) exit 99 ;;
      cleanup_fail) session_rc=75 ;;
    esac
  }
  release_session() {
    [ "$active" = 1 ]
    if [ "$scenario" = cleanup_fail ]; then return 9; fi
    active=0; releases=$((releases+1))
  }
  expected=0
  case "$scenario" in stall|quota|ceiling) expected=1;; cleanup_fail) expected=9;; complete) saved=200;; esac
  verify() {
    local rc=$?
    trap - EXIT
    [ "$rc" = "$expected" ] || exit 90
    if [ "$scenario" = cleanup_fail ]; then
      [ "$allocations" = 1 ] && [ "$active" = 1 ] || exit 91
      exit 0
    fi
    [ "$active" = 0 ] && [ "$allocations" = "$releases" ] || exit 91
    case "$scenario" in
      progress) [ "$saved" = 200 ] && [ "$allocations" = 3 ] || exit 92 ;;
      stall) [ "$allocations" = 2 ] || exit 93 ;;
      quota) [ "$allocations" = 1 ] || exit 94 ;;
      ceiling) [ "$allocations" = 6 ] || exit 95 ;;
      complete) [ "$allocations" = 0 ] || exit 96 ;;
    esac
    exit 0
  }
  trap verify EXIT
  recover_benchmark
}
if [ "$#" = 1 ]; then scenario_run "$1"; exit; fi
for scenario in progress stall quota ceiling complete cleanup_fail; do
  bash "$0" "$scenario"
  echo "RECOVERY_TEST_PASS=$scenario"
done
