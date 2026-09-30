/**
 * Numeric grounding: every number in generated text must appear in the facts (or in the customer's own message),
 * allowing for formatting differences (€3,200 = € 3.200 = 3 200 €).
 */
const NUMBER = /\d+(?:[.,   ]\d+)*/g;

const digits = (token: string) => token.replace(/\D/g, "");

export function numbersIn(text: string): string[] {
  return (text.match(NUMBER) ?? []).map(digits).filter(Boolean);
}

export type Grounding = { ok: boolean; checked: number; unknown: string[] };

export function checkGrounding(texts: string[], facts: string[]): Grounding {
  const allowed = new Set<string>();
  for (const f of facts) {
    for (const token of f.match(NUMBER) ?? []) {
      allowed.add(digits(token));
      for (const part of token.split(/[.,   ]/)) if (part) allowed.add(part);
    }
  }
  const found = texts.flatMap(numbersIn);
  const unknown = found.filter((n) => !allowed.has(n));
  return { ok: unknown.length === 0, checked: found.length, unknown: [...new Set(unknown)] };
}
