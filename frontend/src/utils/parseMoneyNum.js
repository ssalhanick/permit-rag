/**
 * Safely convert a currency-ish value (number, "18500", "$18,500", null) into a plain number.
 *
 * @param {string|number|null|undefined} val
 * @returns {number}
 */
export function parseMoneyNum(val) {
  if (typeof val === "number") return isNaN(val) ? 0 : val;
  if (!val) return 0;
  const num = parseFloat(String(val).replace(/[^0-9.]/g, ""));
  return isNaN(num) ? 0 : num;
}
