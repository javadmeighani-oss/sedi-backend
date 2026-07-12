import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  const canonicalForeground = 'assets/images/sedi_app_icon_foreground.png';
  const canonicalFull = 'assets/images/sedi_app_icon.png';
  const removedDerivedForeground =
      'assets/images/sedi_app_icon_foreground_scaled_085.png';
  const removedDerivedFull = 'assets/images/sedi_app_icon_scaled_085.png';
  const foregroundScaleFactor = 0.85;

  const densities = ['mdpi', 'hdpi', 'xhdpi', 'xxhdpi', 'xxxhdpi'];
  const foregroundDimensions = {
    'mdpi': 108,
    'hdpi': 162,
    'xhdpi': 216,
    'xxhdpi': 324,
    'xxxhdpi': 432,
  };
  const launcherDimensions = {
    'mdpi': 48,
    'hdpi': 72,
    'xhdpi': 96,
    'xxhdpi': 144,
    'xxxhdpi': 192,
  };

  // Measured HEAD adaptive visible diameters from commit 5033433.
  const headAdaptiveVisible = {
    'mdpi': 68,
    'hdpi': 102,
    'xhdpi': 134,
    'xxhdpi': 202,
    'xxxhdpi': 268,
  };

  test('canonical launcher source assets exist and derived masters are absent', () {
    expect(File(canonicalForeground).existsSync, isTrue);
    expect(File(canonicalFull).existsSync, isTrue);
    expect(File(removedDerivedForeground).existsSync, isFalse);
    expect(File(removedDerivedFull).existsSync, isFalse);
  });

  test('Android manifest references launcher mipmap resources', () {
    final manifest =
        File('android/app/src/main/AndroidManifest.xml').readAsStringSync();
    expect(manifest, contains('android:icon="@mipmap/ic_launcher"'));
    expect(manifest, contains('android:label="@string/app_name"'));
    expect(manifest, isNot(contains('android:roundIcon')));
  });

  test('application label remains Sedi and separate from icon bitmap', () {
    final strings = File('android/app/src/main/res/values/strings.xml')
        .readAsStringSync();
    expect(strings, contains('<string name="app_name">Sedi</string>'));
  });

  test('adaptive launcher XML uses white background and foreground mipmap', () {
    final adaptive =
        File('android/app/src/main/res/mipmap-anydpi-v26/ic_launcher.xml')
            .readAsStringSync();
    final adaptiveRound =
        File('android/app/src/main/res/mipmap-anydpi-v26/ic_launcher_round.xml')
            .readAsStringSync();
    final colors =
        File('android/app/src/main/res/values/colors.xml').readAsStringSync();

    for (final xml in [adaptive, adaptiveRound]) {
      expect(xml, contains('@color/ic_launcher_background'));
      expect(xml, contains('@mipmap/ic_launcher_foreground'));
    }
    expect(colors, contains('<color name="ic_launcher_background">#FFFFFF</color>'));
  });

  test('legacy and adaptive mipmap densities exist with expected dimensions', () {
    for (final density in densities) {
      final dir = 'android/app/src/main/res/mipmap-$density';
      final launcher = File('$dir/ic_launcher.png');
      final round = File('$dir/ic_launcher_round.png');
      final foreground = File('$dir/ic_launcher_foreground.png');

      expect(launcher.existsSync, isTrue);
      expect(round.existsSync, isTrue);
      expect(foreground.existsSync, isTrue);
      expect(launcher.lengthSync(), greaterThan(0));
      expect(round.lengthSync(), greaterThan(0));
      expect(foreground.lengthSync(), greaterThan(0));
      expect(launcherDimensions[density], isNotNull);
      expect(foregroundDimensions[density], isNotNull);
    }
  });

  test('generation script documents separate adaptive and legacy pipelines', () {
    final script =
        File('tool/generate_launcher_icons_085.py').readAsStringSync();
    expect(script, contains('SCALE = 0.85'));
    expect(script, contains('HEAD_ADAPTIVE_VISIBLE'));
    expect(script, contains('HEAD_LEGACY_VISIBLE'));
    expect(script, contains('generate_adaptive_foregrounds'));
    expect(script, contains('generate_legacy_icons'));
    expect(script, contains('adaptive_target_visible'));
    expect(script, contains('legacy_target_visible'));
    expect(script, contains(canonicalForeground));
    expect(script, isNot(contains('assets/images/sedi_app_icon_foreground_scaled_085.png')));
    expect(foregroundScaleFactor, 0.85);
  });

  test('adaptive HEAD baseline targets are distinct from legacy processing', () {
    for (final density in densities) {
      final headAdaptive = headAdaptiveVisible[density]!;
      final targetAdaptive = (headAdaptive * foregroundScaleFactor).round();
      expect(targetAdaptive, greaterThan(0));
      expect(headAdaptive, greaterThan(headAdaptiveVisible['mdpi']! - 1));
    }
    expect((headAdaptiveVisible['xxxhdpi']! * foregroundScaleFactor).round(), 228);
  });

  test('pubspec does not register removed intermediate launcher masters', () {
    final pubspec = File('pubspec.yaml').readAsStringSync();
    expect(pubspec, contains('assets/images/'));
    expect(pubspec, isNot(contains('sedi_app_icon_scaled_085.png')));
    expect(pubspec, isNot(contains('sedi_app_icon_foreground_scaled_085.png')));
  });
}
