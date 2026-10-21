"""Greenhouse application adapter over the shared Playwright form engine."""

from lookout.appliers.base import _BrowserFormApplier

_EXTRACTION_JS = """() => {
  const form = document.querySelector('#application_form');
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
        selector: '#' + node.id,
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
    const wrapper = node.closest('.custom-question') || node.closest('.field');
    const labelNode = wrapper ? wrapper.querySelector('label') : null;
    const label = labelNode ? labelNode.textContent.trim() : '';
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


class GreenhouseApplier(_BrowserFormApplier):
    platform = "greenhouse"
    extraction_js = _EXTRACTION_JS
    form_present_js = "() => !!(document.querySelector('#application_form'))"
    resume_selector = "#resume-upload-input"
    submit_selector = "#application_form button[type=submit]"
    apply_route_selector = ""
    identity_names = frozenset(
        {"first_name", "last_name", "email", "phone", "location", "website", "linkedin"}
    )
    name_mode = "identity_only"
    needs_apply_route = False
