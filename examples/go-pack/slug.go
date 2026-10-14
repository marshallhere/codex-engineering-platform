package packfixture

import "strings"

// Slug provides a tiny reference behavior for external-pack conformance.
func Slug(value string) string {
	return strings.Join(strings.Fields(strings.ToLower(value)), "-")
}
