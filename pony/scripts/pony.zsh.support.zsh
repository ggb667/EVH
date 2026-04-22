[[ -x ./pony/bin/codex-pony ]] || return 0

pony_project_root() {
  if git -C "${AGENIC_PROJECT_ROOT:-$PWD}" rev-parse --show-toplevel >/dev/null 2>&1; then
    git -C "${AGENIC_PROJECT_ROOT:-$PWD}" rev-parse --show-toplevel
  else
    printf '%s\n' "${AGENIC_PROJECT_ROOT:-$PWD}"
  fi
}

AGENIC_PROJECT_ROOT="$(pony_project_root)"
AGENIC_PROJECT_PONY_DIR="$AGENIC_PROJECT_ROOT/pony"
AGENIC_PROJECT_PONY_RUNTIME_DIR="$AGENIC_PROJECT_PONY_DIR/runtime"
AGENIC_PROJECT_PONY_RUNTIME_DRAFT_PATH="$AGENIC_PROJECT_PONY_RUNTIME_DIR/user.draft"
AGENIC_PROJECT_PONY_RUNTIME_PENDING_NOTICE_PATH="$AGENIC_PROJECT_PONY_RUNTIME_DIR/pending.notice"
AGENIC_PROJECT_PONY_RUNTIME_PENDING_NOTICE_SEEN_PATH="$AGENIC_PROJECT_PONY_RUNTIME_DIR/pending.notice.seen"

pony_prompt_reload() {
  command -v p10k >/dev/null 2>&1 || return 0
  p10k reload >/dev/null 2>&1 || true
}

twilight()   { export PERSONALITY=TWILIGHT_SPARKLE; pony_prompt_reload; }
twi()        { export PERSONALITY=TWILIGHT_SPARKLE; pony_prompt_reload; }
celestia()   { export PERSONALITY=PRINCESS_CELESTIA_SOL_INVICTUS; pony_prompt_reload; }
princess()   { export PERSONALITY=PRINCESS_CELESTIA_SOL_INVICTUS; pony_prompt_reload; }
tia()        { export PERSONALITY=PRINCESS_CELESTIA_SOL_INVICTUS; pony_prompt_reload; }
celly()      { export PERSONALITY=PRINCESS_CELESTIA_SOL_INVICTUS; pony_prompt_reload; }
sunbutt()    { export PERSONALITY=PRINCESS_CELESTIA_SOL_INVICTUS; pony_prompt_reload; }
sol()        { export PERSONALITY=PRINCESS_CELESTIA_SOL_INVICTUS; pony_prompt_reload; }
rainbow()    { export PERSONALITY=RAINBOW_DASH; pony_prompt_reload; }
rd()         { export PERSONALITY=RAINBOW_DASH; pony_prompt_reload; }
dash()       { export PERSONALITY=RAINBOW_DASH; pony_prompt_reload; }
dashie()     { export PERSONALITY=RAINBOW_DASH; pony_prompt_reload; }
pinkie()     { export PERSONALITY=PINKIE_PIE; pony_prompt_reload; }
rarity()     { export PERSONALITY=RARITY; pony_prompt_reload; }
rares()      { export PERSONALITY=RARITY; pony_prompt_reload; }
applejack()  { export PERSONALITY=APPLEJACK; pony_prompt_reload; }
aj()         { export PERSONALITY=APPLEJACK; pony_prompt_reload; }
shy()        { export PERSONALITY=FLUTTERSHY; pony_prompt_reload; }
fluttershy() { export PERSONALITY=FLUTTERSHY; pony_prompt_reload; }
flutters()   { export PERSONALITY=FLUTTERSHY; pony_prompt_reload; }
spike()      { export PERSONALITY=SPIKE; pony_prompt_reload; }
w()          { export WORKING_ON="$1"; pony_prompt_reload; }
clearwork()  { unset WORKING_ON; pony_prompt_reload; }
clearpony()  { unset PERSONALITY; pony_prompt_reload; }
clearrole()  { unset PERSONALITY WORKING_ON; pony_prompt_reload; }
codexpony()  { ./pony/bin/codex-pony "$@"; }
ponyruntime() { ./pony/scripts/queue-runtime.sh "$@"; }
ponyqueue()  { ./pony/scripts/queue-runtime.sh list; }
ponycontinue() {
  local next_id
  next_id="$(./pony/scripts/queue-runtime.sh next)"
  [[ -n "$next_id" ]] || return 0
  codexpony "$(./pony/scripts/queue-runtime.sh active-prompt)"
  local exit_code=$?
  if [[ $exit_code -eq 0 ]]; then
    ./pony/scripts/queue-runtime.sh pop "$next_id"
    ./pony/scripts/queue-runtime.sh complete
  fi
  return $exit_code
}

if [[ -o interactive ]]; then
  autoload -Uz add-zsh-hook

  pony_runtime_sync_notice() {
    ./pony/scripts/queue-runtime.sh init >/dev/null 2>&1 || return 0
    ./pony/scripts/queue-runtime.sh pending-notice >/dev/null 2>&1 || true
    if [[ -s "$AGENIC_PROJECT_PONY_RUNTIME_PENDING_NOTICE_PATH" ]] && ! cmp -s "$AGENIC_PROJECT_PONY_RUNTIME_PENDING_NOTICE_PATH" "$AGENIC_PROJECT_PONY_RUNTIME_PENDING_NOTICE_SEEN_PATH"; then
      printf '\n%s\n' "$(<"$AGENIC_PROJECT_PONY_RUNTIME_PENDING_NOTICE_PATH")"
      cat "$AGENIC_PROJECT_PONY_RUNTIME_PENDING_NOTICE_PATH" > "$AGENIC_PROJECT_PONY_RUNTIME_PENDING_NOTICE_SEEN_PATH"
    fi
  }

  pony_runtime_draft_restore() {
    [[ -o zle ]] || return 0
    if [[ -z "$BUFFER" && -s "$AGENIC_PROJECT_PONY_RUNTIME_DRAFT_PATH" ]]; then
      BUFFER="$(<"$AGENIC_PROJECT_PONY_RUNTIME_DRAFT_PATH")"
      CURSOR=${#BUFFER}
    fi
  }

  pony_runtime_draft_save() {
    [[ -o zle ]] || return 0
    printf '%s' "$BUFFER" >| "$AGENIC_PROJECT_PONY_RUNTIME_DRAFT_PATH"
  }

  pony_runtime_draft_clear_submitted() {
    : >| "$AGENIC_PROJECT_PONY_RUNTIME_DRAFT_PATH"
  }

  add-zsh-hook precmd pony_runtime_sync_notice
  add-zsh-hook preexec pony_runtime_draft_clear_submitted
  zle -N zle-line-init pony_runtime_draft_restore
  zle -N zle-line-finish pony_runtime_draft_save
fi
