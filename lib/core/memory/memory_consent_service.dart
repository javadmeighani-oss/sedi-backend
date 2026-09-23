import '../network/api_client.dart';
import '../network/api_response.dart';
import 'memory_consent_status.dart';

/// Thin client over the existing I6 memory-consent endpoints.
///
/// GET  /memory/consent
/// POST /memory/consent/grant
/// POST /memory/consent/revoke
///
/// No silent grant. No new memory system.
class MemoryConsentService {
  MemoryConsentService({ApiClient? apiClient})
      : _api = apiClient ?? ApiClient();

  final ApiClient _api;

  Future<ApiResponse<MemoryConsentStatus>> fetchStatus() {
    return _api.get<MemoryConsentStatus>(
      '/memory/consent',
      parser: MemoryConsentStatus.tryParse,
    );
  }

  Future<ApiResponse<MemoryConsentStatus>> grant() {
    return _api.post<MemoryConsentStatus>(
      '/memory/consent/grant',
      parser: MemoryConsentStatus.tryParse,
    );
  }

  Future<ApiResponse<MemoryConsentStatus>> revoke() {
    return _api.post<MemoryConsentStatus>(
      '/memory/consent/revoke',
      parser: MemoryConsentStatus.tryParse,
    );
  }
}
