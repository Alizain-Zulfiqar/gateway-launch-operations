# Gateway Launch Operations
# User Guide
## Last updated: Pre-28B-2 (Forecast station transparency patch)

## 1. Application Overview and Purpose

Gateway Launch Operations is a desktop planning tool for offshore rocket
launch operations. It helps operational planners answer three core
questions:

- **Where can we launch?** Evaluate candidate ocean launch sites against
  weather climatology, buoy observations, and forecast data.
- **When can we launch?** Produce month-by-month launch probability
  profiles and near-term GO/NO-GO forecasts for a chosen site, vehicle,
  and platform combination.
- **What will it cost to get there?** Estimate voyage duration and towing
  economics from a staging port to the launch site.

Everything is organized around the left-hand navigation sidebar:
Projects, Sites, Analysis, Vehicles, Launchers, Comparison, NDBC
Stations, Forecast, Ports, Vessels, Reports, History, and Settings.
All data is stored locally on your machine — no account or server is
required. An internet connection is needed only when fetching live buoy
or historical weather data.

## 2. First-Time Setup Checklist

1. **Launch the application.** On first run it creates its local
   database and folders automatically.
2. **Open Settings** (gear icon at the bottom of the sidebar) and review
   the defaults: GO threshold, buoy search radius, towing speed, fuel
   price, tug rates, port fees, and weather contingency. Adjust any that
   don't match your operation.
3. **Check the vehicle library.** Open the Vehicles section and confirm
   the launch vehicles you plan to analyze are present with sensible
   weather limits. You can edit any vehicle or add your own.
4. **Check the platform list.** Open the Vessels section and confirm the
   Gateway platform variants (S, X, XL) are listed. Gateway S drafts are
   operator-confirmed; X and XL specifications are still unverified — see
   Section 12.
5. **Import the port index if you plan to use voyage planning.** The
   Ports section relies on the World Port Index data file; if ports are
   missing, ask your administrator to run the port import.
6. **Create your first project** (see Section 3) so your candidate sites
   and reports stay organized.

### Running the test suite

Always run tests using the project virtual environment, not the system
Python interpreter:

    venv\Scripts\activate
    python -m pytest

Or use the runapp.bat shortcut:

    runapp.bat test

The test suite requires numpy, PyQt6, and fpdf2 which are installed in
the venv but not in the system Python. Running `py -m pytest` without
activating the venv will produce false failures for these libraries.

## 3. How to Create a Project and Add Candidate Sites

**Create the project.** Open the Projects section. The left panel lists
existing projects; click the create button to start a new one. Give it a
name, an optional code name, a description, a status (active, planning,
on hold, completed, or cancelled), and an optional launch window date
range. Save the project.

**Add sites.** Open the Sites section. In the default "All Sites" view,
enter a site name and its coordinates. Coordinates are accepted in most
common formats (decimal degrees, degrees-minutes, degrees-minutes-
seconds, with or without hemisphere letters) and are displayed in
degrees and decimal minutes. Remember the sign convention: north
latitude and east longitude are positive; south latitude and west
longitude are negative. Click **Apply & Save Site** — a site must be
saved before it can be analyzed. Each saved site is automatically
assigned a short coordinate code (for example N32W061) used in report
filenames.

**Attach sites to the project.** In the Projects section, add your saved
sites to the project as candidates. Each candidate carries a status
(candidate, approved, final, or rejected) that you update as the
evaluation progresses. Every status change is kept in the site's history
with an optional note and supporting document, which you can review at
any time through the History column.

**Review by project.** Back in the Sites section, switch the toggle at
the top to "By Project" for a read-only view filtered to one project's
candidates, including their current status and history count.

**Platform contracts.** A project can be linked to a platform (vessel)
contract — the agreement that defines the vessel's warranted operating
limits for a customer. Linking a contract lets the analysis run a
separate vessel pre-check against those warranted limits (see Section 5).
Each vessel carries a fixed vessel code (Gateway S = 0100, Gateway X =
0101, Gateway XL = 0102), and contracts are identified by a code of the
form CUSTOMER_VESSEL_STARTDATE_ENDDATE (e.g. LM1_0100_10012026_09302027).
The contract document itself stays in its authoritative location — the
application stores only a link (web URL or network path) to it.

