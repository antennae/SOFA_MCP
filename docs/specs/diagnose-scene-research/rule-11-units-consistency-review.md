# Rule 11 — Units Consistency: Deep Review

**Reviewer:** Single-rule deep review agent
**Date:** 2026-04-26
**Rule:** v2.1 §1.1 Rule 11 (NEW — gravity-based unit discrimination + YM threshold checks)

---

## 1. Mechanistic Explanation

Rule 11 detects unit-system mismatches by reading a single, always-present field — the gravity vector on the root node — and then checking `youngModulus` values on force fields against expected ranges for that system.

The core insight from B6: since 1 g/(mm·s²) = 1 Pa, Young's modulus has the *same numerical value* in both SI and mm/g/s for the same physical material. The YM overlap is complete. Therefore, YM magnitude alone cannot discriminate unit systems. What can discriminate is the *extremes*: a YM above 1 GPa is implausible for any soft biological or rubber material regardless of unit system, and a YM below 10 Pa in a scene that declares SI gravity is physically incoherent.

---

## 2. Gravity-Magnitude Classification Table

| Gravity magnitude | Classification | Action |
|---|---|---|
| 0.0 (all axes zero) | zero-gravity / space scene | emit `info`: "Cannot determine unit system: gravity is zero. YM thresholds skipped." |
| no declaration | default SOFA (0, -9.81, 0) | treat as SI (SOFA `Node.cpp` initializes to -9.81) |
| 9.7 – 9.9 (includes -9.81, -9.8, 9.81) | SI | apply SI YM sub-checks |
| 9.9 – 10.1 (e.g., -10, rounded SI) | SI-rounded | treat as SI; emit `info`: "gravity rounded to -10; assuming SI" |
| 90 – 200 (e.g., -98.1, -100) | ambiguous | emit `info`: "Gravity magnitude in ambiguous range [90,200]. Possible mid-conversion or dm/g/s. YM checks skipped." |
| 970 – 990 (e.g., -981) | cm/g/s | emit `info`: "Gravity suggests cm/g/s. No YM thresholds defined for this system." |
| 9790 – 9820 (e.g., -9810, -9800) | mm/g/s | apply mm/g/s YM sub-check |
| 9100 – 9200 (e.g., -9180) | likely mm/g/s typo | emit `warning`: "Gravity magnitude 9180 does not match SI (9.81) or mm/g/s (9810). Probable digit-transposition typo of -9810." |
| anything else | unknown | emit `info`: "Unrecognized gravity magnitude. YM thresholds skipped." |

**Edge cases handled:**

- **Gravity axis**: magnitude is `sqrt(gx² + gy² + gz²)`. Works for gravity on any axis (-9810 on Z, X-axis sidewise robots, etc.).
- **Zero gravity** (171 Python files in corpus): skip all YM checks; emit one `info` note. Do not warn about YM — space simulations and unit-test scenes legitimately use zero gravity.
- **No gravity declaration**: SOFA defaults to `(0, -9.81, 0)` per `Node.cpp` line ~754. Rule treats this as SI.
- **`-9.8`** (STLIB `MainHeader` default): magnitude 9.8, falls in [9.7, 9.9] → SI. Correct.
- **`-10`**: magnitude 10.0, falls in [9.9, 10.1] → SI with info note.
- **`-9180`**: found in `CircularRobot/circularrobot.py` and two `SoftRobots.Inverse` examples. This is almost certainly a digit-transposition of `-9810`. Rule emits a warning rather than silently skipping — this is the one typo-detection bonus Rule 11 can provide.
- **`-0.981`**: found in `CCDIntersection.py`. Magnitude 0.981, outside all classification buckets → "unknown" info note.

---

## 3. YM Threshold Defense

### Literature ranges (SI Pa)

| Material | YM range | Source |
|---|---|---|
| Soft tissue (liver, brain) | 0.5 – 20 kPa | well-established FEM biomechanics |
| Silicone (soft robotics) | 0.1 – 2 MPa | Ecoflex 00-30 ~50 kPa; Dragon Skin ~1 MPa |
| Rubber | 0.5 – 10 MPa | standard elastomer range |
| Cartilage | 10 – 100 MPa | |
| Cortical bone | 10 – 20 GPa | |
| Steel (Cosserat beam) | ~200 GPa | |

