# GuVNA design requirements

## Directional coupler

Design targets adopted November 22, 2026. The band includes both endpoints. The 10.525 GHz application frequency is a point of particular interest within the band.

| Quantity | Target | How to evaluate |
| --- | --- | --- |
| Operating band | 500 MHz to 12 GHz | Evaluate coupling and directivity across the full band. |
| Coupling loss | Approximately 20 dB across the band | Report minimum and maximum coupling loss and their frequencies. Allowable deviation from 20 dB is open. |
| Raw directivity | 30 dB across the band | Treat 30 dB as the design floor. Report the lowest directivity and its frequency before VNA error correction. |

Use equal, real 50 Ω port references. For excitation at port 1 with the other ports matched, port 2 is through, port 3 is forward-coupled, and port 4 is isolated. Mark the physical port locations on each layout. Coupling loss is −20 log₁₀|S₃₁| and isolation is −20 log₁₀|S₄₁|. Raw directivity is isolation minus coupling loss. At a frequency where coupling loss is 20 dB, 30 dB directivity requires at least 50 dB isolation.

Start with Palace and use uniform PCB feed-line reference planes for the first coupon model. Document the actual planes on each result. Connector mating planes will matter for comparison with the assembled hardware. Through loss, return loss, fabrication tolerances, and calibrated reflection accuracy remain open.

## System-level RF simulation

The eventual goal is to predict VNA performance, including how accurately it can measure S11 and S22. Preserve the frequency-dependent **complex four-port S-matrix** for each finalist as a Touchstone .s4p file, with port order, reference impedances, reference planes, and the corresponding geometry. Phase matters because the DUT reflection and leakage add coherently at the receiver.

Combine those responses with source power and match, interconnects, terminations, and receiver gain and noise at the chosen IF bandwidth. Compare simulated reflection readings with known DUT responses before and after modeled calibration. Include drift and calibration-standard uncertainty when estimating achievable accuracy. Source level, receiver bandwidth, and system-level acceptance thresholds are still to be chosen.