**Vehicles Used column.** Both Sites views include a "Vehicles Used"
column that records which launch vehicles have been analyzed at each
site. It fills in automatically as you run analyses (see Section 4): one
vehicle shows its name, two show both, and three or more show the most
recent plus a "+N more" you can hover for the full list with dates. A
dash means no analysis has been run there yet.

## 4. How to Run a Site Analysis (Ad Hoc vs. Project-Linked)

**Ad hoc analysis** is the quickest path: pick a saved site, choose a
vehicle and platform, open the Analysis section, and click **Run
12-Month Profile**. The tool computes a launch probability for every
month of the year and fills the results table with the probability,
verdict, and limiting parameter for each month. The vehicle picker
remembers the last vehicle you analyzed at each site and pre-fills it
the next time you return to that site.

**Project-linked analysis** follows the same steps, but you associate
the output with a project when you generate the report (see Section 8),
so the analysis is filed under the project's name and numbering. Note
that the Analysis section itself does not yet follow an "active
project" — see the deferred item in Section 12.

Two analysis modes are available:

- **Historical mode** uses long-term climatology and ship/buoy
  observation archives over a year range you select. Use it for seasonal
  planning: "Which months are workable at this site?"
- **45-day mode** uses recent buoy observations near the site. Use it
  for near-term campaign planning where current conditions matter more
  than long-term averages.

When you are done, click **Export Analysis PDF** to produce a formatted
report of the 12-month profile.

## 5. Understanding the GO/NO-GO Result and Calculation Basis Panel

Each analyzed month receives an overall probability that weather will be
within your vehicle's limits, shown as a percentage with a color-coded
verdict:

- **GO** (green) — probability 70% or higher. A launch window this month
  is likely.
- **MARGINAL** (amber) — probability between 45% and 69%. Workable, but
  expect weather holds and schedule risk.
- **NO-GO** (red) — probability below 45%. Weather is likely to exceed
  vehicle or platform limits.

**GO in the Forecast section means something slightly different.** In the
month-by-month analysis above, the percentage is a *probability*. In the
Forecast section (Section 6) the "GO" figure is instead the *fraction of
the forecast hours in which every one of the vehicle's thresholds is met
at the same time* — for example "58 of 72 h (81%)" means 58 of the next
72 forecast hours are simultaneously within the wind, gust, wave, and
swell limits. Same GO/MARGINAL/NO-GO color scale, but counted over
forward-looking hours rather than estimated as a monthly probability.

The **limiting parameter** column tells you which single weather
parameter drags the month down the most — for example wind gusts or
swell height. This is the first thing to look at when a month is
marginal: it tells you whether a different vehicle, platform, or season
would help. The limiting parameter is always drawn from the parameters
that actually counted toward the score, so with direction parameters
excluded (the default) it is always one of the five magnitude
parameters — wind speed, wind gust, sea wave height, swell height, or
swell period. A direction parameter can only appear here if you have
explicitly included it.

Below the table, a **Calculation Basis** panel lays out exactly what went
into the run, in two columns. The left column shows the site (name,
coordinates, coordinate code, bounding box, latitude band), the vehicle
(class, recovery mode, provider), and the platform (hull type, motion
factor, maximum operating sea state). The right column shows the analysis
mode and year range, the era confidence weight, the confidence rating,
the exact vehicle limits used, the parameter weights that were applied
(as percentages), and the data source behind each parameter. Every
parameter is tagged **INCLUDED** or **EXCLUDED** so you can see at a
glance what the probability was actually based on. An EXCLUDED parameter
shows a dash ("—") in place of its threshold value and weight — its
limits played no part in the result, so no number is displayed for it.
Before you run anything the panel simply reads "No analysis run yet."

**Vessel pre-check.** When the project is linked to a platform contract,
the analysis also shows a separate **VESSEL** verdict (GO / MARGINAL /
NO-GO) alongside the vehicle result. This checks the weather against the
vessel's warranted operating limits from the contract. Where the
contract and the vehicle both constrain the same parameter, the more
conservative (tighter) of the two governs the vessel verdict — this is a
safety rule for the vessel-vehicle pairing. If the contract's limits have
not been verified against the signed document, the vessel verdict carries
an "⚠ Unverified envelope" warning; treat it as provisional until an
approver confirms the values. If no contract is linked, the row reads
"VESSEL: No contract linked" so you know the pre-check did not run.

