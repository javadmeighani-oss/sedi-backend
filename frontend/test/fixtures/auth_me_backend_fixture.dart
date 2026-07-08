/// Backend `/auth/me` contract fixture derived from `MeOut.model_dump()`.
/// Source: `backend/app/schemas/auth_otp.py` + `build_me_response()`.
library;

const Map<String, dynamic> backendAuthMeIncompleteProfile = {
  'user_id': 42,
  'phone': '+989121234567',
  'name': null,
  'preferred_language': 'fa',
  'account_type': 'normal',
  'birth_year': null,
  'birth_day': null,
  'birth_month': null,
  'calendar_type': null,
  'date_of_birth': null,
  'sex': null,
  'addressing_preference': null,
  'timezone': null,
  'height_cm': null,
  'weight_kg': null,
  'display_name': null,
  'language': 'fa',
};

const Map<String, dynamic> backendAuthMeCompleteProfile = {
  'user_id': 42,
  'phone': '+989121234567',
  'name': 'Sara',
  'preferred_language': 'fa',
  'account_type': 'normal',
  'birth_year': 1370,
  'birth_day': 1,
  'birth_month': 1,
  'calendar_type': 'jalali',
  'date_of_birth': '1991-04-04',
  'sex': 'female',
  'addressing_preference': null,
  'timezone': 'Asia/Tehran',
  'height_cm': 165,
  'weight_kg': 62.5,
  'display_name': 'Sara',
  'language': 'fa',
};

Map<String, dynamic> backendAuthMeEnvelope(Map<String, dynamic> profile) => {
      'ok': true,
      'data': profile,
      'error': null,
    };
