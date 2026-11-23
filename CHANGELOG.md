# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning: [SemVer](https://semver.org/).

## [Unreleased]

## [0.5.1] - 2026-11-23

### Fixed
- Discovery recognised a server it already had only when the mDNS record carried the server's
  id. It now asks the announced address for the id (`/healthz`) when the record has none, and
  takes over the id for an entry that is still identified by its address. A server set up by its
  IPv4 address is no longer offered again under its IPv6 address.

## [0.5.0] - 2026-11-23

### Fixed
- A slow live update could overwrite what a refresh had found in the meantime, so the next
  refresh announced the same new homework (`lumo_new_item`) a second time. Refreshes and live
  updates now run one after the other.
- Discovery no longer offers a server again when it is announced with its IPv6 address and
  was set up with its IPv4 address (or the other way round). That created a second hub for the
  same server, and every new item was announced twice.

### Changed
- A server is identified by its UUID (`id` in `GET /healthz` and in the mDNS record, Lumo
  0.27 and later) instead of its address: the same server reached by another address (IPv4, IPv6,
  name) is recognised when adding it, in discovery and when reconfiguring. Existing entries take
  over the UUID when they are set up; older servers keep working by their address.

## [0.4.0] - 2026-11-20

### Added
- A second calendar entity with only the exams („Klausuren und Arbeiten“), independent of the
  calendar option, so a dashboard can show both calendars and switch between them.
- A third calendar entity with only the category „Arbeiten“ (class tests, without „Klausuren“).

## [0.3.1] - 2026-11-19

### Added
- The Lumo icon (`brand/`): Home Assistant 2026.3 and later show it for the integration instead
  of the placeholder.
- The icon and status badges in the README.

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
