#!/usr/bin/env python3
"""Repair known Android build metadata defects in an extracted project copy."""
from pathlib import Path
import html
import re
import sys

root = Path(sys.argv[1]).resolve()
report = Path(sys.argv[2]) if len(sys.argv) > 2 else root / 'repair-report.txt'
changes = []

def desired_for(group: str, name: str):
    module = f'{group}:{name}'
    if module in ('com.composables:composeunstyled', 'com.composables:core'):
        return module, '1.49.9'
    if module == 'dev.chrisbanes.haze:haze':
        return module, '1.7.3'
    if module == 'sh.calvin.reorderable:reorderable':
        return module, '2.5.1'
    if module == 'com.google.android.gms:play-services-cronet':
        return module, '18.1.1'
    if module in ('org.chromium.net:cronet-okhttp', 'com.google.net.cronet:cronet-okhttp'):
        return 'com.google.net.cronet:cronet-okhttp', '0.1.1'
    if name in ('library', 'ffmpeg', 'aria2c') and group in ('com.github.yausername.youtubedl-android', 'io.github.junkfood02.youtubedl-android'):
        return f'io.github.junkfood02.youtubedl-android:{name}', '0.18.1'
    return None

def repair_toml(path: Path, text: str) -> str:
    lines = text.splitlines()
    section = ''
    aliases = {}
    seen = {}
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            section = stripped
            seen = {}
            continue
        if section == '[libraries]':
            key_match = re.match(r'^\s*([A-Za-z0-9_.-]+)\s*=', line)
            if not key_match:
                continue
            key = key_match.group(1)
            body = line.split('=', 1)[1]
            module_match = re.search(r'module\s*=\s*"([^"]+)"', body)
            group_match = re.search(r'group\s*=\s*"([^"]+)"', body)
            name_match = re.search(r'name\s*=\s*"([^"]+)"', body)
            module = module_match.group(1) if module_match else None
            if module and ':' in module:
                group, name = module.split(':', 1)
            elif group_match and name_match:
                group, name = group_match.group(1), name_match.group(1)
            else:
                continue
            wanted = desired_for(group, name)
            if not wanted:
                continue
            new_module, version = wanted
            ref_match = re.search(r'version\.ref\s*=\s*"([^"]+)"', body)
            inline_version = re.search(r'version\s*=\s*"([^"]+)"', body)
            if ref_match:
                aliases[ref_match.group(1)] = version
            elif inline_version:
                body = body.replace('version = "' + inline_version.group(1) + '"', 'version = "' + version + '"')
            if module_match:
                body = body.replace('module = "' + module + '"', 'module = "' + new_module + '"')
            else:
                body = body.replace('group = "' + group + '"', 'group = "' + new_module.split(':', 1)[0] + '"')
            lines[i] = line.split('=', 1)[0] + '=' + body
            changes.append(f'{path.relative_to(root)}: repaired {group}:{name} coordinate/version')
        elif section == '[plugins]':
            if 'com.android.application' in line or 'com.android.library' in line:
                ref_match = re.search(r'version\.ref\s*=\s*"([^"]+)"', line)
                if ref_match:
                    aliases[ref_match.group(1)] = '8.9.1'
                else:
                    version_match = re.search(r'version\s*=\s*"([0-9.]+)"', line)
                    if version_match:
                        line = line[:version_match.start(1)] + '8.9.1' + line[version_match.end(1):]
                        lines[i] = line
                        changes.append(f'{path.relative_to(root)}: raised Android Gradle Plugin to 8.9.1')
    section = ''
    seen = {}
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            section = stripped
            seen = {}
            continue
        if section == '[versions]':
            match = re.match(r'^\s*([A-Za-z0-9_.-]+)\s*=\s*"([^"]+)"', line)
            if match:
                key, value = match.group(1), match.group(2)
                if key in aliases:
                    wanted = aliases[key]
                    lines[i] = line[:match.start(2)] + wanted + line[match.end(2):]
                    changes.append(f'{path.relative_to(root)}: updated catalog alias {key} to {wanted}')
                elif key.lower().replace('_', '-').replace('.', '-') in ('agp', 'android-gradle-plugin', 'android-gradle') and value != '8.9.1':
                    lines[i] = line[:match.start(2)] + '8.9.1' + line[match.end(2):]
                    changes.append(f'{path.relative_to(root)}: raised Android Gradle Plugin alias {key} to 8.9.1')
                elif key.lower().replace('_', '').replace('-', '') in ('compilesdk', 'compilesdkversion', 'androidcompilesdk') and value != '36':
                    lines[i] = line[:match.start(2)] + '36' + line[match.end(2):]
                    changes.append(f'{path.relative_to(root)}: updated {key} to Android API 36')
        if section in ('[versions]', '[libraries]', '[plugins]'):
            key_match = re.match(r'^\s*([A-Za-z0-9_.-]+)\s*=', line)
            if key_match:
                key = key_match.group(1)
                if key in seen:
                    lines[seen[key]] = None
                    changes.append(f'{path.relative_to(root)}: removed duplicate TOML key {key}')
                seen[key] = i
    return '\n'.join(line for line in lines if line is not None) + ('\n' if text.endswith('\n') else '')

