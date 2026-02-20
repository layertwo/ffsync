import DOMPurify from "dompurify"

/**
 * Strip HTML from an externally-sourced string and cap its length.
 *
 * Used for OAuth error responses and API error bodies before they are
 * included in Error messages shown to the user.
 */
export function sanitizeExternal(value: string, maxLength = 200): string {
  return DOMPurify.sanitize(value, { ALLOWED_TAGS: [], ALLOWED_ATTR: [] }).slice(0, maxLength)
}
