/** Match backend expected_retained_count: interpret the shortest decimal
 * representation of dropout, then floor the exact integer ratio. */
export function expectedRetainedCount(enrollment: number, dropout: number): number {
  if (!Number.isSafeInteger(enrollment) || enrollment <= 0 || !Number.isFinite(dropout) || dropout < 0 || dropout > 1) {
    throw new RangeError("Expected positive integer enrollment and dropout between zero and one.");
  }
  const [mantissa, exponent = "0"] = String(dropout).split("e");
  const [whole, fraction = ""] = mantissa.split(".");
  const scale = fraction.length - Number(exponent);
  const numerator = BigInt(whole + fraction);
  const denominator = BigInt(10) ** BigInt(scale);
  return Number(BigInt(enrollment) * (denominator - numerator) / denominator);
}