for path in root.rglob('*'):
    if not path.is_file() or any(part in ('.gradle', 'build') for part in path.parts):
        continue
    if path.suffix not in ('.toml', '.gradle', '.kts', '.properties'):
        continue
    original = path.read_text(errors='ignore')
    updated = original
    if path.suffix == '.toml':
        updated = repair_toml(path, updated)
    else:
        replacements = {
            'com.composables:composeunstyled:1.20.1': 'com.composables:composeunstyled:1.49.9',
            'com.composables:composeunstyled:1.20.0': 'com.composables:composeunstyled:1.49.9',
            'com.composables:core:1.19.3': 'com.composables:core:1.49.9',
            'com.google.android.gms:play-services-cronet:119.6045.31': 'com.google.android.gms:play-services-cronet:18.1.1',
            'sh.calvin.reorderable:reorderable:2.4.4': 'sh.calvin.reorderable:reorderable:2.5.1',
            'org.chromium.net:cronet-okhttp:131.0.6778.108': 'com.google.net.cronet:cronet-okhttp:0.1.1',
            'com.github.yausername.youtubedl-android': 'io.github.junkfood02.youtubedl-android',
        }
        for old, new in replacements.items():
            updated = updated.replace(old, new)
        updated = re.sub(r'(io\.github\.junkfood02\.youtubedl-android:(?:library|ffmpeg|aria2c):)0\.16\.1', r'\g<1>0.18.1', updated)
        updated = re.sub(r'(compileSdk(?:Version)?\s*(?:=\s*)?)(?:[0-9]+)', r'\g<1>36', updated)
        updated = re.sub(r'(compileSdkVersion\s*\(\s*)([0-9]+)(\s*\))', r'\g<1>36\g<3>', updated)
        updated = re.sub(r'(id\s*\(?\s*["\']com\.android\.(?:application|library)["\']\s*\)?\s+version\s+["\'])[0-9.]+(["\'])', r'\g<1>8.9.1\g<2>', updated)
        updated = updated.replace('com.android.tools.build:gradle:8.8.0', 'com.android.tools.build:gradle:8.9.1')
        updated = updated.replace('com.android.tools.build:gradle:8.8.1', 'com.android.tools.build:gradle:8.9.1')
        updated = updated.replace('com.android.tools.build:gradle:8.9.0', 'com.android.tools.build:gradle:8.9.1')
        updated = updated.replace('libs.androidx.compose.ui.googlefonts.let { libs.androidx.compose.ui.text.googlefonts }', 'libs.androidx.compose.ui.text.googlefonts')
        manifest = path.parent / 'src/main/AndroidManifest.xml'
        has_hilt = ('com.google.dagger.hilt.android' in updated or 'libs.plugins.hilt' in updated)
        if manifest.is_file() and has_hilt:
            hilt_version = '2.57.1'
            for catalog in root.rglob('*.toml'):
                for catalog_line in catalog.read_text(errors='ignore').splitlines():
                    if 'hilt' in catalog_line.lower():
                        version_match = re.search(r'"(2\.\d+\.\d+)"', catalog_line)
                        if version_match:
                            hilt_version = version_match.group(1)
            has_runtime = ('hilt-android' in updated or re.search(r'hilt[._]android', updated))
            if not has_runtime and 'dependencies {' in updated:
                updated = updated.replace('dependencies {', 'dependencies {\n    implementation("com.google.dagger:hilt-android:' + hilt_version + '")', 1)
                changes.append(f'{path.relative_to(root)}: added missing Hilt Android runtime dependency {hilt_version}')
            has_compiler = ('hilt-compiler' in updated or re.search(r'hilt[._]compiler', updated))
            if not has_compiler:
                processor = 'ksp' if re.search(r'\bksp\b', updated) else 'kapt'
                if processor == 'kapt' and not re.search(r'\bkapt\b|kotlin-kapt', updated):
                    if 'plugins {' in updated:
                        updated = updated.replace('plugins {', 'plugins {\n    id("org.jetbrains.kotlin.kapt")', 1)
                    elif 'plugins{' in updated:
                        updated = updated.replace('plugins{', 'plugins{\n    id("org.jetbrains.kotlin.kapt")', 1)
                compiler_line = f'    {processor}("com.google.dagger:hilt-compiler:{hilt_version}")'
                if 'dependencies {' in updated:
                    updated = updated.replace('dependencies {', 'dependencies {\n' + compiler_line, 1)
                    changes.append(f'{path.relative_to(root)}: added missing Hilt compiler via {processor} ({hilt_version})')
    if updated != original:
        path.write_text(updated)
        changes.append(f'{path.relative_to(root)}: repaired Android build metadata')

