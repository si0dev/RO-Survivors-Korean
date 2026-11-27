#!/usr/bin/env bash
# Only recover from explicitly recoverable Colab failures. A retry never
# bypasses provider quota/access refusal, or starts before verified cleanup.
recover_benchmark() {
  local attempts=0 stalled=0 previous=0 current=0 rc=0
  local max_sessions=6 deadline=$((SECONDS+7800))
  while true; do
    restore_checkpoint
    current=$(checkpoint_count)
    echo "COLAB_RECOVERY_RESTORED=$current/200"
    if [ "$current" = 200 ]; then
      echo "CHECKPOINT_COMPLETE_NO_GPU"
      return 0
    fi
    if [ "$attempts" -gt 0 ]; then
      if [ "$current" -lt "$previous" ]; then
        echo "COLAB_RECOVERY_CHECKPOINT_REGRESSION"
        return 1
      elif [ "$current" = "$previous" ]; then
        stalled=$((stalled+1))
      else
        stalled=0
      fi
      if [ "$stalled" -ge 2 ]; then
        echo "COLAB_RECOVERY_NO_PROGRESS"
        return 1
      fi
    fi
    if [ "$attempts" -ge "$max_sessions" ] || [ "$SECONDS" -ge "$deadline" ]; then
      echo "COLAB_RECOVERY_LIMIT_REACHED"
      return 1
    fi
    previous=$current
    attempts=$((attempts+1))
    echo "COLAB_RECOVERY_SESSION=$attempts/$max_sessions"
    run_session "$attempts" "$deadline"
    rc=$session_rc
    release_session
    if [ "$rc" = 0 ]; then
      restore_checkpoint
      [ "$(checkpoint_count)" = 200 ] || { echo "CHECKPOINT_INCOMPLETE"; return 1; }
      return 0
    fi
    if [ "$rc" != 75 ] && [ "$rc" != 124 ]; then
      echo "COLAB_RECOVERY_TERMINAL_EXIT=$rc"
      return "$rc"
    fi
    echo "COLAB_RECOVERY_RESTART_REQUIRED=$rc"
  done
}
