# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning: [SemVer](https://semver.org/).

## [Unreleased]

## [0.3.0] - 2026-11-18

### Added
- Automatic discovery of the Lumo server over mDNS (`_lumo._tcp`). A server that is set up
  already is recognised by address or name and not offered again.

## [0.2.0] - 2026-11-18

### Added
- Binary sensor *Substitutions changed*: on for an hour after new or changed substitution entries.
- Sensor *Next meal* with the list of the next ordered meals.
- Option *Calendar*: show all entries, only exams or no exams.

## [0.1.0] - 2026-11-18

### Added
- First version, moved here from the Lumo repository: one device per child with sensors for
  substitutions, cancellations, open homework and the next lessons, a school calendar, a homework
  to-do list, school meals (with Caseda), connection diagnostics and an update hint. Changes
  arrive live over the event stream; the event `lumo_new_item` fires for new substitutions,
  homework and grades. Grades and marking homework as done are off by default and switched on in
  the integration's options.