for path in root.rglob('*.kt'):
    if any(part in ('.gradle', 'build') for part in path.parts):
        continue
    original = path.read_text(errors='ignore')
    updated = original.replace('org.chromium.net.okhttp.CronetInterceptor', 'com.google.net.cronet.okhttptransport.CronetInterceptor')
    if updated != original:
        path.write_text(updated)
        changes.append(f'{path.relative_to(root)}: corrected Cronet OkHttp import package')

for path in root.rglob('*.xml'):
    if any(part in ('.gradle', 'build') for part in path.parts):
        continue
    original = path.read_text(errors='ignore')
    updated = original.replace('android:postSplashScreenTheme', 'postSplashScreenTheme')
    if updated != original:
        path.write_text(updated)
        changes.append(f'{path.relative_to(root)}: corrected AndroidX SplashScreen postSplashScreenTheme namespace')
# Repair confirmed Aurora Get source API mismatches in the extracted copy.
for source_file in root.rglob('*.kt'):
    if any(part in ('.gradle', 'build') for part in source_file.parts):
        continue
    original = source_file.read_text(errors='ignore')
    updated = original
    if source_file.name == 'AuroraResult.kt':
        updated = updated.replace('inline fun <R> map(', 'fun <R> map(')
        updated = updated.replace('inline fun onSuccess(', 'fun onSuccess(')
        updated = updated.replace('inline fun onFailure(', 'fun onFailure(')
        if updated != original:
            changes.append(f'{source_file.relative_to(root)}: removed invalid inline modifiers from interface members')
    if source_file.name == 'DownloadRepository.kt':
        updated = updated.replace(
            'import com.auroraget.app.engine.SizeProbe',
            'import com.auroraget.app.data.SizeProbe'
        )
        updated = updated.replace(
            'streamSingle(entity, file) { written, speed ->',
            'streamSingle(entity, file) { written, speed, connections ->'
        )
        updated = updated.replace(
            'publish(entity, written, total, speed, 1, DownloadStatus.DOWNLOADING)',
            'publish(entity, written, total, speed, connections, DownloadStatus.DOWNLOADING)'
        )
    elif source_file.name == 'NetworkAndExtractors.kt':
        updated = updated.replace(
            'val cookie = cookies.headerFor(HttpUrl.get(url))',
            'val cookie = cookies.loadForRequest(url.toHttpUrlOrNull() ?: return builder)\n            .joinToString("; ") { "\${it.name}=\${it.value}" }'
        )
    elif source_file.name == 'BrowserScreen.kt':
        if 'import com.auroraget.app.ui.components.ScreenHeader' not in updated:
            anchor = 'import com.auroraget.app.ui.components.AuroraTag'
            if anchor in updated:
                updated = updated.replace(anchor, anchor + '\nimport com.auroraget.app.ui.components.ScreenHeader', 1)
            else:
                updated = updated.replace(
                    'import com.auroraget.app.ui.components.AuroraSheet',
                    'import com.auroraget.app.ui.components.AuroraSheet\nimport com.auroraget.app.ui.components.ScreenHeader',
                    1
                )
        updated = updated.replace(
            'AuroraIconButton("↻") { webView?.reload() }',
            'AuroraIconButton("↻", onClick = { webView?.reload(); Unit })'
        )
        updated = updated.replace(
            'AuroraIconButton("⌂") { current = "https://www.youtube.com"; webView?.loadUrl(current) }',
            'AuroraIconButton("⌂", onClick = { current = "https://www.youtube.com"; webView?.loadUrl(current); Unit })'
        )
    elif source_file.name == 'Glass.kt':
        updated = updated.replace(
            'style.copy(brush = brush, color = c.textPrimary)',
            'style.copy(brush = brush)'
        )
    elif 'hazeChild(' in updated and re.search(r'\bshape\s*=\s*shape', updated) and 'HazeStyle(' in updated:
        # The current Haze API accepts shape through Compose clipping, not as a hazeChild argument.
        updated = re.sub(
            r'Modifier\.hazeChild\(\s*state\s*=\s*hazeState,\s*shape\s*=\s*shape,\s*style\s*=\s*HazeStyle\(',
            'Modifier.clip(shape).hazeChild(\n            state = hazeState,\n            style = HazeStyle(\n                tints = emptyList(),',
            updated,
            count=1
        )
        if 'import androidx.compose.ui.draw.clip' not in updated:
            updated = updated.replace(
                'import androidx.compose.ui.Modifier',
                'import androidx.compose.ui.Modifier\nimport androidx.compose.ui.draw.clip',
                1
            )
        changes.append(f'{source_file.relative_to(root)}: migrated Haze child shape to Compose clip and disambiguated HazeStyle')

    if updated != original:
        source_file.write_text(updated)
        changes.append(f'{source_file.relative_to(root)}: repaired confirmed Compose/download/browser API mismatches')

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