Wind direction, sea direction, and swell direction variability are
**excluded from the overall score by default**; they are of secondary
importance for most sites and the direction tolerance data is the least
reliable. Three checkboxes above the results table — Wind direction, Sea
direction, Swell direction — let you include any of them. They start
unchecked (excluded). Check one and re-run, and that parameter is folded
into the weighting (the weights automatically rebalance to still total
100%) and shows as INCLUDED in the Calculation Basis panel.

## 6. How to Use NDBC Buoy Data and Forecast Integration

**Finding buoys.** Open the NDBC Stations section with a site selected.
The tool searches the national buoy network within the configured radius
(200 nautical miles by default) and shows the results on a map and in a
table: station ID, distance, bearing, and what each station reports.
Note that not every buoy reports wave spectra — swell data comes only
from stations equipped for it, and the tool checks availability before
using one.

**Near-term forecast — where the data comes from.** Open the Forecast
section and click Run Forecast Analysis. The forecast is built from live,
forward-looking model data:

- **Wind** comes from the U.S. National Weather Service (NWS NDFD). NWS
  covers U.S. coastal waters only; outside that coverage the wind portion
  is shown as a model estimate rather than a confirmed NWS forecast.
- **Wave and swell** come from the Open-Meteo Marine service, which is
  global.
- **NDBC buoys** are used as an optional *observed overlay* and for
  station blending when you have selected stations in the NDBC tab — they
  are supplementary to the model forecast, not the primary source.

