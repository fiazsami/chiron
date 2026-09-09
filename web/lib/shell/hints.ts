// Hint-mode labels (key f): home-row alphabet, uniform length so the label
// set is prefix-free — a typed buffer either extends toward exactly one
// label or misses.

const ALPHABET = "asdfghjkl";

export function hintLabels(count: number): string[] {
  if (count <= 0) return [];
  let length = 1;
  while (ALPHABET.length ** length < count) length++;
  const labels: string[] = [];
  const indexes = new Array<number>(length).fill(0);
  for (let n = 0; n < count; n++) {
    labels.push(indexes.map((i) => ALPHABET[i]).join(""));
    for (let pos = length - 1; pos >= 0; pos--) {
      indexes[pos]++;
      if (indexes[pos] < ALPHABET.length) break;
      indexes[pos] = 0;
    }
  }
  return labels;
}