# Emit bounded source and Gradle configuration diagnostics for unresolved compile/build errors.
diagnostic = []
gradle_roots = []
for settings in list(root.rglob('settings.gradle')) + list(root.rglob('settings.gradle.kts')):
    if any(part in ('.gradle', 'build') for part in settings.parts):
        continue
    gradle_roots.append(settings.parent)
    diagnostic.append(f'--- SETTINGS {settings.relative_to(root)} ---')
    diagnostic.extend(f'{i}: {line}' for i, line in enumerate(settings.read_text(errors='ignore').splitlines(), 1) if i <= 180)

for gradle_root in gradle_roots[:3]:
    for rel in ('build.gradle', 'build.gradle.kts', 'gradle/libs.versions.toml'):
        candidate = gradle_root / rel
        if candidate.is_file():
            diagnostic.append(f'--- GRADLE FILE {candidate.relative_to(root)} ---')
            diagnostic.extend(f'{i}: {line}' for i, line in enumerate(candidate.read_text(errors='ignore').splitlines(), 1) if i <= 180)
    common_dir = gradle_root / 'core' / 'common'
    if common_dir.exists():
        diagnostic.append(f'--- MODULE core/common DIRECTORY {common_dir.relative_to(root)} ---')
        entries = sorted(common_dir.rglob('*'))
        diagnostic.extend(str(p.relative_to(root)) for p in entries[:100] if p.is_file())
        for build_file in (common_dir / 'build.gradle', common_dir / 'build.gradle.kts'):
            if build_file.is_file():
                diagnostic.append(f'--- CORE COMMON BUILD {build_file.relative_to(root)} ---')
                diagnostic.extend(f'{i}: {line}' for i, line in enumerate(build_file.read_text(errors='ignore').splitlines(), 1) if i <= 180)

