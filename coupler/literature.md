# Wideband directional couplers for GuVNA

The target is about 20 dB coupling and at least 30 dB raw directivity from 0.5 to 12 GHz, a
24:1 frequency span. At a frequency where coupling loss is 20 dB, the unwanted sample must be
at least 50 dB below the input. Use the difference between isolation and coupling loss at the
same frequency. Record which physical end receives the desired sample for each topology.

## Three geometries to recognize

### Two microstrip arcs that approach in the middle

Morgan and Weinreb's VNA sampler uses two quarter-circle arcs on the same side of an alumina
substrate. The traces keep the width of the 50 Ω feed lines. Radius and closest spacing set the
interaction. The even and odd modes accumulate different phases through the coupled region.
At the far end their difference produces a useful sample on the second line. The gradual change
in spacing suppresses reflections that would send energy back to its near end.

They measured >20 dB directivity from 50 to 110 GHz. Coupling loss was 15.4 dB at 50 GHz,
12.8 dB at 75 GHz, and 11.2 dB at 110 GHz. The maximum through loss was 1.1 dB. The VNA
measurement used a 48 Ω reference after renormalization. The thesis shows the layout and hardware
in Figs. 7.18–7.19 and measured response in Fig. 7.25. [Paper][arcs] · [Thesis][morgan]

Compare Hrobak et al.'s **backward-wave** microstrip. They shaped the line edges to compensate
modal dispersion, extracted frequency-dependent parameters in 2D, and built a planar matched
termination for the isolated port. Their measurement gives 16.6 ± 2.4 dB coupling over
2–50 GHz. Reported directivity is >10 dB from 10 MHz to 33.8 GHz and 8 dB up to 48.4 GHz.
This is a measured 25:1 coupling band with a much lower directivity floor than ours. [Paper][bw]

### A conductive square between four feeds

Menzel et al. show a solid rectangular microstrip patch joining four feeds in a 38 GHz
radiometer. The basic plate gave unequal output powers. Slots cut into the long sides adjusted
the current paths and brought the outputs closer to the intended 3 dB split. Figs. 10–11 show
the copper shape and prototype measurements. This is a plausible match to the solid square.
A related connected-patch design by Zhou et al. used via-grounded cells beneath the patch to
redistribute current. It measured 8 ± 0.5 dB coupling and 90° ± 4° output phase difference
over 5.3–11.6 GHz. These results concern power division and output phase.
[Menzel et al., §3.5][patch] · [Zhou et al., Figs. 1 and 4][sectors]

An **open center** suggests a branch-line hybrid. Its four conducting arms form a loop, and
signals traveling around the two paths can cancel at the isolated port. Lee and Lee added a
quarter-wave transformer at each port. Their 3 GHz prototype held coupling at 10 ± 0.5 dB over
50.9% fractional bandwidth, with 18.7 dB minimum isolation. At the frequency of minimum
isolation, those numbers imply about 8–9 dB directivity. [Lee and Lee][branch]

### Striplines crossing at a shallow angle on different layers

Du Toit, Joubert, and Odendaal show the cross section in Fig. 2 and the plan view in Fig. 3.
Two buried strips approach, overlap in projection, and separate. There is dielectric between
them even at the crossing. Lateral offset and width set the local coupling and impedance. At
full overlap, changing width alone cannot independently set both. The authors let the local
impedance depart from 50 Ω and taper it back to 50 Ω at the ports. Their 2–18 GHz tandem 3 dB
hybrid measured within 1 dB amplitude imbalance and 4° phase error. [2022 paper][crossing]

Their follow-up includes a fabricated 21-section **0.5–18 GHz** hybrid. Fig. 10 shows its layout
and Fig. 12 includes measured input match and isolation. Maximum measured output imbalance was
1.47 dB. For a separate 2–18 GHz design, the authors perturbed spline parameters and used the
response at ripple extrema to estimate a Jacobian. Five iterations took 55 full-wave simulations.
GuVNA could apply the same strategy to coupling and isolated-port leakage. [2026 paper][splines]

For weak coupling specifically, López-Berrocal et al. built a six-section offset stripline in
LTCC. They measured 10.3 ± 0.6 dB coupling, >23 dB isolation, and >15 dB return loss over
1.8–18 GHz. The published limits guarantee >12.1 dB directivity by subtraction. The actual
pointwise result can be better. The design includes the transitions to its external ports.
[Paper and measured S-parameters][ltcc]

Hrobak et al. also built two symmetric offset-stripline samplers specifically for VNA test sets.
They report >15 dB directivity up to 40 GHz and 29 GHz, respectively. They characterized line
cross sections with 2D EM and identified the transitions from stripline to surface microstrip
and fabrication tolerances as important to the finished sampler. [Conference abstract][testset]

