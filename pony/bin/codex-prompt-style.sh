#!/usr/bin/env bash

codex_prompt_glyph_for_personality() {
  case "${1:-}" in
    TIA|CELESTIA|PRINCESS|CELLY|SUNBUTT|PRINCESS_CELESTIA_SOL_INVICTUS) printf '%s\n' '☀︎' ;;
    TWI|TWILIGHT|TWILIGHT_SPARKLE) printf '%s\n' '✶' ;;
    AJ|APPLEJACK) printf '%s\n' '🍎' ;;
    PINKIE|PINKIE_PIE) printf '%s\n' '🎈' ;;
    SHY|FLUTTERS|FLUTTERSHY) printf '%s\n' '🦋' ;;
    RARES|RARITY) printf '%s\n' '💎' ;;
    DASH|RAINBOW|RAINBOW_DASH) printf '%s\n' '⚡' ;;
    SPIKE) printf '%s\n' '🐲' ;;
    *) return 1 ;;
  esac
}

codex_prompt_background_for_personality() {
  case "${1:-}" in
    TIA|CELESTIA|PRINCESS|CELLY|SUNBUTT|PRINCESS_CELESTIA_SOL_INVICTUS) printf '%s\n' '#FDF5B7' ;;
    TWI|TWILIGHT|TWILIGHT_SPARKLE) printf '%s\n' '#c79dd7' ;;
    AJ|APPLEJACK) printf '%s\n' '#fff4a3' ;;
    PINKIE|PINKIE_PIE) printf '%s\n' '#f0afd1' ;;
    SHY|FLUTTERS|FLUTTERSHY) printf '%s\n' '#fdf6af' ;;
    RARES|RARITY) printf '%s\n' '#e4e7ec' ;;
    DASH|RAINBOW|RAINBOW_DASH) printf '%s\n' '#9edbf9' ;;
    SPIKE) printf '%s\n' '#D5EBAD' ;;
    *) return 1 ;;
  esac
}