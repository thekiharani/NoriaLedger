import { describe, expect, it } from "vitest";
import { centsToString, periodBounds, previousPeriod, sumCents, toCents, toCsv } from "./format";

describe("money arithmetic", () => {
  it("parses decimal strings exactly", () => {
    expect(toCents("0.1")).toBe(10);
    expect(toCents("1,234.56")).toBe(123456);
    expect(toCents("-5.05")).toBe(-505);
    expect(Number.isNaN(toCents("1.234"))).toBe(true);
    expect(Number.isNaN(toCents("abc"))).toBe(true);
  });
  it("sums without floating point drift", () => {
    expect(sumCents(["0.1", "0.2"])).toBe(30);
    expect(centsToString(sumCents(["100.10", "200.20", "0.70"]))).toBe("301.00");
  });
});

describe("periods", () => {
  it("computes month bounds incl. leap years", () => {
    expect(periodBounds("2028-02")).toEqual({ from: "2028-02-01", to: "2028-02-29" });
    expect(periodBounds("2026-09")).toEqual({ from: "2026-09-01", to: "2026-09-30" });
  });
  it("finds the previous period across years", () => {
    expect(previousPeriod(new Date(2027, 0, 15))).toBe("2026-12");
  });
});

describe("csv export", () => {
  it("escapes and neutralises formulas", () => {
    const csv = toCsv([{ key: "a", label: "A" }], [{ a: '=HYPERLINK("x")' }, { a: "-12.50" }, { a: "x,y" }]);
    expect(csv).toBe(`A\n"'=HYPERLINK(""x"")"\n-12.50\n"x,y"`);
  });
});
