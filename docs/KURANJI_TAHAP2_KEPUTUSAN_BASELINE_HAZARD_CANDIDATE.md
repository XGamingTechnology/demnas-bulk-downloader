# Keputusan Baseline Hazard Candidate Tahap 2 DAS Kuranji

## Status

Tahap 2 telah menyelesaikan sensitivity analysis untuk definisi drainage network, GFI flood-prone threshold, dan parameter Fuzzy Large. Hasil utama tahap ini dikunci sebagai **baseline hazard candidate**, bukan final calibrated hazard, karena belum tersedia standard flood map independen untuk kalibrasi classifier threshold.

## 1. Drainage Network

Primary drainage network:

- method: local `channel_FAt`;
- minimum contributing area: 6 km2;
- conditioning: BREACH100;
- basis: hasil kalibrasi Tahap 1 terhadap RBI dan comparison terhadap default `channel_ASk`.

Default GFA `channel_ASk` disimpan sebagai sensitivity/reference, tetapi tidak dipakai sebagai primary network karena menghasilkan jaringan terlalu padat terhadap RBI dan tidak memperbaiki masalah WD negatif.

Full GFI comparison:

| Method | Channel cells DAS | Resolved routing | Manual -0.53 prone area | WD positive | WD negative | Physical WD+ area |
|---|---:|---:|---:|---:|---:|---:|
| GFA channel_ASk | 20,728 | 100.000% | 74.175 km2 | 21.1% | 78.9% | 15.683 km2 |
| Local FAt 6 km2 | 8,274 | 99.862% | 60.138 km2 | 22.0% | 78.0% | 13.249 km2 |

Kesimpulan: WD negatif tidak terutama disebabkan local drainage adaptation.

## 2. GFI Baseline

Primary GFI calculation follows active GFA logic:

- `H` = terrain elevation minus elevation of first hydrologically connected downstream channel;
- `Ariver` = flow accumulation on the connected channel;
- `hr = A_km2^n`;
- `n = 0.354429752`;
- `GFI_raw = ln(hr/H)`;
- normalized GFI mapped to [-1,+1] for compatibility with GFA classifier behavior.

Baseline QC:

- analysis cells: 3,238,533;
- resolved routing: 3,234,064 (99.862%);
- unresolved: 4,469;
- negative H: 0;
- zero H: 8,274 channel cells;
- GFI raw range: -6.638383 to 13.411668;
- normalized range: -1 to +1.

## 3. Flood-Prone Threshold Sensitivity

Manual GFA classifier threshold `-0.53` yields:

- flood-prone area: 60.138 km2;
- positive WD: 22.03%;
- negative WD: 77.97%.

The mathematical boundary `WD=0` is equivalent to:

- `hr = H`;
- `GFI_raw = 0`;
- normalized GFI approximately `-0.337819` for this baseline dataset.

The corresponding positive-WD domain is 13.249 km2 (about 5.90% of the rasterized DAS analysis area).

This threshold is a physical-consistency boundary, not an empirical calibration threshold.

## 4. Fuzzy Hazard Sensitivity

Four scenarios were evaluated:

| Scenario | Flood-prone mask | Spread | Area km2 | Low % | Medium % | High % | Raw negative WD |
|---|---|---:|---:|---:|---:|---:|---:|
| M175 | GFI norm > -0.53 | 1.75 | 60.138 | 85.79 | 7.08 | 7.13 | 675,819 |
| M250 | GFI norm > -0.53 | 2.50 | 60.138 | 86.67 | 5.03 | 8.30 | 675,819 |
| P175 | GFI raw > 0 / WD > 0 | 1.75 | 13.249 | 35.49 | 32.13 | 32.38 | 0 |
| P250 | GFI raw > 0 / WD > 0 | 2.50 | 13.249 | 39.51 | 22.81 | 37.67 | 0 |

## 5. Primary Baseline Hazard Candidate

Primary scenario for reporting Stage 2 baseline:

**P175**

Definition:

- drainage network: local FAt 6 km2;
- flood-prone domain: physical-positive domain (`WD > 0`, equivalent to `GFI_raw > 0`);
- WD: `hr - H`;
- Fuzzy Large midpoint: 1.125 m;
- Fuzzy Large spread: 1.75;
- hazard index range: 0–1;
- class thresholds:
  - low: H <= 0.333;
  - medium: 0.333 < H <= 0.666;
  - high: H > 0.666.

### Rationale

1. Spread 1.75 follows the explicit written parameter in MODUL TEKNIS KRB BANJIR-2.
2. P175 contains no negative WD values.
3. It preserves the module's WD-to-fuzzy-hazard structure.
4. The flood-prone boundary is physically interpretable, while being clearly labelled as a physical-consistency boundary rather than empirical calibration.
5. It avoids silently converting a very large negative-WD domain into zero-depth hazard.

## 6. Sensitivity Products Retained

The following remain mandatory sensitivity outputs:

- M175: closest diagnostic reproduction of the module manual threshold with written spread;
- M250: manual threshold with spread matching the figure/table behavior more closely;
- P250: physical-positive mask with alternative spread.

These products are retained for Stage 3 external validation.

## 7. Validation Status

P175 is **not yet called final calibrated hazard**.

Final validation requires comparison against independent observed flood extent, preferably:

1. historical flood map not used in parameter selection; and/or
2. observed flood extent from the November 2025 event.

Because the available local data folder currently contains no independent flood/genangan calibration map, the November 2025 event will be used as external validation rather than hidden calibration.

Stage 3 must compare at minimum:

- P175 vs observed flood;
- M175 vs observed flood;
- P250 vs observed flood;
- optionally M250 vs observed flood.

Metrics should include overlap area, precision, recall, F1, hit rate, and spatial false-positive/false-negative patterns where the observed flood product supports those calculations.

## 8. Stage 2 Remaining Deliverables

Before Stage 2 is administratively complete:

- package primary P175 raster outputs;
- calculate area by hazard class for the full DAS;
- calculate Pauh and Kuranji statistics;
- calculate per-kelurahan statistics;
- export CSV tables;
- prepare map-ready layers;
- create report-ready Stage 2 method/results narrative;
- retain all sensitivity rasters and QC JSON/CSV.
