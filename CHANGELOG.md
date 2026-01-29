## [3.0.1](https://github.com/terrylica/iterm2-scripts/compare/v3.0.0...v3.0.1) (2026-01-29)


### Bug Fixes

* **setup:** mark swiftdialog and broot as required dependencies ([72f4c56](https://github.com/terrylica/iterm2-scripts/commit/72f4c5609b490fbd39dea44e11771f64830616c6))

# [3.0.0](https://github.com/terrylica/iterm2-scripts/compare/v2.2.0...v3.0.0) (2026-01-29)


### Features

* **launcher:** rename to workspace-launcher with migration support ([52ede81](https://github.com/terrylica/iterm2-scripts/commit/52ede812ec76acd064aaf40264664b190d129eb4))


### BREAKING CHANGES

* **launcher:** Configuration paths and file naming have changed:
- Output: default-layout.py → workspace-launcher.py
- Config dir: ~/.config/iterm2/ → ~/.config/workspace-launcher/
- Layout files: layout-*.toml → workspace-*.toml
- Preferences: selector-preferences.toml → preferences.toml

Features:
- Add migration wizard for existing users (auto-detects legacy config)
- Original files preserved as backup during migration
- All UI text updated to use "workspace" terminology

Updates:
- Dialog titles: "Select Layout" → "Select Workspace"
- "Manage Layouts" → "Manage Workspaces"
- Documentation updated with new architecture

SRED-Type: support-work
SRED-Claim: WORKSPACE-LAUNCHER

# [2.2.0](https://github.com/terrylica/iterm2-scripts/compare/v2.1.1...v2.2.0) (2026-01-29)


### Features

* **dialogs:** use regular-size switch toggles and add maintenance utilities ([7301fca](https://github.com/terrylica/iterm2-scripts/commit/7301fca5d36d62e52c7e45df37a6f2a656345e65))

## [2.1.1](https://github.com/terrylica/iterm2-scripts/compare/v2.1.0...v2.1.1) (2026-01-29)


### Bug Fixes

* **privacy:** sanitize private project names from public source ([5d96c96](https://github.com/terrylica/iterm2-scripts/commit/5d96c96c39e7b19b624c028dbd9ee7b7f7a260f6))

# [2.1.0](https://github.com/terrylica/iterm2-scripts/compare/v2.0.2...v2.1.0) (2026-01-28)


### Features

* **dialogs:** improve rename dialog layout and add bidirectional pagination ([87cea59](https://github.com/terrylica/iterm2-scripts/commit/87cea597737ac992a1440ba2bbde60437710c481))

## [2.0.2](https://github.com/terrylica/iterm2-scripts/compare/v2.0.1...v2.0.2) (2026-01-28)


### Bug Fixes

* **bin:** add PATH augmentation and worktree support to iterm-open ([14fb958](https://github.com/terrylica/iterm2-scripts/commit/14fb9589da32e08497dc23ea0de2adfab79a420f))

## [2.0.1](https://github.com/terrylica/iterm2-scripts/compare/v2.0.0...v2.0.1) (2026-01-28)


### Bug Fixes

* **dialogs:** integrate category-based rename flow ([31233da](https://github.com/terrylica/iterm2-scripts/commit/31233da920991fcf867f0c26f23054af0859c776))

# [2.0.0](https://github.com/terrylica/iterm2-scripts/compare/v1.1.0...v2.0.0) (2026-01-28)


### Features

* **dialogs:** add category-based rename with custom tab names ([3d56a2c](https://github.com/terrylica/iterm2-scripts/commit/3d56a2c689be9e88f5d766e40d340149f2922664))


### BREAKING CHANGES

* **dialogs:** Rename dialog now uses category-based flow

- Extract SwiftDialog utilities to new src/swiftdialog.py module
  - find_swiftdialog_path(), is_swiftdialog_available()
  - run_swiftdialog(), format_tab_label()
  - CATEGORY_ICONS dict for SF Symbol definitions

- Add show_category_selector_dialog() for category selection
  - Uses checkbox with switch style (single-select semantics)
  - Shows item counts per category with colored icons
  - Auto-sizes height based on content

- Refactor show_rename_tabs_dialog() for category filtering
  - Accept optional category_name parameter
  - Auto-size height (omit height param for SwiftDialog auto-calc)
  - Remove search/filter field (categories sufficient)

- Add custom_tab_names persistence to preferences
  - Store path -> shorthand mappings in TOML
  - Load/save via preferences.py

- Update main.py with save callback for rename flow
  - Pass custom_tab_names and callback to show_tab_customization()

- Fix truncated panes.py (missing error_type and return)
- Fix main.py orphaned code from bad module split
- Fix type hints: callable -> Callable

- Add mise.toml for task orchestration
  - build, lint, validate, release tasks
  - test:aliases, test:dialog utilities

SRED-Type: experimental-development
SRED-Claim: ITERM2-SCRIPTS

# [1.1.0](https://github.com/terrylica/iterm2-scripts/compare/v1.0.0...v1.1.0) (2026-01-27)


### Bug Fixes

* **bin:** use portable paths in iterm-open script ([17da4e2](https://github.com/terrylica/iterm2-scripts/commit/17da4e230eb1c690b72a87a874650ef3a75aa070))


### Features

* **dialogs:** add SF Symbol colored icons to tab customization ([01c4ee3](https://github.com/terrylica/iterm2-scripts/commit/01c4ee386ad20bfb202ec085c6b8b81159ef4b71))

# 1.0.0 (2026-01-26)


### Features

* initial iTerm2 automation repository scaffolding ([566c8ad](https://github.com/terrylica/iterm2-scripts/commit/566c8ad304edda09a90591c443c0c37bba90ef09))
* **modularization:** modular source with build concatenation ([3d950b3](https://github.com/terrylica/iterm2-scripts/commit/3d950b3fa5d89dac381f74847bb4e96ca53dd3c2))
