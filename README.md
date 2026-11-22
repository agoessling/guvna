# GuVNA

GuVNA is a hardware vector network analyzer project. The first design task is a wideband directional
coupler. The [design requirements](REQUIREMENTS.md) record the RF targets and what each simulation
needs to preserve for system-level analysis.

## Build plan

We plan to use Bazel as the common build and test entry point for the monorepo. Python analysis
tools and web apps will consume the same simulation results, and future firmware and FPGA builds may
share hardware definitions. Bazel targets will make those dependencies explicit and give
contributors and coding agents the same commands to reproduce a result.

We’ll introduce Bazel with the first nominal 50 Ω through-line case. The initial setup will pin the
Bazel version, expose one target to run Palace on a CPU, and provide a fast check of the analysis
code. The run will save complex S-parameters and the inputs needed to reproduce them.
