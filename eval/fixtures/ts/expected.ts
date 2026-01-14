export function toKebab(value: string, stopwords: string[] = []): string {
  const cleaned = value.replace(/[^a-zA-Z0-9\s-]/g, " ");
  const parts = cleaned
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .map((p) => p.toLowerCase())
    .filter((p) => !stopwords.includes(p));
  return parts.join("-");
}
