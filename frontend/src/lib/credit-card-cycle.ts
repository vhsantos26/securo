import { format, parseISO } from 'date-fns'

import { localDateString } from './date-utils'

export function creditCardCycleBoundaries(closeDay: number, reference = new Date()): { start: string; end: string } {
  const ref = new Date(reference)
  ref.setHours(0, 0, 0, 0)
  const clampDay = (year: number, month: number) => Math.min(closeDay, new Date(year, month + 1, 0).getDate())
  const thisMonthClose = new Date(ref.getFullYear(), ref.getMonth(), clampDay(ref.getFullYear(), ref.getMonth()))
  const nextClose = thisMonthClose > ref
    ? thisMonthClose
    : new Date(ref.getFullYear(), ref.getMonth() + 1, clampDay(ref.getFullYear(), ref.getMonth() + 1))
  const end = new Date(nextClose)
  end.setDate(end.getDate() - 1)
  const start = new Date(nextClose.getFullYear(), nextClose.getMonth() - 1, clampDay(nextClose.getFullYear(), nextClose.getMonth() - 1))
  return { start: localDateString(start), end: localDateString(end) }
}

/** Derive a bill's cycle close date from the account's statement_close_day.
 * Pluggy doesn't expose the close date directly, but it's recoverable: the
 * close is the most recent occurrence of close_day on or before the bill's
 * due_date. Falls back to due_date when close_day is not configured. */
export function closeDateForBill(billDueDate: string, closeDay: number | null | undefined): string {
  if (!closeDay) return billDueDate
  const due = parseISO(billDueDate + 'T00:00:00')
  const y = due.getFullYear()
  const m = due.getMonth()
  const lastThis = new Date(y, m + 1, 0).getDate()
  const sameMonth = new Date(y, m, Math.min(closeDay, lastThis))
  if (sameMonth.getTime() <= due.getTime()) {
    return format(sameMonth, 'yyyy-MM-dd')
  }
  const py = m === 0 ? y - 1 : y
  const pm = m === 0 ? 11 : m - 1
  const lastPrev = new Date(py, pm + 1, 0).getDate()
  return format(new Date(py, pm, Math.min(closeDay, lastPrev)), 'yyyy-MM-dd')
}

/** True when `windowStart` falls inside the cycle that is still open, meaning
 * every transaction in the window is by definition unbilled.
 *
 * This is the question `unbilled_only` answers on the backend: it drops every
 * transaction already linked to a bill, which is right for the open cycle
 * (whose window overlaps the newest closed bill's range, so without it the
 * closed bill's charges would double-count) and wrong for anything else.
 *
 * The open cycle starts on the newest bill's close day, since the close day
 * itself opens the next cycle. A window starting before that covers billed
 * history, and the caller must not ask for unbilled transactions only, or the
 * history disappears.
 *
 * Both arguments are `yyyy-MM-dd`, which compares chronologically as a string.
 */
export function isOpenCycleWindow(
  windowStart: string,
  newestBillDueDate: string,
  closeDay: number | null | undefined,
): boolean {
  if (!windowStart) return false
  return windowStart >= closeDateForBill(newestBillDueDate, closeDay)
}
