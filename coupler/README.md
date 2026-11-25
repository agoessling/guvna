# Four-port coupled-line simulation

The [wideband coupler literature review](literature.md) compares candidate geometries, measured
directivity, and alternatives for the VNA test port.

Run from the checkout on Linux x86-64 with the source-built CPU Palace toolchain. Choose a fresh
output directory. The sample frequencies range from 0.5 to 12 GHz and include 10.525 GHz. The
workflow saves the electric and magnetic fields at 6 and 10.525 GHz for each excitation.

```sh
runs="$HOME/.local/state/guvna/coupler"
bazel run //coupler:solve -- --output "$runs/initial"
bazel run //coupler:solve -- --output "$runs/refined" --refinement 1
```

Use `--frequencies-ghz 0.5 10.525 12 --save-ghz 10.525` for a shorter direct sweep. Each saved
frequency must occur in the sweep. `--order` selects the finite-element polynomial order,
`--tolerance` the GMRES relative tolerance and `--ranks` the MPI process count. The defaults are
order two, 1e-9 and four MPI ranks with one OpenMP thread each. Set `--gap-cells`,
`--length-cells`, `--substrate-cells`, `--strip-cells`, `--air-cells`, or `--side-cells`
to override individual mesh counts. The `trace-edges` preset also takes `--edge-cells` and
`--interface-cells` for the outer strip edges and trace-plane layers.
[Regional mesh study](../geometry/README.md#trace-edge-refinement-study)

Override `--gap`, `--length`, `--width`, `--substrate-height`, `--lid-clearance`, or
`--side-clearance` in mm, or use `--relative-permittivity` for the substrate. For example, this
command isolates a change from 0.22 to 0.35 mm gap at the same reference planes and mesh level.

```sh
bazel run //coupler:solve -- --gap 0.35 --frequencies-ghz 10.525 --save-ghz 10.525 \
  --output "$runs/gap035"
```

The mesh generator supplies the trial geometry, port locations and material properties in mm.
The Palace deck assigns lossless dielectric and air, PEC traces and enclosure, and natural
magnetic boundaries on the non-port portions of both end faces. Each port uses a single uniform
lumped element across the substrate from ground to trace, with a 50 Ω real reference. Assigning
a unique excitation to each port gives four loaded solves per frequency. All reference planes are
at the PCB section ends. [Geometry and port map](../geometry/README.md)

## Output

- `geometry.json`, `model.msh` and `mesh.log` describe the generated coupon.
- `palace.json`, `solver.log`, `version.log` and `postpro/` retain the input and native results.
  Open a volume series in ParaView from `postpro/paraview/driven/excitation_N/excitation_N.pvd`.
- `run.json` records frequencies in GHz, ports, field files and the complex scattering matrix
  as `s[frequency index][output port - 1][input port - 1][real or imaginary]`. Port order is
  1 input, 2 through, 3 near-end pickup and 4 far-end pickup. These physical labels stay fixed
  even where the two pickup responses cross.
- `coupler.s4p` stores all 16 complex coefficients. The Touchstone option line specifies GHz,
  S, real/imaginary pairs and 50 Ω. For a four-port file each frequency has four matrix rows.
  [Touchstone specification](https://ibis.org/touchstone_ver2.0/touchstone_ver2_0.pdf)

Validation checks actual excitation groups, the GMRES convergence reports, all 32 labeled scalar
columns, MPI and thread counts, and the parallel VTK field pieces. At each sampled frequency it
reports the largest absolute complex difference between reciprocal S entries and the largest
singular value of S. A passive network with equal real port references has a largest singular
value no greater than one, including for coherent multiport drive.

Input match and through loss come from S11 and S21. Positive coupling loss and isolation use
−20 log₁₀ of the magnitudes of S31 and S41. Their difference (isolation minus coupling loss) gives
raw directivity. The run record stores this convention in `diagnostics.directivity_ports` as
drive 1, coupled 3 and isolated 4. Sparse direct sampling can miss a null. Run a denser sweep
and compare the same frequency on both meshes before interpreting a narrow isolation feature.

## First simulated coupon

On kratos, Palace v0.19.0 converged for all 40 GMRES solves on each mesh. Wall times include
writing the eight volume field datasets and their boundary counterparts. Each job used four MPI
ranks with one thread per rank on the Intel Core i5-13600K.

| Mesh | Hexahedra | Unknowns | GMRES iterations per solve | Palace wall time | Peak host MiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| Initial | 1,920 | 50,128 | 15–19 | 22.66 s | 480 |
| Refined | 8,840 | 223,350 | 23–29 | 159.52 s | 1,441 |

Selected refined-mesh samples are in dB.

| GHz | Coupling loss | Isolation | Directivity | Input return loss | Through loss |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0.5 | 31.37 | 47.10 | 15.73 | 47.35 | 0.003 |
| 6 | 14.43 | 27.11 | 12.68 | 26.42 | 0.189 |
| 8 | 16.44 | 22.74 | 6.30 | 18.20 | 0.211 |
| 10.525 | 26.07 | 18.96 | −7.11 | 13.35 | 0.307 |
| 11 | 29.39 | 18.55 | −10.84 | 12.92 | 0.331 |
| 12 | 27.80 | 17.98 | −9.82 | 12.48 | 0.373 |

The nominal geometry misses the 30 dB raw-directivity target. At 10.525 GHz the far-end pickup
receives a stronger signal than the designated near-end pickup. Refining changes directivity from
−6.85 to −7.11 dB there. Across the ten default samples the largest directivity change is 0.70 dB,
at 0.5 GHz. Both meshes give a maximum singular value below 1.000001 and a maximum reciprocal
coefficient difference below 7e-10 at those samples. These consistency checks apply to the
discretized model at the chosen planes.

The symmetric lines illustrate the cancellation. Driving the two near-end ports in phase selects
the even mode, and opposite drive phases select the odd mode. The near-end pickup S31 is half
the difference between their reflection coefficients, and the far-end S41 is half the difference
between their transmission coefficients. On the initial mesh, the two reflection coefficients
are 175° apart at 6 GHz but only 13° apart at 10.525 GHz, where they largely cancel. The
transmission phase difference grows from 5° to 13° over the same interval. Those numbers describe
the complete structure including its lumped ports. Moving the reference planes into uniform
feed lines would help separate the coupled section from the port discontinuities.

Increasing only the gap to 0.35 mm on the initial mesh changes coupling loss at 10.525 GHz from
25.74 to 28.38 dB and isolation from 18.89 to 19.61 dB. Since the loss at the desired pickup
increases more, directivity falls to −8.77 dB. This single variation does not establish a
broadband optimum.

Adding 11.25, 11.5 and 11.75 GHz finds a deeper sampled minimum at 11.5 GHz on both meshes:
−12.42 dB initially and −12.41 dB after refinement. The default ten-point sweeps placed their
minima at 11 GHz (−10.58 and −10.84 dB). Reproduce the extra points on each mesh as follows.

```sh
bazel run //coupler:solve -- --frequencies-ghz 11.25 11.5 11.75 --save-ghz 11.5 \
  --output "$runs/notch"
bazel run //coupler:solve -- --refinement 1 --frequencies-ghz 11.25 11.5 11.75 --save-ghz 11.5 \
  --output "$runs/notch-refined"
```

The two full sweep records on kratos are under `~/.local/state/guvna/coupler/{initial,refined}`.
The changed-gap record is `gap035` under the same directory.

The [Palace adaptivity study](adaptivity.md) compares solver-driven mesh refinement and adaptive
frequency sampling on the 100 mm coupon, including a direct check at a newly resolved S21 dip.

## Taper design history

Run a sequence of field solves on an SM89 GPU and inspect results as they finish. The viewer can
run in a separate terminal. Use its **Design history** link to see the measured tradeoffs, open a
mesh and select saved fields. Each design's port response overlays its parent by default.

```sh
study="$HOME/.local/state/guvna/coupler/design-history"
mkdir -p "$study"
bazel run //coupler:design_study -- "$study" --continuous
bazel run //viewer:serve -- --history "$study"
```

The initial study compares the uniform 100 mm control, a linear gap taper, dielectric filling above
the traces, and a narrower embedded pair. Subsequent sweeps use the best completed screen as the
parent and vary input gap, taper exponent, trace width and section length. The gap follows
`g(x) = g_in + (g_out - g_in) (x/L)^p`. Each x plane of the validated structured Gmsh mesh is
warped monotonically in y. Both equal-width traces can taper together using the same normalized
profile as the gap. The enclosure walls stay fixed and each lumped port spans its local trace
width. The first width trial widens from 0.725 to 0.855 mm. A constant 0.790 mm pair provides an
equal-mean-width control. Both trials use their parent's gap, length, materials and mesh policy.
Run `bazel run //coupler:modal_width` to estimate the width giving √(Ze Zo) = 50 Ω at each
cross-section of the homogeneous, dielectric-covered coupon. The calculation uses even and odd
electrostatic strip charge in its grounded rectangular enclosure. Palace includes the transitions,
lumped ports and propagation along the complete taper.
In the model browser, toggle **Facing trace edges** to inspect the two sizing bands inside the gap.
**Gap interior** and **Outer trace edges** have their own eyes.

Each facing band has two lateral intervals capped at 0.055 mm. Intervals toward the middle can
grow by up to 1.5× per cell to a maximum of 0.22 mm. The widest section sets the structured
interval count. Cells compress where the traces approach. Swept overlays follow the mesh stations.
For an archive made with the old four-cell gap, the worker repeats its best screening geometry on
the new policy and a second mesh with halved pitch caps. Later design rankings use the new policy.
The old geometry, mesh and port response remain available as the comparison parent.

All screens use the same 100 output frequencies from 0.5 to 12 GHz, one port-1 excitation, a
50 Ω reference at each PCB end and saved volume and boundary fields at the band edges. The
underlying model uses lossless dielectrics and PEC conductors. The covered pair has an upper
grounded lid and the same bottom-referenced lumped ports as the air-filled control. The exponent
defines a trial profile. Coupling flatness and directivity are measured from the resulting solve.

For ranking, the provisional score is the larger of the maximum absolute coupling error from 20 dB
and the worst directivity shortfall below 30 dB. Both use dB at the sampled frequencies. Match
and through loss are reported separately. The best candidate gets a second solve with twice as
many longitudinal cells and a full direct solve at every output frequency. Narrow extrema can
fall between samples.

With `--continuous`, the worker then perturbs two dimensions of the best screening design at a
time. Every fourth proposal also explores the wider parameter range and upper dielectric. Each
finished directory contains the sampled complex port response (magnitude and phase), Palace deck,
field data, mesh, solver log and `design.json` with its parent, parameters, metrics and wall time.
The history page refreshes every ten seconds. Completed directories are published by atomic rename.

Create `"$study/PAUSE"` to stop after the current solve. Remove it and repeat the same command to
resume. Completed designs are reused in sequence. Interrupted attempts remain in hidden directories
for diagnosis. The worker also stops between runs below 24 GiB free by default
(`--reserve-gib`).

### COBYQA width and gap optimization

Start the bounded optimizer when the GPU study worker has released its lock. The same command
resumes an interrupted experiment from the archived seed, pinned SciPy version and completed
evaluations. Both workers honor the same PAUSE marker and free-space reserve.

```sh
bazel run //coupler:optimize -- "$study" --budget 30
```

The best eligible full-band screen on the facing-edge mesh seeds the experiment. Start and end
gap vary within 0.10–0.80 and 1.40–3.40 mm. Mean width varies within 0.60–1.15 mm and end width
minus start width within ±0.40 mm. Length, taper exponent, stackup and mesh policy follow the seed.
COBYQA works in normalized dimensions. At every output frequency the auxiliary objective in dB
must cover the absolute coupling error and the directivity shortfall. Requests differing only in
that auxiliary variable reuse a single physical sweep. Ranking uses the actual measured score.

The history lists every completed evaluation, including regressions. Evaluation number gives solve
order. Generation is depth from the seed (generation 0). The parent is the best measured design
available before that trial and provides the comparison overlay. Multiple proposals can share one
parent. The progress plot starts at the common seed and accumulates screen wall time separately
for each search method on the current mesh policy. Checks and legacy uniform-gap screens are
excluded. At completion the worker solves the seed and winner directly with halved gap pitch caps
on one shared grid around both designs' limiting coupling and directivity samples. These spot
checks have their own history entries. The starting configuration is in `cobyqa-plan.json` and
the outcome, timing and validation references are in `cobyqa-result.json`. If libCEED aborts with
its borrowed-device-array error or the GPU direct check raises SIGFPE, the optimizer archives the
attempt and repeats that case on four CPU ranks. History identifies the completing device and
includes retry time in the run cost.

Use `--mesh gap8` to run a separate eight-cell screening campaign with the same 100-point sweep:

```sh
bazel run //coupler:optimize -- "$study" --mesh gap8 --budget 30
```

The worker re-solves the starting geometry before ranking candidates. Four cells span each
half-gap. From the copper edge inward their pitch caps are 0.11, 0.22, 0.33 and 0.44 mm for a
2.2 mm outlet. Wider gaps expand the three interior caps in proportion. The worker records
the caps, seed, parent, device and wall time. The `cobyqa-gap8` prefix identifies this campaign.
The history shows median and range across completed eight-cell candidate screens. Seed and
validation times appear in their own rows. Both campaigns use the same finer validation policy.
