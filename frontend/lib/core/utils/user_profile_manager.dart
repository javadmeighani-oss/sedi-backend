/// ============================================
/// UserProfileManager - User Profile Persistence
/// ============================================
/// 
/// RESPONSIBILITY:
/// - Save/load user profile from SharedPreferences
/// - Manage user information
/// ============================================

import 'package:shared_preferences/shared_preferences.dart';
import 'package:flutter/foundation.dart';
import 'dart:convert';
import '../../data/models/user_profile.dart';

class UserProfileManager {
  static const String _profileKey = 'user_profile';

  static void _log(String message) {
    if (kDebugMode) {
      debugPrint(message);
    }
  }

  /// Load user profile from storage
  static Future<UserProfile> loadProfile() async {
    try {
      _log('[UserProfileManager] load profile start');
      final prefs = await SharedPreferences.getInstance();
      final profileJson = prefs.getString(_profileKey);
      
      if (profileJson == null) {
        _log('[UserProfileManager] no profile found');
        return UserProfile(); // Return empty profile
      }

      final json = jsonDecode(profileJson) as Map<String, dynamic>;
      final profile = UserProfile.fromJson(json);
      
      _log('[UserProfileManager] profile loaded');
      
      return profile;
    } catch (e, stackTrace) {
      _log('[UserProfileManager] error loading profile: $e');
      if (kDebugMode) debugPrint('$stackTrace');
      return UserProfile(); // Return empty profile on error
    }
  }

  /// Save user profile to storage
  static Future<bool> saveProfile(UserProfile profile) async {
    try {
      _log('[UserProfileManager] save profile start');
      
      final prefs = await SharedPreferences.getInstance();
      final json = jsonEncode(profile.toJson());
      
      final result = await prefs.setString(_profileKey, json);
      _log('[UserProfileManager] save profile result: $result');
      return result;
    } catch (e, stackTrace) {
      _log('[UserProfileManager] error saving profile: $e');
      if (kDebugMode) debugPrint('$stackTrace');
      return false;
    }
  }

  /// Update profile with new values
  static Future<bool> updateProfile(UserProfile Function(UserProfile) updater) async {
    try {
      final current = await loadProfile();
      final updated = updater(current);
      return await saveProfile(updated);
    } catch (e) {
      return false;
    }
  }

  /// Clear profile (logout)
  static Future<bool> clearProfile() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      return await prefs.remove(_profileKey);
    } catch (e) {
      return false;
    }
  }
}

