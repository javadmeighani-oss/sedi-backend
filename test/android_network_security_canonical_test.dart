import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:sedi_app/core/config/app_config.dart';

String _read(String relativePath) => File(relativePath).readAsStringSync();

bool _exists(String relativePath) => File(relativePath).existsSync();

void main() {
  test('production API remains HTTPS canonical base', () {
    expect(AppConfig.baseUrl, 'https://api.sedi-ai.com');
    expect(AppConfig.baseUrl.startsWith('https://'), isTrue);
    expect(AppConfig.baseUrl.contains('91.107.168.130'), isFalse);

    final config = _read('lib/core/config/app_config.dart');
    expect(config.contains('https://api.sedi-ai.com'), isTrue);
    expect(config.contains('91.107.168.130'), isFalse);
    expect(config.contains('http://api.sedi-ai.com'), isFalse);
  });

  test('main Android cleartext and legacy direct-IP policy are absent', () {
    final manifest = _read('android/app/src/main/AndroidManifest.xml');
    expect(manifest.contains('usesCleartextTraffic="true"'), isFalse);
    expect(manifest.contains('networkSecurityConfig'), isFalse);
    expect(manifest.contains('91.107.168.130'), isFalse);
    expect(manifest.contains('android.permission.INTERNET'), isTrue);

    expect(
      _exists('android/app/src/main/res/xml/network_security_config.xml'),
      isFalse,
    );

    // Non-archive product tree must not reintroduce the legacy IP.
    final libRoot = Directory('lib');
    final androidRoot = Directory('android');
    const textExts = <String>{
      '.dart',
      '.xml',
      '.gradle',
      '.kts',
      '.properties',
      '.kt',
      '.java',
      '.yml',
      '.yaml',
      '.md',
      '.txt',
      '.json',
    };
    final hits = <String>[];
    for (final root in [libRoot, androidRoot]) {
      for (final f in root.listSync(recursive: true)) {
        if (f is! File) continue;
        final path = f.path.replaceAll('\\', '/');
        final lower = path.toLowerCase();
        final dot = lower.lastIndexOf('.');
        if (dot < 0) continue;
        final ext = lower.substring(dot);
        if (!textExts.contains(ext)) continue;
        final src = f.readAsStringSync();
        if (src.contains('91.107.168.130')) {
          hits.add(path);
        }
      }
    }
    expect(hits, isEmpty, reason: 'legacy direct IP must be absent from lib/android');
  });
}
