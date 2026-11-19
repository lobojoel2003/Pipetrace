# Importing your inventory

Pipetrace reads the spreadsheet you already keep: EPA's service line inventory
template, your state's version of it, or an export from a billing or GIS system.
Only a street address is required.

## In the staff area

**Staff → Imports → Upload inventory**, then four steps:

1. **Upload** an `.xlsx` or `.csv` file (old `.xls` files must be re-saved as `.xlsx`).
   Choose what the file should do:
   * *Update matching lines and add new ones* — for regular updates. Lines are matched
     by service line ID, or by address when the file has no ID column.
   * *Replace the whole inventory* — lines missing from the file are hidden from the
     public site (not deleted).
2. **Match columns.** Pipetrace finds the sheet and the header row by itself, even
   under title rows and two-row group headers like EPA's "System-Owned Portion /
   Customer-Owned Portion", and skips a row of allowed codes under the header. Check
   each guess against the sample values and fix anything that's wrong. Columns you
   don't map are kept with each line as extra information.
3. **Check values.** Every distinct value in the material, classification, connector
   and replacement columns is listed with how it will be read: `Pb`, `LSL`, `L` and
   `Lead` all mean lead; `Cu`, `NL - Copper` mean copper; `GRR`, `GALV-RR` mean
   galvanized requiring replacement; `U`, `UNK`, `?` mean unknown. Codes that are
   ambiguous (`PB` is usually lead but sometimes polybutylene) or unrecognised are
   highlighted for you to confirm.
4. **Preview and import.** See how many lines will be added, updated, left alone or
   hidden; the classification counts; rows with errors; and lines where the file's
   own classification contradicts the materials. Then import.

Your column and value choices are remembered: the next file with the same columns
starts with them filled in.

## Classification rules

If you map an overall classification column, Pipetrace uses it. Otherwise it works
the classification out from the two portions, following the Lead and Copper Rule
Improvements:

* **Lead** if either portion is lead (lead-lined galvanized counts as lead).
* **Galvanized requiring replacement** if either portion is galvanized, unless the
  file says the line was *never* downstream of lead and the other portion is known.
* **Not lead** if both portions are known non-lead materials.
* **Lead status unknown** otherwise.

A line marked as replaced (a "replaced" status or a replacement date) is shown as
replaced and not lead.

## Fields Pipetrace understands

| Field | Example headers it recognises |
| --- | --- |
| Service line ID | Service Line ID, SL ID, Account Number, Premise ID, Acct # |
| Street address | Street Address, Location Identifier, Service Address, Service Addr |
| House number + street name | House Number / Street Name (when split) |
| Unit, City, State, ZIP | Unit, Apt, City, Town, State, Zip Code, Postal Code |
| Latitude / longitude | Latitude, Lat, Y / Longitude, Lon, X |
| Utility-side material | System-Owned Portion › Material, Utility Side, Public Side Material |
| Customer-side material | Customer-Owned Portion › Material, Cust Side, Private Side Material |
| Overall classification | Entire Service Line Material Classification, Lead Status, LSL? |
| Galvanized ever downstream of lead | Was Material Ever Previously Lead?, Ever Downstream of Lead |
| Lead connector | Lead Connector, Gooseneck, Pigtail |
| Basis of classification, date verified | Basis of Classification, Verification Method, Date Verified |
| Year installed, year built | Installation Date, Year Built |
| Replacement status, scheduled, date replaced | Replacement Status, Scheduled Replacement, Date Replaced |
| Public note | Notes, Comments |

Schedules can be a date, a year, or text such as "Spring 2027", "Q3 2028" or
"Phase 2"; residents see the text.

Coordinates in a state-plane projection (large numbers) are ignored and the address
is geocoded instead. ZIP codes that Excel stored as numbers (`2134`) get their
leading zero back.

## Placing lines on the map

Lines without coordinates are geocoded after the import. **Staff → Map locations**
runs the U.S. Census Bureau geocoder in batches while the page is open, shows
progress, and lists addresses it couldn't find. Fix those in your spreadsheet and
re-import, or open a line in the admin and type its latitude and longitude.

Set `PIPETRACE_GEOCODER=pelias` and `PIPETRACE_PELIAS_URL` to use your own
[Pelias](https://pelias.io) server instead (for example if addresses must not leave
your network), or `none` to turn geocoding off.

## From the command line

```bash
pipetrace import_inventory inventory.xlsx --show-mapping      # see the detected columns
pipetrace import_inventory inventory.xlsx --dry-run           # check without saving
pipetrace import_inventory inventory.xlsx --mode replace      # import
pipetrace import_inventory export.csv --mapping mapping.json  # override columns
pipetrace geocode                                             # locate new lines
```

`--save-mapping mapping.json` writes the mapping used, as `{"field": "column header"}`,
so a scheduled job can reuse it.

## Exporting

**Staff → Download CSV** (or `/staff/export/inventory.csv`) downloads the current
inventory with EPA-style column names, ready for a state report.

## Try it

`pipetrace/inventory/demo/millbrook-inventory.xlsx` is laid out like EPA's template
and `millbrook-messy.csv` like a billing-system export. Both are fictional.
