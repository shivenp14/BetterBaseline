export function MethodDisclosures() {
  return <aside aria-label="Simulation method disclosures">
    <p>These simulations are synthetic and conditional on specified rates, effect, independent missingness, and frozen enrollment. They do not predict treatment efficacy.</p>
    <p>Analytical power uses Cohen’s-h and floored expected retained counts. Monte Carlo samples actual retained counts and applies a two-sided pooled-z test; these are different approximations.</p>
    <p>MCSE measures simulation sampling error separately for each significance fraction. It does not measure uncertainty in the entered assumptions.</p>
    <p>Under a null effect, two-sided rejection is approximately alpha; favorable-direction rejection is approximately alpha/2. Undefined tests count as nonrejections over all replicates.</p>
  </aside>;
}