A row of **data source badges** at the top of the results tells you
exactly what each run used: a green check means that source supplied real
data (e.g. "Wave: Open-Meteo ✓"), blue means a model estimate ("Wind:
Model est."), red means a source was unavailable, and gray means no buoy
overlay was applied. If every source is unavailable for a location, a
clear message explains why (for example, NWS coverage is U.S.-only) and
suggests checking your connection.

**The horizon selector controls the forward-looking window.** Choose 24,
48, 72 hours, 5 days, or 7 days. This selects how many hours of the
*model forecast* to analyze — it is a look-ahead window, not a window
over past buoy observations. After the first run, changing the horizon
re-analyzes the already-fetched data instantly, without another network
call. Each horizon carries a confidence score from 5 (24-hour, high
confidence) down to 2 (7-day, low confidence) — treat the 5- and 7-day
outlooks as directional only.

**GO window.** The banner reports how many of the forecast hours meet all
of the selected vehicle's thresholds at once — for example "58 of 72 h
(81%)". Select a vehicle in the Analysis section first; without one the
section asks you to choose a vehicle before it can compute the GO window.

**How this feeds analysis.** In 45-day analysis mode, nearby buoy
observations replace the climate baseline wherever real data is
available, which sharpens the result for sites with good buoy coverage.

Station selections made in the NDBC section are cleared automatically
each time the application starts. This prevents stale buoy selections
from a prior session appearing unexpectedly in a new session.

The Forecast section shows a status line indicating which NDBC stations,
if any, are contributing to the buoy overlay for the current run. If no
active site is set, station distances default to 1.0 NM and an amber
warning appears noting that blend weights are equal rather than
distance-weighted.

Use the **Clear Buoy Overlay** button to remove all selected stations
from the current run without visiting the NDBC section.

## 7. Port Proximity and Voyage Economics

Open the Ports section with a site selected to see the nearest suitable
staging ports, with distance, bearing, harbor size, shelter, depths, and
fuel availability drawn from the World Port Index.

If a port isn't relevant to your plan, click its **✕ Remove** button to
drop it from the list for the session; a short "Port removed" bar with an
**Undo** appears if you change your mind, and a **Show All Ports** button
brings back everything you've removed. This only affects the on-screen
list — nothing is deleted from the database, and a fresh search resets it.

Select a port to build a voyage estimate. Enter or accept the defaults
for towing speed, daily fuel consumption, fuel price, number of tugs,
tug day rates, port fees, crew costs, and a weather contingency
percentage. The tool computes the great-circle route with intermediate
waypoints, transit time with and without contingency, and a cost
breakdown (fuel, tugs, port fees, crew) for one-way and round-trip
voyages. A departure date can be attached to produce a dated waypoint
schedule, and the whole plan can be exported as a voyage PDF from the
Reports section.

The default towing figures reflect a semi-submersible platform under tow
at about 6 knots; update them in Settings to match your actual tow plan.

## 8. How to Generate and Manage Reports

Reports are generated from the Reports section. Choose the report type
(site analysis, voyage plan, or multi-site comparison), the site, and
optionally the project it belongs to. Project-linked reports are named
automatically from the project code name, the site's coordinate code,
and a running sequence number, so files sort and file themselves
predictably. If the project is missing required fields (such as a code
name), the tool will ask you to complete them first.

The saved report list below shows every report generated, filterable by
project, type, and archived status. Right-click a report to open it,
archive or unarchive it, or delete it. An "Archive All Filtered" button
tidies up an entire filtered set at once. Archived reports stay on disk;
archiving only hides them from the default view.

## 9. Expense Ledger and Invoice OCR

The expense ledger and invoice OCR features are **not yet implemented**
(planned for Instruction Set 30). When delivered, this section will
cover recording campaign expenses, scanning invoices, and reconciling
voyage cost estimates against actuals. There is nothing to configure or
use yet.

## 10. Data Sources and Confidence Ratings Explained

The tool draws on several data sources and always tells you which one
produced each number:

- **NDBC buoys (real-time)** — live wind and wave observations from
  moored buoys near your site. The best available source when a buoy is
  close by. Used in 45-day mode and the Forecast section.
- **NCEI Global Marine archive** — more than a century of ship and buoy
  weather reports, used for historical wind statistics.
- **ERA5 reanalysis** — a global weather model reconstruction used for
  historical swell characteristics. Requires a configured data key;
  ask your administrator if swell data shows as model-based when you
  expect reanalysis data.
- **Climate model (ICOADS baseline)** — built-in latitude-band
  climatology with seasonal adjustment. This is the fallback whenever no
  observational source covers a parameter.

Every analysis carries a **confidence rating** — high, moderate, low, or
model — reflecting how much of the result came from real observations
versus the built-in climatology, and, in historical mode, how dense the
observation record is for the selected years (data before 1960 is
sparser and is weighted accordingly). A "model" rating does not mean the
result is wrong; it means you should treat it as a planning estimate and
firm it up with buoy or forecast data as the campaign approaches.

## 11. Coordinate Convention Reference

All coordinates in the application are WGS-84 decimal degrees with this
sign convention:

- **Positive latitude = North. Negative latitude = South.**
- **Positive longitude = East. Negative longitude = West.**

Examples: 28.5°N, 80.6°W is entered as latitude 28.5, longitude −80.6.
32.6°S, 61.1°E is entered as latitude −32.6, longitude 61.1.

Coordinate entry fields accept decimal degrees, degrees and decimal
minutes, or degrees-minutes-seconds, with hemisphere letters or signs.
The convention is validated at every entry point — the tool will reject
out-of-range values rather than guess. The sidebar shows a permanent
reminder of the convention.

## 12. Known Limitations and Deferred Features

- DEFERRED: Active project context in Analysis section. Project-aware
  vehicle pre-fill via project_sites.preferred_vehicle_id is not yet
  implemented. The Analysis section currently pre-fills vehicle from
  site_vehicles last-used lookup only (no project context). This must be
  addressed when global session_state active project pattern is
  established across all sections.
- **Direction parameters excluded by default.** Wind, sea, and swell
  direction variability are excluded from the overall probability by
  default. The three Analysis-screen checkboxes default to unchecked and
  the five magnitude parameters carry the full weighting; check a
  direction box and re-run to include it (the weights rebalance
  automatically). This is fully in effect as of this release.
- **Expense ledger not implemented.** See Section 9 (planned for Set 30).
- **Contract UI (Pre-28B-2):** The Contracts section for creating and
  managing platform contracts is implemented in Pre-28B-2. For now,
  contract records and their warranted limits exist in the database and
  drive the vessel pre-check, but there is not yet an in-app screen to
  create or edit them.
- **Gateway X and Gateway XL drafts unverified.** Only Gateway S transit
  and launch drafts are operator-confirmed. Treat X/XL depth and draft
  results as provisional.
- **Swell data coverage varies.** Many buoys do not report wave spectra;
  where none is available, swell figures fall back to the climate model.
- **Forecast horizons beyond 72 hours are low-confidence** and should be
  used for situational awareness, not commitment decisions.
- **Database backups.** The application keeps full database backups in
  the backups folder whenever a data migration is run. To restore one,
  close the application, copy the backup file back over the main
  database file, and restart.
