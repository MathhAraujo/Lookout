"""Lever application adapter over the shared Playwright form engine.

The hosted Lever posting links to the application form; the adapter follows the
apply link before reading the form.
"""

from lookout.appliers.base import _BrowserFormApplier

_EXTRACTION_JS = """() => {
  const form = document.querySelector('#lever-application');
  if (!form) return null;
  const nodes = form.querySelectorAll(
    'input[type="file"], input:not([type="file"]):not([type="hidden"]):not([type="submit"]):not([type="checkbox"]), textarea, select, .signature-widget'
  );
  return Array.from(nodes).map((node) => {
    if (node.type === 'file') {
      return {
        kind: 'file',
        name: node.name || '',
        label: '',
        required: node.required === true,
        options: [],
        selector: node.id
          ? '#' + node.id
          : node.name
            ? '[name="' + node.name + '"]'
            : '',
      };
    }
    let kind;
    if (node.classList && node.classList.contains('signature-widget')) {
      kind = 'unsupported';
    } else if (node.tagName === 'SELECT') {
      kind = 'select';
    } else {
      kind = 'text';
    }
    const labelNode = node.closest('label');
    let label = '';
    if (labelNode) {
      const first = labelNode.firstChild;
      label =
        first && first.nodeType === 3 ? first.textContent.trim() : labelNode.textContent.trim();
    }
    const options = kind === 'select'
      ? Array.from(node.querySelectorAll('option'))
          .filter((option) => option.value.length > 0)
          .map((option) => option.textContent.trim())
          .filter((text) => text.length > 0)
      : [];
    const required = node.required === true || node.getAttribute('aria-required') === 'true';
    const selector = node.id
      ? '#' + node.id
      : node.name
        ? '[name="' + node.name + '"]'
        : (node.classList && node.classList.length ? '.' + node.classList[0] : '');
    return { kind, name: node.name || '', label, required, options, selector };
  });
}"""


class LeverApplier(_BrowserFormApplier):
    platform = "lever"
    extraction_js = _EXTRACTION_JS
    form_present_js = "() => !!(document.querySelector('#lever-application'))"
    resume_selector = '#lever-application input[type="file"]'
    submit_selector = "#lever-application button[type=submit]"
    apply_route_selector = "a.big-btn"
    identity_names = frozenset()
    name_mode = "always"
    needs_apply_route = True
