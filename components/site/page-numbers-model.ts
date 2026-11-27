/** "214 reviews · page 3 of 9" — the total first (MQA-036/037). Pure, for tests/frontend. */
export function countLine(total: number, noun: [string, string], page: number, pages: number): string {
  const what = `${total.toLocaleString("en-PH")} ${total === 1 ? noun[0] : noun[1]}`;
  return pages > 1 ? `${what} · page ${Math.min(page, pages)} of ${pages}` : what;
}