snippets = {
    'AuroraResult.kt': [(1, 90)],
    'PlayerScreen.kt': [(1, 80), (180, 235)],
    'AuroraGlassComponents.kt': [(85, 115)],
    'SegmentedDownloadEngine.kt': [(185, 215), (260, 285), (390, 430)],
    'AuroraGlassComponents.kt': [(1, 145)],
    'DownloadRepository.kt': [(1, 45), (165, 215)],
    'NetworkAndExtractors.kt': [(1, 115)],
    'Glass.kt': [(245, 285)],
    'BrowserScreen.kt': [(1, 50), (150, 185), (245, 285)],
}
for filename, ranges in snippets.items():
    matches = [p for p in root.rglob(filename) if p.is_file() and not any(part in ('.gradle', 'build') for part in p.parts)]
    for source_file in matches[:2]:
        source_lines = source_file.read_text(errors='ignore').splitlines()
        diagnostic.append(f'--- SOURCE {source_file.relative_to(root)} ---')
        for first, last in ranges:
            diagnostic.append(f'-- lines {first}-{last} --')
            diagnostic.extend(f'{number}: {line}' for number, line in enumerate(source_lines, 1) if first <= number <= min(last, len(source_lines)))

for symbol in ('SizeProbe', 'headerFor', 'ScreenHeader', 'hazeEffect', 'HazeStyle'):
    occurrences = []
    for source_file in root.rglob('*.kt'):
        if any(part in ('.gradle', 'build') for part in source_file.parts):
            continue
        try:
            source_lines = source_file.read_text(errors='ignore').splitlines()
        except OSError:
            continue
        for number, line in enumerate(source_lines, 1):
            if symbol in line:
                occurrences.append(f'{source_file.relative_to(root)}:{number}: {line.strip()}')
    diagnostic.append(f'--- SYMBOL {symbol} ---')
    diagnostic.extend(occurrences[:60] or ['NO MATCH'])

for catalog in root.rglob('*.toml'):
    matches = [(i, line) for i, line in enumerate(catalog.read_text(errors='ignore').splitlines(), 1)
               if any(k in line.lower() for k in ('haze', 'composeunstyled', 'cronet', 'youtubedl', 'media3', 'reorderable', 'hilt'))]
    if matches:
        diagnostic.append(f'--- CATALOG {catalog.relative_to(root)} ---')
        diagnostic.extend(f'{i}: {line}' for i, line in matches[:120])

if diagnostic:
    changes.append('SOURCE DIAGNOSTICS START')
    changes.extend(diagnostic)
    changes.append('SOURCE DIAGNOSTICS END')

report.parent.mkdir(parents=True, exist_ok=True)
report.write_text('\n'.join(changes) + ('\n' if changes else 'No known build repairs were needed.\n'))
print(report.read_text())