# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning: [SemVer](https://semver.org/).

## [Unreleased]

### Added
- First version, moved here from the Lumo repository: one device per child with sensors for
  substitutions, cancellations, open homework and the next lessons, a school calendar, a homework
  to-do list, school meals (with Caseda), connection diagnostics and an update hint. Changes
  arrive live over the event stream; the event `lumo_new_item` fires for new substitutions,
  homework and grades. Grades and marking homework as done are off by default and switched on in
  the integration's options.
