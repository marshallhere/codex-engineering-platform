package packfixture

import "testing"

func TestSlug(t *testing.T) {
	for input, want := range map[string]string{
		"  New Project  ": "new-project",
		"": "",
		"ONE\tTWO": "one-two",
	} {
		if got := Slug(input); got != want {
			t.Errorf("Slug(%q) = %q; want %q", input, got, want)
		}
	}
}
