# Four-port coupled-line simulation

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
to override individual mesh counts in either refinement preset.

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
