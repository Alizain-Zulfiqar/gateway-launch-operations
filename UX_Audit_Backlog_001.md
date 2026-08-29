# GLO UX Audit Backlog — Source: Seagate_Mission_Planner.docx
Tracking sheet. Update Status as items are resolved. Suggested Status values: Open / In Progress / Answered / Blocked / Needs Decision.

| # | Tab | Item | Type | Status | Notes |
|---|-----|------|------|--------|-------|
| 1 | Main Page | Tab icons to 2x current size | Polish | **Done** | Set 31: Icon size increased via font-size 9pt→16pt in NavButton QSS |
| 2 | Main Page | Tab font size min 16pt | Polish | **Done** | Set 31: Font size increased 9pt→16pt in NavButton QSS styling |
| 3 | Main Page | Tooltip on tab mouseover | Feature | **Done** | Set 31: Tooltips added to all navigation buttons via NavButton.setToolTip() |
| 4 | Projects | Archive Project function (hide from main list) | Feature | **Done** | Set 32: Added is_archived column + migration, Archive button in detail panel, "Show archived" filter toggle in left panel. Archived projects hidden by default. |
| 5 | Projects | Note next to Candidate Sites explaining Sites-tab creation + dropdown association | Copy/Feature | **Done** | Set 33: Added explanatory QLabel under the Candidate Sites header in projects.py clarifying that sites are created/edited in the Sites tab and "+ Add Site" only associates an existing site. |
| 6 | Projects | Edit/Delete sites from Candidate Sites table | Feature | **Done** | Set 32B: Added Edit + Remove buttons to Candidate Sites Actions column. Edit opens SiteEditorDialog (global site fields). Remove calls remove_site_from_project() — unlinks only, never deletes the site or touches activation state except clearing a stale active pairing if this exact site+project was active. Locked rule preserved: no activation/re-pairing occurs here. |
| 7 | Sites | Edit/Delete from All Sites and By Project views | Feature | **Done** | Set 32B: All Sites — "Edit" already existed via inline table editing (unchanged); added real DB delete_site() to the "Delete Row" context action (previously only removed the UI row, leaving orphaned DB records — this was a latent bug, now fixed). By Project — added "Remove from Project" context-menu action (same unlink semantics as item 6), consistent with the view's existing "edit in All Sites" redirect note. |
| 8 | Sites | Prompt for launch vehicle on first-time site creation | Feature | **Done** | Set 33: After saving a newly-created site (not on edits of existing sites), a skippable dialog offers to associate a launch vehicle; writes to site_vehicles (same table/pattern as AnalysisTab._upsert_site_vehicle). Non-fatal — site save always succeeds regardless of dialog outcome. |
| 9 | Sites | Bbox NM editable per site | Feature | **Done** | Already implemented: bbox_nm column in All Sites table is inline-editable (DoubleClicked trigger), read by _parse_row(), and persisted by _save_all(). |
| 10 | Sites | Make By Project the default Sites-tab view | Feature | **Done** | Set 32: Changed default from All Sites to By Project. Updated test_pairing_activation.py to reflect new default. Reinforces locked rule. |
| 11 | Analysis | Platform Name field defaults to Gateway X instead of Active Site's actual platform | Bug | **Done** | Set 34: Root cause — `GatewayMainWindow.platform` was set once at `__init__` (`self.platforms[1]`, "Gateway X") and never resynced; `on_site_changed()`'s docstring claimed platform was "already updated" by the caller but no caller did that. Fixed by resolving `self.platform` from the active site's `platform_id` (fresh DB lookup) inside `on_site_changed()` itself, so every activation path benefits automatically. Falls back to leaving `self.platform` unchanged if the site has no `platform_id` or the lookup fails — never raises. |
| 12 | Analysis | Detail calculation method for Annual GO fraction | Question | **Answered** | `annual_go_fraction()`: count of months with overall_prob >= threshold (default 0.70) / 12 |
| 13 | Analysis | 12-month profile shows aggregated view only, no per-month table; PDF export covers only current month | Bug | **Done** | Set 34: The on-screen 12-row table already existed; the actual bug was in `_export_pdf()`, which discarded the already-computed `self._profile` and silently recomputed a single fresh month using `datetime.now()` + hardcoded engine defaults (ignoring the run's actual mode/year-range settings). Fixed by using `self._profile` directly and adding a new PDF page (`_page_annual()` in `pdf_report.py`) rendering the full 12-month Month/Probability/Verdict/Limiting-Parameter table, inserted right after the cover page via a new `generate_analysis_report(..., annual_profile=)` parameter. |
| 14 | Analysis | Where is Mode set, what does it affect | Question | **Done** | Set 34: Built the `'45day'` mode selector as real radio buttons (Historical / 45-Day) on the Analysis tab. Discovered `modules/m2_weather/data_manager.py::get_site_weather_summary(site, mode, ...)` already fully implements both modes (live NDBC fetch vs NCEI historical) but was never called from the UI — wired it in: 45-Day mode fetches one live near-term snapshot and passes it as `observed_means`; year-range spinboxes disable automatically in 45-Day mode (ignored by the engine in that mode). Extended `compute_annual_profile()` to accept and pass through `mode`/`observed_means` to each month's `compute_probability()` call (purely additive — existing callers like Comparison are unaffected). Network fetch wrapped in try/except so a connectivity failure falls back to model climatology per-parameter rather than crashing the run. |
| 15 | Analysis | Year Range (1960-2024) only settable on Comparison tab, not wired to Analysis tab | Bug/Wiring | **Done** | Set 34: Added Year start/end `QSpinBox` controls (1960-2024, matching Comparison tab's range) to the Analysis tab, wired into the `compute_annual_profile()` call. Previously always used the engine's hardcoded 1960-2024 default regardless of what Comparison's spinboxes were set to (the two tabs' year ranges are independent settings, not shared state — each tab's spinboxes now drive its own analysis run). |
| 16 | Analysis | What other historical sources feed the Analysis | Question | **Answered** | Confirmed — `modules/m2_weather/data_manager.py` explicitly documents the phased plan (swh/swp: "ERA5 reanalysis climatology (Phase 2); fallback → icoads_model"; wg/sea/swell params "remain icoads_model until ERA5 (Phase 2)"). Corroborated independently by the internship-scope doc (`Seagate Metocean & Offshore Mission Analytics Initiative.docx`), which lays out the same Phase 1 (metocean data foundation) / Phase 2 (operational suitability modeling) split. Set 28 remediation did not touch ERA5/WW3 historical wiring — icoads_model-only is by design for the current phase, not an oversight. |
| 17 | Analysis | See Reports #4 | Cross-ref | Open | See item 34 |
| 18 | Vehicles | Selected-state highlight on click | Feature | **Done** | Set 31: Selected rows now highlight with #2563eb (accent blue) background + white text via apply_table_colors() QSS |
| 19 | Launchers | Research online sources to populate launcher table | Research | Open | |
| 20 | Launchers | Selected-state highlight on click | Feature | **Done** | Set 31: Selected rows now highlight with #2563eb (accent blue) background + white text via apply_table_colors() QSS |
| 21 | Comparison | Add detailed comparison report button (threshold params vs. site probability, limiting factors) | Feature | **Done** | Set 35: `generate_comparison_report()` already existed but had zero UI callers (CLI-only, via main.py). Added "Export Detailed Report (PDF)" button to comparison.py, enabled only after a comparison run completes. Report itself was missing per-parameter threshold/probability detail (only had monthly verdict + limiting-parameter name) — added new `_page_site_params()` page per site (Parameter/Threshold/Eff.mean/Prob/Source/Limit-flag, reusing pdf_report.py's single-site parameter table pattern) for that site's best month. Verified end-to-end: button correctly disabled until results exist, enabled after run, PDF generates successfully (7 pages: cover, ranking, then site+params pair per site, data basis). |
| 38 | Reports | Excluded direction parameters (wdV/sdV/swdV) displayed identically to included magnitude params in both PDF report types, with no indication they carried zero weight | Bug | **Done** | Cole-reported 2026-07-11. Confirmed via investigation: the on-screen Analysis tab's Calculation Basis panel already correctly distinguishes included vs. excluded params (`active_params` + INCLUDED/EXCLUDED badges, built in Set 27B), but `pdf_report.py::_page2()` and the new Set 35 `comparison_pdf.py::_page_site_params()` both iterated all 8 parameters uniformly — direction params got the same colour-coded probability styling as included magnitude params even when their weight was zero, misrepresenting them as having counted toward the verdict. Fixed both to check `param in r.active_params` (same field the on-screen panel already uses): excluded rows now show "(excluded)" next to the parameter name, italic/grey text, a grey (not colour-coded) probability cell, and a caption explaining the marker. Excluded params can never carry the "< LIMIT" flag (engine only selects `limiting_param` from `active_params`), so no change needed there. Verified via actual PDF text extraction (pdftotext) on both report types with default weights (direction params excluded by default per Set 27B): single-site report showed 4 "(excluded)" occurrences (3 params + caption), comparison report showed 8 (2 sites × 4). Full suite: 314 passed / 1 skipped / 0 failed, unchanged. |
| 22 | Comparison | What data is used for comparison when no buoy selected / no forecast run | Question/Conflict | **Answered** | Resolves with item 16 — comparison uses icoads_model by design when no buoy/forecast data is present; not a conflict. |
| 23 | NDBC Stations | Changing Network Settings search radius doesn't update NDBC section header | Bug | **Done** | Set 36: Real root cause was deeper than a header-sync issue — `_DiscoverWorker` was instantiated without a `radius_nm` argument at all, so station discovery always used the hardcoded 200.0 NM class default regardless of any setting. Resolved by items 23+24 together (see 24). |
| 24 | NDBC Stations | Move search radius control to NDBC tab itself | UX | **Done** | Set 36: Removed `ndbc_radius_spin` from Settings > Network & Search Settings; added a live "Search radius" spinbox directly on the NDBC tab, reading/writing the same `ndbc_radius_nm` setting. `_on_discover()` now passes the spinbox's current value into `_DiscoverWorker`, and the status label shows the radius actually used ("Fetching stations within N NM…", "X stations found within N NM"). Verified end-to-end: spinbox loads the saved setting, edits persist, and the value is actually passed to the discovery worker (previously silently ignored). |
| 25 | Forecast | Show model data per threshold parameter vs. threshold value | Feature | **Done** | Set 36: Parameter status cards (Wind Speed, Wave Height) previously showed only the model value and GO/MARGINAL/NO-GO status, with no indication of the limit that produced it. Added a `threshold` field to both card-building paths in `compute_forecast_analysis()` (merged-model and legacy NDBC-aggregation), sourced from the active vehicle's real threshold (`max_wind_kts`/`max_hs_m`) when available, falling back to the same conservative constants the status functions already use internally. `_status_card()` now renders it as a third line ("limit 22.0 kts"). Verified: a vehicle with `max_wind_kts=22.0` produces a card correctly reading "limit 22.0 kts", not the generic default. |
| 26 | Forecast | What does "Wind Model est.~" designate | Question | **Done** | Investigated the full data path: `fetch_combined_forecast()` only pulls wind from NWS — Open-Meteo supplies wave/swell only in this app's wiring, nothing else feeds wind. So when NWS coverage is unavailable, there is no actual "model estimate" backing the wind value at all; the label was inaccurate/misleading. Fixed to reflect reality: NWS available → unchanged "Wind: NWS NDFD ✓"; NWS unavailable but NDBC buoy stations selected → "Wind: NDBC buoy overlay (N) ~" (the only real fallback source); neither available → "Wind: Unavailable ✗" (matching the existing Wave badge's pattern for its own unavailable case). Verified all three states via direct calls to `_update_source_badges()`. |
| 27 | Ports | (no findings) | — | — | |
| 28 | Vessels | Reorder Vessels tab above Vehicles tab | UX | Open | |
| 29 | Vessels | Selected-state highlight on click | Feature | **Done** | Set 31: Selected rows now highlight with #2563eb (accent blue) background + white text via apply_table_colors() QSS |
| 30 | Vessels | Investigate ABS/Equasis/public vessel DB integration | Research | Open | |
| 31 | Vessels | If (30) feasible, add vessel-by-IMO-number lookup | Feature | Open | Dependent on 30 |
| 32 | Contracts | (no findings) | — | — | |
| 33 | Reports | Ability to delete reports | Feature | **Done** | Set 37: The capability already existed (right-click → "Delete..." — removes both the file and DB row) but wasn't discoverable without knowing to right-click. Added a visible "Delete Selected" toolbar button next to Refresh, supporting multi-row selection with one confirmation and a per-report failure summary if any deletion fails. Refactored the shared delete logic into `_delete_report_row()` so both the context-menu single-delete and the new batch button use the same path. Verified: selecting all rows and clicking Delete Selected removes both the DB rows and clears the table. |
| 34 | Reports | "Associate with Project" dropdown non-functional | Bug | **Done** | Set 37: The dropdown and generation wiring were actually fully functional — the real issue is that `build_report_filename()` requires `project.code_name` + both launch dates to construct the `{CODE}_..._{start}-{end}_...` filename, but "+ New Project" only ever sets `name`/`status`, so nearly every project fails this validation silently (a warning dialog with no path forward) the first time a user tries to generate with one selected — reading as "non-functional." Fixed two ways: (1) incomplete projects are now flagged directly in the dropdown itself (e.g. "IncompleteProj ⚠ missing code name, start date, end date", with a matching tooltip) so the gap is visible before generating; (2) the blocking warning dialog gained a "Go to Projects" button that navigates straight to the Projects section (reused/generalized the existing `_go_to_analysis()` pattern into `_go_to_section(key)`). Verified end-to-end: dropdown label and tooltip correctly list missing fields, and clicking "Go to Projects" in the warning actually navigates there. |
| 35 | Reports | Cannot generate Go/NO-GO without buoy data; should fall back to forecast-model-only when no buoys in radius | Feature/Bug | **Answered** | Resolves with item 16 — buoy-less fallback to forecast-model-only is Phase 2 scope, not a bug in the current phase. |
| 36 | Reports | Report format should match original spec detail (screenshot) | Feature/Spec | **Deferred** | Spec shows "Summary of Wave Statistics" section to be inserted into probability report. Requires monthly statistics extraction + seasonal narrative generation functions (not yet built). Scoped for a future larger Set that builds reusable statistical aggregation + report formatting framework. Current Set 28 descoped; placeholder instruction retained for future assignment. |
| 37 | History | No historical display captured at all | Gap | **Done** | Set 38 confirmed it was a genuine placeholder (not a bug); Set 40 built it per the scope below. `ui/sections/history.py` now merges 4 already-existing, already-timestamped tables (`analyses`, `project_site_status_history`, `reports`, `site_vehicles`) into one read-only, newest-first table — no new schema. Filters by Type/Project/Site (reusing `reports.py`'s filter-combo pattern); double-click a row to jump to the relevant section (Analysis/Projects/Reports), reusing the `_go_to_section(key)` pattern from Set 37. Explicitly read-only, consistent with `project_site_status_history` being append-only elsewhere. Verified end-to-end: all 4 event types load and merge correctly, newest-first sort holds, project filter correctly excludes events with no project association (analysis runs/vehicle usage aren't project-scoped), and row double-click navigates to the correct section. |

## Immediate decision items (before scoping instruction sets)
- Items 14, 16, 22, 35: resolved as of Set 29 (see rows above) — no longer open decision items.
- Set 28 (Item 36 — Reports format spec): **deferred** pending construction of supporting statistical functions (monthly statistics extraction, seasonal narrative generation). These will be built as part of a larger, future Set that multiple report types and features can reuse.
- Note: Set 28 itself was not run — a "Pre-28 correction set" was completed instead. CLAUDE.md should reflect that Set 28 is still outstanding, not superseded.

## Suggested next step
Sequence remaining Set numbers against this table (e.g., Set 30 = Expense Ledger per memory, Set 31+ = this backlog by tab) so the tracking column and CLAUDE.md stay in sync.

## Set 32B — Site Edit/Delete — DONE
Scope: Items 6 & 7. Completed:
  - `ui/dialogs/site_editor.py` — new SiteEditorDialog (Edit only; Add remains
    inline in the All Sites table per existing convention).
  - `modules/m1_site/site_config.py` — added `update_site()`; `delete_site()`
    left as a real DB delete (was already the intended semantic) but its
    docstring now documents the FK-constraint failure mode explicitly.
  - `modules/m1_site/project_sites.py` — added `remove_site_from_project()`
    (project_sites unlink only; append-only history untouched, matching the
    module's existing "never UPDATE/DELETE history" rule).
  - Candidate Sites table (Projects tab): Edit + Remove buttons added.
  - All Sites table (Sites tab): context-menu "Delete Row" was previously
    UI-only (never touched the database for saved rows — a latent bug, now
    fixed) — now performs a real `delete_site()` with FK-error handling.
  - **Post-completion fix (user-reported 2026-07-10):** Cole manually tested
    and found that deleting sites via the Sites tab still reoccurred after
    an app restart, while Candidate Sites removal did not. Root cause:
    `_delete_selected()` — the prominent **"Delete Selected" toolbar button**
    — was a separate, pre-existing method from the context-menu "Delete Row"
    fixed above, and it ONLY called `self._table.removeRow()`, never
    `delete_site()`. It predates Set 32B and was missed because the toolbar
    button is far more discoverable than the right-click context menu, but
    only the latter had been fixed. Reproduced empirically against a copy of
    the live `gateway.db` (confirmed the exact symptom: row vanishes, DB
    record persists, reappears on simulated restart) before fixing. Fix:
    extracted the delete logic into a shared `_delete_site_row(row, site_id)`
    helper used by both `_delete_row()` (single, context menu) and
    `_delete_selected()` (batch, toolbar) — batch delete now shows one
    confirmation covering all selected saved sites, deletes each via
    `delete_site()`, and reports any FK-blocked failures by name in a single
    summary dialog at the end. Re-verified empirically: single delete,
    multi-select batch delete (mixed standalone/linked/unsaved rows), and
    persistence across a simulated restart all behave correctly. Full suite:
    314 passed / 1 skipped / 0 failed, unchanged.
  - **Second post-completion fix (user-reported 2026-07-10):** Cole then
    reported a raw "Foreign Key Constraint Failed" error when deleting
    sites "from a project" on the Sites tab. Investigated by attempting to
    reproduce `remove_site_from_project()` raising an FK error directly and
    via the full UI path (including with realistic history rows and an
    active-site removal) — could not reproduce; a plain `DELETE FROM
    project_sites` cannot violate an FK constraint since nothing references
    that table. Root cause was message design, not logic: the All Sites
    "Cannot Delete Site" dialog (for the correct, by-design case of a
    project-linked site) embedded the raw `str(exc)` text, which literally
    reads "FOREIGN KEY constraint failed" — Cole likely saw this dialog and
    described it by that phrase. Fixed by translating the exception inside
    `_delete_site_row()` into plain language before it ever reaches a
    dialog (detects "FOREIGN KEY" in the exception and substitutes a
    human-readable explanation); also hardened both
    `remove_site_from_project()` call sites (`sites.py`'s
    `_on_remove_from_project` and `projects.py`'s
    `_on_remove_candidate_site`) to show a clean generic message instead of
    `str(exc)`, defensively, even though no failure path was found there.
    Verified via a stubbed-dialog script against a copy of the live DB that
    the resulting message body contains no "FOREIGN KEY" or "IntegrityError"
    text. Full suite: 314 passed / 1 skipped / 0 failed, unchanged.
  - **Behavior change (Cole-authorized, 2026-07-10):** Cole clarified that
    "Delete Selected"/"Delete Row" in the All Sites table should actually
    delete project-linked sites, not just block them. Since
    `project_site_status_history` (append-only) also holds a NOT NULL FK to
    `sites(id)`, the site could never be deleted while any history existed
    for it, even after unlinking from every project — confirmed this
    directly (unlink via `remove_site_from_project()`, then `delete_site()`
    still raised `FOREIGN KEY constraint failed`). Presented Cole two ways
    to resolve the conflict; he chose to delete the site's own history
    rows (scoped to that one site only, all other sites'/projects' history
    untouched) rather than keep the block. Added
    `modules/m1_site/site_config.py::delete_site_cascade()` — one atomic
    transaction that removes the site's rows from every table with a FK to
    `sites(id)` (`project_sites`, `project_site_status_history`,
    `site_vehicles`, `voyage_schedules`, `analyses`, `reports`) and then
    the site itself; rolls back entirely on any failure. Added
    `get_site_associations()` for a pre-delete count used to warn the user
    exactly what will be removed before they confirm (both single-row and
    batch delete confirmations now list this). Report PDF files already on
    disk are deliberately NOT deleted — only their `reports` row, so files
    become orphaned-but-harmless rather than being destroyed.
    `_delete_site_row()` in `sites.py` now calls `delete_site_cascade()`
    instead of the non-cascading `delete_site()` (which is kept, unchanged,
    for any future caller that wants the conservative behavior). "Remove
    from Project"/Candidate Sites "Remove" remain unlink-only — this
    cascade only applies to the All Sites delete actions. Verified
    end-to-end against a copy of the live DB with a realistic multi-
    association site (2 projects, 4 history entries, vehicle usage,
    analysis result, report): confirmation dialog correctly listed all
    associations, all 6 referencing tables were cleared, the site was
    removed, both projects remained fully intact, and it did not reoccur
    after a simulated restart. Full suite: 314 passed / 1 skipped / 0
    failed, unchanged. **Live-confirmed by Cole (2026-07-10):** deleted all
    sites individually in the running app; they remain deleted after
    restart.
  - By Project table (Sites tab): added "Remove from Project" context action,
    consistent with the view's existing "edit in All Sites" redirect note.
  - Locked rule preserved: none of the new code paths perform activation —
    they only clear a stale active pairing if the removed/deleted site
    happened to be the currently active one for that project.
  - **Important discovered behavior, superseded by the cascade-delete
    change above:** once a site has ever been linked to any project,
    `project_site_status_history` retains a permanent FK to it, so the
    non-cascading `delete_site()` will always fail for that site even
    after unlinking. This is still true of `delete_site()` itself (kept
    unchanged), but no longer applies to the Sites tab's delete actions,
    which now call `delete_site_cascade()` instead — see the entry above.
  - **Bug fixed in passing:** `update_site()`/`delete_site()` (both new/
    touched in this Set) previously lacked `try/finally` around the
    connection, so a raised exception (e.g. the FK case above) leaked an
    open connection and could lock the database for subsequent calls.
    Fixed. **Note:** `save_site()` in the same file has the identical
    pre-existing pattern and was NOT touched — out of this Set's scope,
    flagged for a future pass.

## Set 39 — Full Historical Data-Source Wiring — RUN 2026-07-11, PARTIAL

Cole confirmed (2026-07-10) the original app scope always intended Copernicus
data to be included; investigation found it's implemented but dormant. Scope
this as its own Set — **do not fold into Set 35/36/37/38** (Comparison
report / NDBC+Forecast / Reports / History are already sequenced ahead of
this) — since it touches the engine's observed-data path, not just UI.

**Confirmed current state (as of Set 34):**
  - `modules/m2_weather/era5.py::fetch_swell_climatology()` is a real, working
    Copernicus CDS API client. Credentials are configured on this machine
    (`~/.cdsapirc` exists). It currently fetches only `swh`/`swp`/`swd`
    (significant swell height, swell period, swell direction) — no wind or
    combined-wave-height variables.
  - `data_manager._apply_era5_swell()` correctly calls it and populates
    `swh`/`swp` with `source: "era5_reanalysis"`. Wired into
    `_fetch_historical()`, which is the historical-mode branch of
    `get_site_weather_summary(site, mode)`.
  - **The gap:** `get_site_weather_summary(mode="historical")` has ZERO live
    callers anywhere in the app (confirmed by grep across the full codebase).
    Set 34 wired `get_site_weather_summary()` into the Analysis tab, but only
    for `mode="45day"`. Historical mode still uses pure ICOADS
    climatological lookup (`effective_mean()`) with no live/reanalysis
    overlay of any kind — Copernicus/ERA5 included.
  - Per-parameter source coverage today, by mode:

    | Param | 45-Day mode source | Historical mode source |
    |---|---|---|
    | `ws` (wind speed) | NDBC live | NCEI Global Marine (wired, but unused — see gap above) |
    | `wg` (wind gust) | NDBC live | **icoads_model only — no live/reanalysis source wired** |
    | `sh` (sea/wave height) | NDBC live | **icoads_model only — no live/reanalysis source wired** |
    | `swh` (swell height) | NDBC .spec, else WW3 fallback | ERA5/Copernicus (wired, but unused — see gap above) |
    | `swp` (swell period) | NDBC .spec, else WW3 fallback | ERA5/Copernicus (wired, but unused — see gap above) |
    | `wdV` (wind direction) | NDBC live | NCEI Global Marine (wired, but unused) |
    | `sdV` (sea direction) | NDBC live (partial) | icoads_model only |
    | `swdV` (swell direction) | NDBC .spec | icoads_model only |

**Scope for the future Set (per Cole's explicit ask — must cover ALL of
these, not just re-wire what already exists):**
  1. Wire Historical mode to actually call `get_site_weather_summary(mode=
     "historical")` (mirrors the 45-Day wiring from Set 34) — closes the
     "implemented but dormant" gap for `ws`, `wdV`, `swh`, `swp`.
  2. Research whether NCEI Global Marine's underlying dataset exposes wind
     **gust** (`wg`) — `ncei.py::fetch_wind_history()` currently extracts
     only mean/p90 wind speed and direction; confirm whether gust is present
     in the raw NCEI response and just not being parsed, or genuinely absent
     from that dataset (may require a different NCEI product).
  3. Research ERA5/Copernicus variables beyond swell: ERA5 reanalysis
     includes "significant height of combined wind waves and swell" (a
     candidate source for `sh`) and 10m wind components — evaluate whether
     `era5.py` should be extended to also pull these, giving `sh` a real
     historical source instead of icoads_model-only.
  4. Clarify and implement "sea state percentages" — Cole's phrasing suggests
     this may be a distinct derived statistic (e.g., % of time below an
     operational threshold, or a distribution rather than a single mean),
     closer to what `modules/m2_weather/ndbc_history.py::compute_period_statistics()`
     already computes for NDBC data than to a single climatological mean.
     Needs a scoping conversation before implementation: is this a new
     report/UI element, or an enhancement to the existing observed_means
     shape?
  5. Once source coverage is decided, update `AnalysisResult.data_sources`
     labeling and the PDF report's "Data Source per Parameter" table
     (`_page3` in `pdf_report.py`) so users can see exactly which live
     source (if any) backed each parameter for a given run — today that
     table already exists but will only ever show real diversity once this
     gap is closed.
  6. Full regression pass required — this touches the engine's
     `observed_means` path shared by both modes; must confirm 45-Day mode
     (Set 34) is unaffected.

### What was actually delivered (2026-07-11)

**Item 2 (gust research) — CONFIRMED, empirically:** queried the live NCEI
API directly (not just docs) with both plausible field names
(`WIND_GUST_SPEED`, `GUST_SPEED`) against a wide bbox/date range (36,000+
real records). Neither ever appeared. NCEI Global Marine genuinely does not
carry gust — `wg` has no live historical source, confirmed rather than
assumed.

**Item 3 (ERA5 extra variables) — SUPERSEDED by a better discovery:** while
testing, found NCEI Global Marine *also* reports `WAVE_HGT`, `WAVE_DIR`,
`SWELL_HGT`, `SWELL_DIR` — fields `ncei.py` never requested before. This
covers `sh`/`sdV`/`swdV` from the *already-wired* NCEI source (real
observations) better than extending ERA5 reanalysis would, so extending
ERA5 further was dropped as unnecessary. `modules/m2_weather/ncei.py` and
`data_manager.py::_fetch_historical()` extended to fetch/parse/aggregate
these — verified against live data: `sh=1.94m`, `sdV=6.0°`, `swdV=7.9°`,
correctly labeled `source: ncei_global_marine`.

**Item 1 (wire Historical mode to `get_site_weather_summary()`) —
IMPLEMENTED BUT LEFT INERT, by Cole's decision.** While verifying this
end-to-end, discovered NCEI's query latency is **~130 seconds per calendar
month requested**, and — critically — this is true of the *original*,
unmodified 2-field (wind-only) request too (direct A/B test: 128.9s vs
129.6s for the new 6-field request, statistically identical). This is a
**pre-existing NCEI-side reality that predates this Set** and was never
caught before because `get_site_weather_summary(mode="historical")` had
zero live callers until Set 39. The module's old docstring claim ("~2 years
complete in <30s") was already false.

Since the Analysis tab only offers year-granularity controls, the smallest
possible request is 12 months ≈ 26 minutes — far too slow to wire in
automatically. `_fetch_historical()`'s safety cap was tightened from
`NCEI_MAX_YEARS=2` to `NCEI_MAX_MONTHS=3`, which — given the UI's year-only
granularity — means the live NCEI overlay **never actually fires through
the real UI today**; Historical mode silently stays on ERA5+ICOADS only,
the same behavior as before this Set. `ui/analysis_tab.py::_run()` still
calls `get_site_weather_summary(mode="historical", ...)` on every run (so
the wiring is real and ready), but the cap makes it a fast no-op in
practice for any realistic year selection.

**Cole's direction (2026-07-11):** don't force this into the interactive
Analysis flow given the latency. Instead, a future local caching/download
mechanism should let the app fetch NCEI data once (e.g., the last ~5 years)
and store it locally, so `_fetch_historical()` can serve from cache instead
of hitting the live API on every run. Scoped as **Set 41** below.

**Item 4 (sea state percentages)** — not addressed this Set; still needs
the scoping conversation noted in the original plan above (item 4).

**Item 5 (data_sources labeling)** — already correct as a side effect of
items 2/3's implementation: `sh`/`sdV`/`swdV` now correctly show
`ncei_global_marine` in `AnalysisResult.data_sources` and the PDF's "Data
Source per Parameter" table whenever the (currently inert) live path does
fire.

**Item 6 (regression)** — full suite: 314 passed / 1 skipped / 0 failed,
unchanged throughout.

## Set 41 — Local NCEI Historical Data Cache — DONE (2026-07-11)

Scope: unblock Set 39's item 1 (live NCEI wind/wave/swell overlay for
Historical mode) by removing the per-run network latency, per Cole's
direction (2026-07-11).

**Problem this solves:** NCEI Global Marine queries take ~130s per calendar
month requested — this is NCEI-side query cost (confirmed via direct A/B
test, not caused by which fields are requested), so it can't be sped up by
changing what this app asks for. It CAN be avoided on repeat use by fetching
once and storing locally.

**Proposed shape:**
  1. A new local cache table (e.g. `ncei_monthly_cache`), keyed by a
     coarse lat/lon bucket (NCEI's `boundingBox` already covers an area, not
     a point, so caching should key on the same bbox granularity, not exact
     site coordinates) + calendar month, storing exactly what
     `ncei.py::_summarise()` already computes (ws/wave/swell means, p90s,
     circular-mean directions, record_count) — not raw observation rows, to
     keep storage small.
  2. A one-time/on-demand "Download NCEI history" action (Settings or Sites
     tab) that runs the existing month-by-month loop as a background job
     (QThread, with a progress bar — "Fetching month 3 of 60…") and writes
     results into the cache instead of returning them synchronously. Cole
     suggested defaulting the initial download to roughly the last 5 years.
  3. `_fetch_historical()` checks the cache first for each month in range;
     only falls through to a live NCEI request (or skips, per the existing
     cap) for months not yet cached.
  4. Cache staleness: this is climatological/historical data, not live
     conditions — no complex invalidation needed. The most recent 1-2
     months may get corrected/backfilled by NCEI later, so a manual
     "Refresh" action covering just the recent window is enough; no
     automatic expiry required.
  5. Once cached data exists, revisit Set 39's `NCEI_MAX_MONTHS` cap — it
     only needs to gate LIVE fetches, not cached reads, so a full 1960-2024
     Historical run could safely use cached months while still capping any
     live top-up fetch for uncached months.

### What was delivered

  1. `core.database`: new `ncei_monthly_cache` table, keyed by the exact
     NCEI `boundingBox` string queried (not site id — two sites sharing a
     bbox_nm and area naturally share a cache row) + calendar month.
     Stores `ncei.py::_summarise()`'s exact output shape (means/p90s/
     circular-mean directions/record_count), not raw observation rows.
  2. `ncei.py`: `get_cached_month()` / `save_cached_month()` helpers.
  3. `ui/sections/settings.py`: new "NCEI Historical Data Cache" group on
     the Data Sources tab — site combo, From/To year spinboxes (defaulting
     to the last 5 years per Cole's suggestion), "Download NCEI History"
     button, progress bar, and Cancel (backed by `_NceiDownloadWorker`, a
     QThread that skips already-cached months automatically, so it's safe
     to stop and resume later).
  4. `data_manager._fetch_historical()` rewritten to check the cache first
     for every month in range.

### Critical regression found and fixed during verification

The first version of item 3/5 gated the `NCEI_MAX_LIVE_MONTHS` cap
**per-month** instead of **per-range** — meaning even a 65-year default
request would still attempt up to 3 live NCEI fetches (390+ seconds)
before giving up, instead of skipping live fetching entirely as Set 39
guaranteed. This silently broke the core safety property Set 39 was built
around and was caught by running the full test suite: **it took 3.5 hours
instead of ~90 seconds**, with 18 unrelated NDBC tests failing afterward
from apparent socket exhaustion (WinError 10013) caused by that duration —
not a logic bug in those tests, confirmed by them passing cleanly once the
regression was fixed and the suite re-run (68s, 314 passed / 1 skipped).

**Fix:** the live-fetch gate now checks whether the ENTIRE requested range
is small (`≤ NCEI_MAX_LIVE_MONTHS`) *before* iterating, not per-month.
Checking the cache for every month in a huge range is still fine (a fast
local SQLite read, confirmed at 0.65s for a 780-month check), but an
uncached large range now NEVER calls `fetch_wind_history()` — cache-only,
matching Set 39's original guarantee exactly. The only way to populate the
cache for large ranges is the explicit Settings download action, which has
no range cap of its own (by design — it's an intentional, user-initiated,
cancellable background job, not part of the interactive Analysis flow).
This is slightly more conservative than the original item 5 wording ("cap
any live top-up fetch for uncached months" implied large ranges could
still live-fetch a few months) — deliberately chosen after the regression
made clear that ANY live-fetch allowance on large ranges reintroduces
multi-minute risk to the interactive flow, which Set 39 explicitly ruled
out.

**Verified:** cache write/read round-trip; a fully-cached 12-month range
uses the cache exclusively (1.15s, correct source label, no live call);
a mostly-uncached 65-year range stays fast (0.65s, cache-only, no live
call attempted). Full suite: 314 passed / 1 skipped / 0 failed.

## Set 40 — Build the History Tab — DONE (2026-07-11)

Scope: Item 37. `ui/sections/history.py` currently has zero data wiring — this
is a real feature build, not a bug fix. The placeholder's own text ("Analysis
session history and previously visited sites will appear here") already
names the two data sources; a good first version wouldn't need any new
tables, since the underlying data already exists and is timestamped:

  - `analyses` (`created_at`) — every saved analysis run: site, vehicle,
    platform, mode, overall_prob, verdict.
  - `project_site_status_history` (`created_at`, append-only) — every
    project-site status change, with `changed_by`/`approval_note`.
  - `reports` (`generated_at`) — every generated PDF, analysis or voyage.
  - `site_vehicles` (`last_used`) — most-recently-used site+vehicle pairs
    (already surfaced elsewhere as the Sites tab's "Vehicles Used" column,
    Set 27B — History would be a second consumer of the same table).

**Proposed shape for a first version:**
  1. A single chronological table merging the four sources above (a `UNION
     ALL` across them with a common `event_type`/`timestamp`/`summary`
     shape), newest-first, matching the read-only, no-new-schema spirit of
     the placeholder text.
  2. Filters: by type (Analysis run / Status change / Report generated /
     Vehicle used), by project, by site — reusing the same filter-combo
     pattern already established in `ui/sections/reports.py`.
  3. Row click → jump to the relevant section (Analysis/Projects/Reports),
     reusing the `_go_to_section(key)` helper generalized in Set 37.
  4. Explicitly NOT in scope for a first version: editing or deleting
     history entries (some of these tables, like
     `project_site_status_history`, are intentionally append-only/immutable
     elsewhere in this app — History should stay read-only, consistent with
     that existing rule) or a brand-new history-specific table — start from
     what's already recorded before inventing new persistence.

## Set 42 — Fix ERA5/Copernicus Data Calls — DONE (2026-07-13), all items resolved

Scope: fix two real bugs found while answering "what's the best CDS dataset
to call" (2026-07-12): a broken client library URL path, and a wrong swell
variable. Follow-up to Set 39's Copernicus/ERA5 gap.

**Delivered (code):**
  1. Swapped `cdsapi.Client` for `ecmwf.datastores.legacy_client.LegacyClient`
     in `era5.py` (new `_get_cds_client()` helper) — plain `cdsapi.Client`
     builds retrieve() URLs on a retired path (`/api/resources/{dataset}`,
     confirmed 404 via direct testing); `LegacyClient` uses the correct
     current path and is a drop-in replacement (identical call signature).
     `requirements.txt` updated to list `ecmwf-datastores-client` explicitly.
  2. Fixed `_ERA5_VARS`: was requesting
     `significant_height_of_combined_wind_waves_and_swell` (combined
     wind-sea+swell) to populate the app's `swh` (swell-only) parameter —
     a genuine mismatch, confirmed against ECMWF's own parameter docs. Now
     requests `significant_height_of_total_swell` /
     `mean_period_of_total_swell` / `mean_direction_of_total_swell`
     (swell-only), with `_parse_era5_nc()`'s netCDF key lookups updated to
     match (`shts`/`mpts`/`mdts`).
  3. Fixed `check_era5_auth()`: previously only instantiated
     `cdsapi.Client()` (parses `.cdsapirc`, makes no network call) and
     reported "Connected" regardless of whether real requests would
     succeed — confirmed this gave a false positive even while every live
     retrieve() call was failing. Now calls a real, lightweight
     `check_authentication()` request.
  4. Full suite: 314 passed / 1 skipped / 0 failed, unchanged.

**Verified live (2026-07-12):** confirmed the URL fix works — requests now
reach the correct endpoint (`/api/retrieve/v1/processes/{dataset}/execution`,
no longer 404) and fail gracefully (clean `None` return, clear log
message) rather than crashing. Could not verify the corrected swell
variables produce correct *values* end-to-end, or test wind gust
availability (both were in scope) — blocked by item 5.

**Blocker — RESOLVED.** Cole regenerated the CDS API key as a current
Personal Access Token; live CDS requests now authenticate successfully.

**Item 3 (wind gust via ERA5)** — still not implemented/wired up. No longer
blocked by auth, but out of scope for the bugs Cole actually reported; left
as a future task.

**Follow-up fixes, both found and fixed via real-world use after the 401 was
resolved (2026-07-12 to 2026-07-13):**

1. **ERA5 `_parse_era5_nc()` — `KeyError: "No variable named 'time'"`.**
   Reported by Cole while running an analysis (mislabeled "45D forecast" in
   his message, but traced to Historical mode — `_apply_era5_swell()` is
   only reachable from `_fetch_historical()`). Current CDS output names the
   time coordinate `valid_time`, not `time`. Fixed with a flexible lookup
   (`_first_nc_key(ds_pt, ["valid_time", "time"])`) used for both the month
   filter and the `.sel()` call. **Verified live**:
   `fetch_swell_climatology(28.5, -80.5, 2020, 2020, months=[6])` returned
   real swell data (`swh_mean_m: 0.511`, `swp_mean_s: 6.169`,
   `swd_mean_deg: 95.7`) — physically plausible.

2. **WW3 ERDDAP — `"no recognised SWH variable found in NWW3_Global_Best"`.**
   Reported by Cole immediately after the ERA5 fix above. Live inspection of
   the dataset (`.das` + `info/.../index.json`) found three independent bugs
   in `_do_fetch_ww3()`:
   - Every candidate in `_WW3_SWH_CANDIDATES`/`_WW3_MWD_CANDIDATES`/
     `_WW3_MWP_CANDIDATES` was stale — none exist in the live dataset. Real
     names are short codes; confirmed via `standard_name` metadata that
     `shgt`/`sdir`/`sper` are the genuinely swell-only fields (same
     "combined vs swell-only" mistake class as the `_ERA5_VARS` bug above —
     `Thgt`/`Tdir`/`Tper` are combined/total, `whgt`/`wdir`/`wper` are
     wind-sea-only). Candidate lists reordered to prioritize the correct
     names, old names kept as fallbacks.
   - Missing `depth` constraint — this griddap dataset has 4 dims
     (`time, depth, latitude, longitude`), not 3.
   - Wholesale-replacing `e.constraints` (even after adding `depth`) still
     failed erddapy's key-equality check because it drops the `{dim}_step`
     keys erddapy auto-populates — fixed by mutating the dict in place
     (`e.constraints.update({...})`) instead of reassigning it.
   - Longitude convention mismatch: dataset uses 0–360°E, this app uses
     -180..180 (+E/-W) — fixed by converting only at this API boundary
     (`lon % 360`).
   **Verified live**: `fetch_swell_realtime_ww3(28.5, -80.5)` returned
   `{'swh_mean_m': 0.452, 'swh_p90_m': 0.78, 'swd_mean_deg': 95.6,
   'swp_mean_s': 7.429, 'source': 'ww3_erddap', 'record_count': 6125}`.
   Note: live WW3 griddap queries against this dataset took ~13 minutes
   during testing (server-side, not a code issue) — same latency character
   as the documented NCEI historical-fetch delay.

Full suite re-run after both follow-up fixes: 314 passed / 1 skipped / 0
failed (189.07s) — baseline unchanged.

**Follow-up #3 — WW3 local cache (requested by Cole 2026-07-13):** the
~13-minute WW3 latency above is real and NOAA-side, not fixable by trimming
the request further (already down to 1 depth level, a 1° lat/lon box, and
only the 3 needed variables). Same mitigation as Set 41's NCEI cache, added
here for WW3:
  - New `ww3_realtime_cache` table (`core/database.py`), keyed by
    `(lat_bucket, lon_bucket)` — lat/lon rounded to the nearest whole
    degree, matching the query's own `+-0.5` deg window, so nearby sites
    share a cache row.
  - `get_cached_ww3()` / `save_cached_ww3()` (`era5.py`), same
    `INSERT ... ON CONFLICT DO UPDATE` shape as the NCEI cache helpers.
  - **Unlike the NCEI cache, this one expires** (24h, `_WW3_CACHE_MAX_AGE_HOURS`)
    — the WW3 window is "last 45 days," a rolling current-conditions figure,
    not climatology, so a stale cache row is wrong, not just outdated.
  - `fetch_swell_realtime_ww3()` now checks the cache first and only calls
    the slow live path on a miss; both cache read and write are non-fatal
    (wrapped in try/except) so a cache problem never blocks a live result.
  - **Verified live**: first call against an empty cache took 215.8s
    (live ERDDAP fetch); an immediate second call for the same coordinates
    returned the identical result in 0.0s from the cache.
  - Full suite re-run: 314 passed / 1 skipped / 0 failed — baseline
    unchanged.

## Set 42 follow-up #4 — Wind gust via ERA5 + Analysis tab fetch-status banner — DONE (2026-07-13)

Two items requested by Cole in the same message: (1) wire up wind gust via
ERA5, deferred earlier only because CDS auth was blocked (now resolved);
(2) add a status indicator to the Analysis tab for the waits during live
data refresh.

**1. Wind gust via ERA5 — implemented and wired into `data_manager.py`.**
NCEI Global Marine (the other historical wind source) carries no gust field
at all, so `wg` had no live historical source and stayed `icoads_model` by
design. Live-tested (now that CDS auth works) whether ERA5's
monthly-averaged reanalysis product actually carries gust — ECMWF's docs
mark gust "forecast only", so this was genuinely uncertain — and confirmed
it does, netCDF shortname `i10fg`.
  - New `fetch_gust_climatology()` in `era5.py`, structured identically to
    `fetch_swell_climatology()` (`_do_fetch_era5_gust()` /
    `_parse_era5_gust_nc()`, same `valid_time`/`time` coordinate fix reused).
    Converts m/s → knots via `config.MS_TO_KTS`.
  - New `_apply_era5_gust()` in `data_manager.py`, wired into
    `_fetch_historical()` right after the existing `_apply_era5_swell()`
    call — populates `summary["wg"]` with `source: "era5_reanalysis"` on
    success, leaves `icoads_model` otherwise.
  - **Verified live**: `fetch_gust_climatology(28.5, -80.5, 2020, 2020,
    months=[6])` → `{6: {'wg_mean_kts': 11.81, 'wg_p90_kts': 11.81, ...}}`.
    Through the full path, `_apply_era5_gust(summary, 28.5, -80.5, 2020,
    2020)` moved `summary["wg"]` from `{'mean': None, 'source':
    'icoads_model'}` to `{'mean': 15.5, 'source': 'era5_reanalysis'}`.
  - New unit tests in `tests/test_era5.py`: `TestFetchGustClimatology`
    (mirrors `TestFetchSwellClimatology`) plus two data-manager integration
    tests (`test_era5_gust_populated_updates_wg_source`,
    `test_era5_gust_none_leaves_wg_as_icoads_model`).

**2. Analysis tab fetch-status banner.** `_run()`'s live fetches (NCEI/ERA5
in Historical mode, NDBC in 45-Day mode) and `compute_annual_profile()`
itself are synchronous; only the small bottom-of-window status bar updated
previously, so a slow fetch made the app look frozen.
  - New `fetch_status_widget` (indeterminate `QProgressBar` + `QLabel`) in
    `AnalysisTab._build()`, shown/hidden via `_set_fetch_status(msg)`, which
    also disables `run_btn` while a fetch is in flight (prevents
    double-click re-entrancy) and forces a repaint.
  - `_run()`'s body is now wrapped in `try/finally` so the banner clears and
    `run_btn` re-enables even if a fetch or the engine call raises, not just
    on success.
  - New `tests/test_analysis_fetch_status.py` (5 tests): banner
    hidden-by-default, shows/disables on `_set_fetch_status(msg)`,
    hides/restores on `_set_fetch_status(None)`, correctly leaves the Run
    button disabled when there's no active site, and confirms the
    try/finally clears the banner even when `compute_annual_profile` is
    mocked to raise.

**Bug found and fixed along the way — DB test isolation, real production
data pollution.** Adding the WW3 cache in follow-up #3 above meant
`fetch_swell_realtime_ww3()` now touches the database — and
`tests/test_era5.py` was the one test file in the suite with no DB
isolation fixture (unlike `test_contracts_and_pairing.py`,
`test_analysis_fetch_status.py`, etc.). Running the full suite after this
Set's changes caused `TestFetchSwellRealtimeWW3`'s network-gated live test
to write real rows straight into **production** `gateway.db`'s
`ww3_realtime_cache` — confirmed via direct inspection: two polluted rows,
`(lat_bucket=33, lon_bucket=-61)` and `(lat_bucket=40, lon_bucket=-70)`.
Worse, this then broke a *different*, previously-passing test in the same
class (`test_returns_none_when_erddapy_missing`, which mocks the `erddapy`
import to fail) because the cache-first check runs before `erddapy` is
even imported — a leftover cache row from the polluting test made the
mocked-failure test return cached data instead of exercising the
(intentionally broken) import path.
  - Purged both rows from `gateway.db` (`DELETE FROM ww3_realtime_cache`),
    confirmed empty afterward.
  - Fixed root cause: added the same `monkeypatch.setattr(db_mod,
    "DB_PATH", ...)` + `db_mod.init_db()` autouse fixture the other
    isolated test files already use, to `tests/test_era5.py`.
  - Full suite re-run clean: **325 passed** (was 314 passed / 1 skipped
    before this Set — the 11 new tests are the two new test files above;
    the previously-skipped ERA5 test also now runs and passes since CDS
    auth works). 324.36s. `gateway.db`'s `ww3_realtime_cache` confirmed
    still empty after this run — isolation fix holds.