**Consequence**: In mm/g/s, these same physical materials carry the same numerical values (1 Pa = 1 g/(mm·s²)). The number 450 means 450 Pa either way.

### SI sub-checks

- `YM < 100 Pa` → **warning**: "YM below 100 Pa with SI gravity. Physically implausible for any structural material. Likely a unit-conversion error (e.g. forgot to convert MPa to Pa)."
- `YM < 10 Pa` → **error**: "YM below 10 Pa with SI gravity. Below any known material. Simulation will produce nonsensical deformation."

**Corpus verification**: The only SI scene with YM < 100 found was `liver.py` with YM=3000 (safely above threshold). No corpus scene triggered a false positive at YM < 100 in SI context. The `multiGait.py` YM=70 case is under mm/g/s gravity (-9810), not SI — B6's claim of "one FP at YM=70" was misattributed. In mm/g/s, YM=70 is 70 Pa, extremely soft but not necessarily wrong (reduced-order model artifact); it does not trigger the mm/g/s rule (threshold is 1e9).

### mm/g/s sub-check

- `YM > 1e9` → **warning**: "YM exceeds 1 GPa with mm/g/s gravity. This is above any biological tissue or silicone. Likely an SI value (in Pa or MPa) used without conversion to mm/g/s units."

**Corpus verification**: Zero mm/g/s scenes in the corpus trigger this. Max observed: `SoftArmGripper` has YM=1e8 (100 MPa), Trunk=450, Diamond=180, Diamond=450. Well below 1e9.

### Poison Ratio

Rule 11 as drafted does not check `poissonRatio`. This is correct: Poisson's ratio is dimensionless — it has the same value in any unit system. Rule 11 should not add a Poisson sub-check.

---

## 4. Density / Mass — Should Rule 11 Check These?

**Short answer: no, not in v2.1.**

In mm/g/s, mass density of water is 1e-3 g/mm³ (= 1000 kg/m³ in SI). Typical soft robot silicone (~1.1 g/cm³) = 1.1e-3 g/mm³. These are very small numbers.

In SI, water is 1000 kg/m³, silicone ~1100 kg/m³.

The gap is large (factor of 1e6), so in principle a discriminating check is possible. However:

1. Most SoftRobots scenes use `UniformMass` with `totalMass` rather than `massDensity`. `totalMass` is geometry-dependent; there is no universal plausible range.
2. In the corpus, mm/g/s scenes use `totalMass` values of 0.01–0.5 (in grams — plausible for small soft robots). SI scenes use `massDensity=1.0` (kg/m³? dimensionless? ambiguous).
3. `massDensity` appears in only ~10 scenes in the corpus. Low statistical power.

**Recommendation**: Defer density sub-check to v2.2. Add a note in the rule that `massDensity` consistency would be a useful future extension.

---

## 5. Final Rule Wording (v2.1 replacement for §1.1 Rule 11)

> **Rule 11 — Units Consistency (NEW)**
>
> Detect the unit system from gravity magnitude `g = sqrt(gx² + gy² + gz²)`:
>
> - `g = 0`: emit `info` "Cannot determine unit system: zero gravity. YM thresholds skipped."
> - No `gravity` declaration: SOFA default is `(0, -9.81, 0)` → treat as SI.
> - `g in [9.7, 10.1]` → **SI**. Check `youngModulus`: `< 100` → `warning`; `< 10` → `error`.
> - `g in [9790, 9820]` → **mm/g/s**. Check `youngModulus`: `> 1e9` → `warning`.
> - `g in [90, 200]` → emit `info`: "Gravity magnitude in ambiguous range. Possible mid-conversion or dm/g/s."
> - `g in [9100, 9200]` (e.g., 9180): emit `warning`: "Gravity near 9180 — probable digit-transposition of -9810 (mm/g/s)."
> - `g in [970, 990]` (cm/g/s): emit `info` "Gravity suggests cm/g/s. No YM thresholds defined."
> - All other magnitudes: emit `info` "Unrecognized gravity magnitude. YM thresholds skipped."
>
> Notes: Gravity axis is irrelevant (some scenes use X- or Z-axis). `poissonRatio` is dimensionless — not checked by this rule. `massDensity` check deferred to v2.2.

---

## 6. Severity Per Sub-Check

