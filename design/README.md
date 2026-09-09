# design/ — inputs for the design agent

Machine-readable inputs for a UI/UX design agent optimizing the viewer's typography and
building a theming system. Two files, two deliberately different views:

- **`datamodel.json`** — the ideal underlying data model of the linguistic substrate:
  entities, attributes, relationships, enums, caps, and invariants. Modeled on
  `methodology/` (the theory contract: dimension = mode slug = methodology doc =
  dimension module), with caps mirroring each dimension's `validate_payload` in
  `tools/lingua/dimensions/`. The current web viewer's types are *not* the source for
  this file. Every attribute carries a `contentKind` (prose / headword / label /
  identifier / code / quote / count) so typographic decisions can be made from what the
  text *is*.

- **`ui-map.json`** — the viewer as built: every surface, how the substrate is
  partitioned across surfaces, every distinct text role with its current spec, the full
  theme-token inventory (light + dark), and the known gaps. Text roles reference
  datamodel entities via `binds` and its `contentKind` vocabulary, so the two files
  cross-link. The delta between this file and `datamodel.json` is the design space.

## Maintenance

Both files are hand-authored. Every claim carries a `file:line` (or `source`) pointer to
the code or methodology doc it was taken from — checking those pointers is the drift
test. When `web/app/globals.css`, the manifest contract, or a methodology doc's "Schema
and caps" section changes, update the corresponding entries here in the same change.