## Alternatives for a VNA test port

- **Resistive directional bridge.** Drobotun and Mikheev balanced a resistive bridge so a
  matched DUT produces a null at the pickup. An asymmetric divider preserves through power.
  Their multilayer PCB with surface-mount resistors and a balun measured 16 ± 3 dB coupling
  and at least 25 dB directivity from 300 kHz to 13.5 GHz. Nominal through loss was 1.6 dB.
  This covers the entire GuVNA band, including the difficult low end. Figs. 8–11 show the
  hardware, through loss, coupling, and directivity. [Conference paper][bridge]
- **Machined coupled bars with a metal diaphragm.** Lvov et al. used rectangular bars in a
  common housing. Shaping the metal between them gave control over the coupling while keeping
  the cross section narrow enough to suppress higher modes. They report at least 30 dB
  directivity for a nominal 20 dB coupler from 2 to 18 GHz. The authors identify the built-in
  termination and the dielectric supports as critical to that result. Fig. 1 gives the cross
  section. This is a measured precedent for our upper band. [URSI paper][bars]
- **Equalized pickup.** Li et al. added a lumped bridged-T equalizer to a microstrip sampler
  on a GaAs chip. They report nominal 20 dB coupling, ±0.3 dB flatness, >20 dB directivity,
  and <1.5 dB through loss over 2–20 GHz. It suggests optimizing the sampled-arm network
  alongside the EM geometry once measured component parasitics are available. [IEEE paper][eq]

A commercial reference at the same nominal coupling is Marki's C20-0R520. Its 0.5–12 GHz
directivity specification is 15 dB minimum and 22 dB typical. Marki's CBR16-0012 bridge
specifies 22 dB minimum and 32 dB typical across 200 kHz–12 GHz, with up to 3.5 dB through
loss and typical coupling of 12 dB at 12 GHz. A typical 30 dB curve and a 30 dB guaranteed
minimum are substantially different design targets. [Coupler datasheet][markic] ·
[Bridge datasheet][markib]

The 1998 paper from the design discussion is by Yukawa, Oh-Hashi, and Miyazaki. They added
uniform coupled end sections to a nonuniform center to shorten the device and reduce required
line spacing. The accessible abstract reports a 50% size reduction for the fabricated coupler.
The numerical bandwidth and directivity remain unverified. [Conference record][yukawa]

## Experiments suggested by the measurements

1. Model a symmetric two-arc coupon on actual air-over-substrate microstrip. Use fixed 50 Ω
   feeds, sweep radius and closest gap, and score the **far-end** pickup. Compare with the
   existing taper using both physical pickup traces. A dielectric-filled enclosure changes the
   modal velocity difference that the arcs exploit.
2. Model a single weak broadside section between ground planes in a homogeneous dielectric.
   Compare a uniform offset with a smooth offset profile at the same port planes. Vary width
   alongside offset to control the match. Allow a nonzero minimum offset. Check sensitivity
   to layer registration and dielectric thickness before increasing the number of sections.
3. Use the published bridge as a system-level comparison. Budget its through loss and receiver
   sample power at both band edges. On both coupled-line coupons, extend the uniform feeds and
   vary wall clearance separately before attributing a change in isolation to the taper.

[arcs]: https://authors.library.caltech.edu/records/js4nv-sga10
[morgan]: https://www.submm.caltech.edu/~jonas/Theses/Matt_Morgan_03.pdf
[bw]: https://cris.fau.de/publications/123898544/
[patch]: https://mwt-www.e-technik.uni-ulm.de/public/papers/2003/431_Menzel_et_al.pdf
[sectors]: https://doi.org/10.1049/el.2014.4050
[branch]: https://doi.org/10.1109/LMWC.2011.2176723
[crossing]: https://doi.org/10.1049/ell2.12355
[splines]: https://doi.org/10.1155/mmce/1531761
[ltcc]: https://www.jpier.org/ac_api/download.php?id=10040704
[testset]: https://www.researchgate.net/publication/241629335
[bridge]: https://www.mikrocontroller.net/attachment/482240/GHz-Directional-Bridge.pdf
[bars]: https://ursi.org/proceedings/procGA05/pdf/AP.2%2801639%29.pdf
[eq]: https://doi.org/10.1109/TMTT.2022.3146028
[markic]: https://markimicrowave.com/products/connectorized/directional-couplers/c20-0r520/
[markib]: https://markimicrowave.com/products/connectorized/directional-couplers/cbr16-0012/
[yukawa]: https://doi.org/10.1109/EUMA.1998.338237