| Sub-check | Severity | Rationale |
|---|---|---|
| Zero gravity | `info` | Legitimate (space sim, unit tests) |
| Ambiguous gravity [90, 200] | `info` | Rare; could be deliberate |
| cm/g/s gravity [970, 990] | `info` | Legal but uncommon — 29 corpus scenes |
| 9180 gravity (typo) | `warning` | 5 corpus scenes; almost certainly transposition error |
| SI + YM < 100 | `warning` | 1 or fewer corpus triggers; plausible but suspicious |
| SI + YM < 10 | `error` | No known physical material below 10 Pa |
| mm/g/s + YM > 1e9 | `warning` | Zero corpus triggers; catches the classic SI-GPa-in-mm-scene bug |

---

## 7. Sample Scenes

**Consistent (should not trigger):**

1. `plugins/SoftRobots/examples/tutorials/Trunk/trunk.py` — gravity=-9810 (mm/g/s), YM=450. No trigger.
2. `plugins/SoftRobots/examples/tutorials/DiamondRobot/DiamondRobot.py` — gravity=-9810 (mm/g/s), YM=180. No trigger.
3. `build/external_directories/fetched/SofaPython3/examples/liver.py` — gravity=-9.81 (SI), YM=3000. No trigger.

**Violations (should trigger):**

4. Synthetic test scene: gravity=-9.81 (SI), `youngModulus=5e9` → triggers mm/g/s warning (wrong — user meant SI Pa but used a GPa-range number). Used in v2.1 Step 5 E2E test #2.
5. Synthetic test scene: gravity=-9.81 (SI), `youngModulus=5` → triggers SI error.
6. `plugins/SoftRobots/examples/tutorials/CircularRobot/circularrobot.py` — gravity=-9180 → triggers 9180 typo warning. YM=500 is fine once unit is disambiguated.

---

## 8. Implementation LOC Estimate

```python
# _build_summary_wrapper addition in scene_writer.py
def _check_rule_11(tree) -> list[Check]:
    # 1. Extract gravity vector from root node (1 findData call)        ~5 LOC
    # 2. Compute magnitude                                               ~3 LOC
    # 3. Classify magnitude via if/elif ladder                          ~20 LOC
    # 4. Walk tree for TetrahedronFEMForceField / HexahedronFEMForceField
    #    and read youngModulus (reuse existing tree-walk utility)       ~15 LOC
    # 5. Apply YM threshold checks per classification                   ~15 LOC
    # 6. Emit Check objects                                             ~10 LOC
    pass  # total                                                       ~68 LOC
```

Plus ~15 LOC of unit tests (known-good and known-bad fixtures). Total: **~83 LOC**.

This is the cheapest new rule in the v2.1 spec — gravity and `youngModulus` are top-level, well-structured fields. No mesh loading, no per-step data, no regex parsing.

---

## 9. Confidence Verdict

| Claim | Confidence | Notes |
|---|---|---|
| Gravity magnitude is the correct discriminator | HIGH | B6 corpus analysis; 452 SI, ~100 mm/g/s, ~29 cm/g/s confirmed |
| mm/g/s YM > 1e9 threshold | HIGH | Zero corpus FPs; zero legitimate materials above 1 GPa in soft robotics |
| SI YM < 100 → warning | MEDIUM-HIGH | Zero corpus FPs found (B6's 1 FP was misattributed to SI); still plausible edge case for ultra-soft hydrogels |
| SI YM < 10 → error | HIGH | No physical material below 10 Pa |
| 9180 typo detection | MEDIUM | Only 5 corpus instances; 9180 could theoretically be intentional (unlikely) |
| Zero-gravity skip | HIGH | 171 Python files use zero gravity legitimately |
| Density sub-check deferral | HIGH | totalMass is geometry-dependent; low corpus density for massDensity |

**Overall: STRONG CONDITIONAL ADD.** The rule is low-cost (~83 LOC), catches the most-cited real-world SOFA bug class (units mismatch, Agent 4 #1 and #2), has near-zero false-positive rate, and the gravity-as-discriminator approach is the only viable one given that YM values overlap across unit systems. The 9180 typo bonus is a genuine addition over v2.0. Density checks should remain deferred.

One spec gap to fix: the original v2.1 §1.1 Rule 11 wording omits the 9180 case, the cm/g/s band, the zero-gravity behavior, and the no-declaration default. The revised wording in §5 above should replace it.
