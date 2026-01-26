_iterm2_layout() {
  local cur="${COMP_WORDS[COMP_CWORD]}"
  local commands="setup validate list show version"
  COMPREPLY=($(compgen -W "$commands" -- "$cur"))
}

complete -F _iterm2_layout iterm2-layout
