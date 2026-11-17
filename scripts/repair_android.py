#!/usr/bin/env python3
"""Repair known Android build metadata defects in an extracted project copy."""
from pathlib import Path
import html
import re
import sys

root = Path(sys.argv[1]).resolve()
report = Path(sys.argv[2]) if len(sys.argv) > 2 else root / 'repair-report.txt'
changes = []

coordinate_replacements = {
    'com.composables:composeunstyled:1.20.1': 'com.composables:composeunstyled:1.49.9',
    'com.composables:composeunstyled:1.20.0': 'com.composables:composeunstyled:1.49.9',
    'com.composables:core:1.19.3': 'com.composables:core:1.49.9',
    'com.google.android.gms:play-services-cronet:119.6045.31': 'com.google.android.gms:play-services-cronet:18.1.1',
    'org.chromium.net:cronet-okhttp:131.0.6778.108': 'com.google.net.cronet:cronet-okhttp:0.1.1',
}
catalog_versions = {
    'com.composables:composeunstyled': '1.49.9',
    'com.composables:core': '1.49.9',
    'com.google.android.gms:play-services-cronet': '18.1.1',
    'com.google.net.cronet:cronet-okhttp': '0.1.1',
}
coordinate_modules = {
    'org.chromium.net:cronet-okhttp': 'com.google.net.cronet:cronet-okhttp',
}

def repair_catalog(path: Path, content: str) -> str:
    lines = content.splitlines()
    section = ''
    alias_versions = {}
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            section = stripped
            continue
        if section != '[libraries]' or 'module = ' not in line:
            continue
        module_part = line.split('module = ', 1)[1]
        if not module_part.startswith('"'):
            continue
        module = module_part.split('"', 2)[1]
        if module in coordinate_modules:
            lines[i] = line.replace(module, coordinate_modules[module])
            line = lines[i]
            module = coordinate_modules[module]
            changes.append(f'{path.relative_to(root)}: changed Cronet OkHttp module coordinate')
        if module not in catalog_versions:
            continue
        desired = catalog_versions[module]
        if 'version.ref = ' in line:
            ref_part = line.split('version.ref = ', 1)[1]
            if ref_part.startswith('"'):
                alias_versions[ref_part.split('"', 2)[1]] = desired
        elif 'version = ' in line:
            before, after = line.split('version = ', 1)
            if after.startswith('"'):
                old = after.split('"', 2)[1]
                lines[i] = before + 'version = "' + desired + '"' + after.split('"', 2)[2]
                changes.append(f'{path.relative_to(root)}: updated {module} from {old} to {desired}')
    section = ''
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            section = stripped
            continue
        if section == '[versions]' and ' = ' in line:
            key = line.split(' = ', 1)[0].strip()
            if key in alias_versions and '"' in line:
                lines[i] = key + ' = "' + alias_versions[key] + '"'
                changes.append(f'{path.relative_to(root)}: updated catalog alias {key} to {alias_versions[key]}')
    return '\n'.join(lines) + ('\n' if content.endswith('\n') else '')

for path in root.rglob('*'):
    if not path.is_file() or any(part in ('.gradle', 'build') for part in path.parts):
        continue
    if path.suffix in ('.toml', '.gradle', '.kts', '.properties'):
        original = path.read_text(errors='ignore')
        updated = original
        for old, new in coordinate_replacements.items():
            updated = updated.replace(old, new)
        if path.suffix == '.toml':
            updated = repair_catalog(path, updated)
        if path.suffix in ('.gradle', '.kts'):
            updated = updated.replace(
                'libs.androidx.compose.ui.googlefonts.let { libs.androidx.compose.ui.text.googlefonts }',
                'libs.androidx.compose.ui.text.googlefonts'
            )
            manifest = path.parent / 'src/main/AndroidManifest.xml'
            has_hilt = ('com.google.dagger.hilt.android' in updated or 'libs.plugins.hilt' in updated)
            if manifest.is_file() and has_hilt and 'hilt-android' not in updated and 'dependencies {' in updated:
                updated = updated.replace(
                    'dependencies {',
                    'dependencies {\n    implementation("com.google.dagger:hilt-android:2.57.1")',
                    1
                )
                changes.append(f'{path.relative_to(root)}: added missing Hilt Android runtime dependency')
        if path.suffix in ('.gradle', '.kts', '.properties') and updated != original:
            path.write_text(updated)
            changes.append(f'{path.relative_to(root)}: corrected dependency metadata')
        elif path.suffix == '.toml' and updated != original:
            path.write_text(updated)
            changes.append(f'{path.relative_to(root)}: corrected version catalog metadata')

for path in root.rglob('*.kt'):
    if any(part in ('.gradle', 'build') for part in path.parts):
        continue
    original = path.read_text(errors='ignore')
    updated = original.replace(
        'org.chromium.net.okhttp.CronetInterceptor',
        'com.google.net.cronet.okhttptransport.CronetInterceptor'
    )
    if updated != original:
        path.write_text(updated)
        changes.append(f'{path.relative_to(root)}: corrected Cronet OkHttp import package')

label_pattern = re.compile(r'((?:android:)?shortcut(?:Short|Long)Label\s*=\s*")([^"]+)(")')
for shortcuts in root.rglob('shortcuts.xml'):
    if any(part in ('.gradle', 'build') for part in shortcuts.parts):
        continue
    xml = shortcuts.read_text(errors='ignore')
    generated = []
    def replace_label(match):
        value = match.group(2)
        if value.startswith('@') or value.startswith('?'):
            return match.group(0)
        name = 'buildfix_shortcut_label_' + str(len(generated) + 1)
        generated.append((name, value))
        return match.group(1) + '@string/' + name + match.group(3)
    fixed = label_pattern.sub(replace_label, xml)
    if generated:
        shortcuts.write_text(fixed)
        values_dir = shortcuts.parent.parent / 'values'
        values_dir.mkdir(parents=True, exist_ok=True)
        values_file = values_dir / 'buildfix_shortcut_labels.xml'
        values = ['<?xml version="1.0" encoding="utf-8"?>', '<resources>']
        for name, value in generated:
            values.append('    <string name="' + name + '">' + html.escape(value) + '</string>')
        values.append('</resources>')
        values_file.write_text('\n'.join(values) + '\n')
        changes.append(f'{shortcuts.relative_to(root)}: moved {len(generated)} shortcut labels into string resources')

report.parent.mkdir(parents=True, exist_ok=True)
report.write_text('\n'.join(changes) + ('\n' if changes else 'No known build repairs were needed.\n'))
print(report.read_text())