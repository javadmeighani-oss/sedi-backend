#!/usr/bin/env python3
"""
Notification Contract Test Script
Tests backend endpoints against contract requirements
"""
import requests
import json
from datetime import datetime
from typing import Dict, Any

# Use server URL instead of localhost
BASE_URL = "http://91.107.168.130:8000"
NOTIFICATIONS_URL = f"{BASE_URL}/notifications"
FEEDBACK_URL = f"{BASE_URL}/notifications/feedback"

def test_get_notifications(user_id: int = 1) -> Dict[str, Any]:
    """Test GET /notifications endpoint"""
    print(f"\n{'='*60}")
    print("TEST A2: GET /notifications")
    print(f"{'='*60}")
    
    response = requests.get(NOTIFICATIONS_URL, params={"user_id": user_id})
    print(f"Status Code: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ Error: {response.text}")
        return {"ok": False, "error": response.text}
    
    data = response.json()
    print(f"Response: {json.dumps(data, indent=2, ensure_ascii=False)}")
    
    # Validate structure
    issues = []
    
    if not isinstance(data, dict):
        issues.append("Response is not an object")
        return {"ok": False, "issues": issues}
    
    if "ok" not in data:
        issues.append("Missing 'ok' field")
    elif not isinstance(data["ok"], bool):
        issues.append("'ok' must be boolean")
    
    if data.get("ok") and "data" in data:
        data_obj = data["data"]
        
        # Check required fields
        if "notifications" not in data_obj:
            issues.append("Missing 'notifications' array in data")
        elif not isinstance(data_obj["notifications"], list):
            issues.append("'notifications' must be an array")
        else:
            # Validate each notification
            for i, notif in enumerate(data_obj["notifications"]):
                notif_issues = validate_notification(notif, i)
                issues.extend(notif_issues)
        
        if "total" not in data_obj:
            issues.append("Missing 'total' field")
        elif not isinstance(data_obj["total"], int):
            issues.append("'total' must be integer")
        
        if "unread_count" not in data_obj:
            issues.append("Missing 'unread_count' field")
        elif not isinstance(data_obj["unread_count"], int):
            issues.append("'unread_count' must be integer")
    
    if issues:
        print(f"\n❌ Issues found: {len(issues)}")
        for issue in issues:
            print(f"  - {issue}")
        return {"ok": False, "issues": issues, "api_response": data}
    else:
        print("\n✅ Contract validation PASSED")
        return {"ok": True, "api_response": data}


def validate_notification(notif: Dict[str, Any], index: int) -> list:
    """Validate a single notification against contract"""
    issues = []
    prefix = f"Notification[{index}]"
    
    # Required fields
    required_fields = ["id", "type", "priority", "message", "created_at", "is_read"]
    for field in required_fields:
        if field not in notif:
            issues.append(f"{prefix}: Missing required field '{field}'")
    
    # Field types
    if "id" in notif and not isinstance(notif["id"], str):
        issues.append(f"{prefix}: 'id' must be string (got {type(notif['id']).__name__})")
    
    if "type" in notif:
        valid_types = ["info", "alert", "reminder", "check_in", "achievement"]
        if notif["type"] not in valid_types:
            issues.append(f"{prefix}: Invalid 'type' value: {notif['type']} (must be one of {valid_types})")
    
    if "priority" in notif:
        valid_priorities = ["low", "normal", "high", "urgent"]
        if notif["priority"] not in valid_priorities:
            issues.append(f"{prefix}: Invalid 'priority' value: {notif['priority']} (must be one of {valid_priorities})")
    
    if "message" in notif and not isinstance(notif["message"], str):
        issues.append(f"{prefix}: 'message' must be string")
    
    if "created_at" in notif and not isinstance(notif["created_at"], str):
        issues.append(f"{prefix}: 'created_at' must be ISO 8601 string")
    
    if "is_read" in notif and not isinstance(notif["is_read"], bool):
        issues.append(f"{prefix}: 'is_read' must be boolean")
    
    # Optional fields
    if "title" in notif and notif["title"] is not None and not isinstance(notif["title"], str):
        issues.append(f"{prefix}: 'title' must be string or null")
    
    # Actions validation
    if "actions" in notif:
        if notif["actions"] is not None:
            if not isinstance(notif["actions"], list):
                issues.append(f"{prefix}: 'actions' must be array or null")
            else:
                for j, action in enumerate(notif["actions"]):
                    action_issues = validate_action(action, f"{prefix}.actions[{j}]")
                    issues.extend(action_issues)
    
    # Metadata validation
    if "metadata" in notif:
        if notif["metadata"] is not None:
            if not isinstance(notif["metadata"], dict):
                issues.append(f"{prefix}: 'metadata' must be object or null")
            else:
                metadata_issues = validate_metadata(notif["metadata"], f"{prefix}.metadata")
                issues.extend(metadata_issues)
    
    return issues


def validate_action(action: Dict[str, Any], prefix: str) -> list:
    """Validate action object"""
    issues = []
    
    required = ["id", "label", "type"]
    for field in required:
        if field not in action:
            issues.append(f"{prefix}: Missing required field '{field}'")
    
    if "type" in action:
        valid_types = ["quick_reply", "navigate", "dismiss", "custom"]
        if action["type"] not in valid_types:
            issues.append(f"{prefix}: Invalid 'type' value: {action['type']}")
    
    if "payload" in action and action["payload"] is not None:
        if not isinstance(action["payload"], dict):
            issues.append(f"{prefix}: 'payload' must be object or null")
    
    return issues


def validate_metadata(metadata: Dict[str, Any], prefix: str) -> list:
    """Validate metadata object"""
    issues = []
    
    # All fields are optional, but if present must be strings
    for field in ["language", "tone", "context", "source"]:
        if field in metadata and metadata[field] is not None:
            if not isinstance(metadata[field], str):
                issues.append(f"{prefix}: '{field}' must be string or null")
    
    return issues


def create_test_user(name: str = "testuser", secret_key: str = "test123") -> Dict[str, Any]:
    """Create a test user"""
    print(f"\n{'='*60}")
    print("Creating test user...")
    print(f"{'='*60}")
    
    url = f"{BASE_URL}/interact/introduce"
    params = {
        "name": name,
        "secret_key": secret_key,
        "lang": "en"
    }
    
    response = requests.post(url, params=params)
    print(f"Status Code: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ Error: {response.text}")
        return {"ok": False, "error": response.text}
    
    data = response.json()
    print(f"Response: {json.dumps(data, indent=2, ensure_ascii=False)}")
    
    # Extract user_id from response
    user_id = data.get("user_id")
    if user_id:
        print(f"✅ User created with ID: {user_id}")
        return {"ok": True, "user_id": user_id}
    
    return {"ok": False, "error": "User ID not found in response"}


def create_test_notification(user_id: int = 1) -> Dict[str, Any]:
    """Create a test notification"""
    print(f"\n{'='*60}")
    print("Creating test notification...")
    print(f"{'='*60}")
    
    url = f"{BASE_URL}/notifications/create"
    params = {
        "user_id": user_id,
        "type": "info",
        "priority": "normal",
        "message": "Test notification for contract validation"
    }
    
    response = requests.post(url, params=params)
    print(f"Status Code: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ Error: {response.text}")
        return {"ok": False, "error": response.text}
    
    data = response.json()
    print(f"Response: {json.dumps(data, indent=2, ensure_ascii=False)}")
    
    return data


def test_feedback_endpoint(notification_id: str, reaction: str = "seen", action_id: str = None) -> Dict[str, Any]:
    """Test POST /notifications/feedback endpoint"""
    print(f"\n{'='*60}")
    print("TEST A3: POST /notifications/feedback")
    print(f"{'='*60}")
    
    payload = {
        "notification_id": notification_id,
        "reaction": reaction,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if action_id:
        payload["action_id"] = action_id
    
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    response = requests.post(FEEDBACK_URL, json=payload)
    print(f"Status Code: {response.status_code}")
    
    if response.status_code != 200:
        print(f"❌ Error: {response.text}")
        return {"ok": False, "error": response.text}
    
    data = response.json()
    print(f"Response: {json.dumps(data, indent=2, ensure_ascii=False)}")
    
    # Validate response
    if not isinstance(data, dict):
        return {"ok": False, "error": "Response is not an object"}
    
    if "ok" not in data or not data["ok"]:
        return {"ok": False, "error": data.get("error", "Unknown error")}
    
    print("\n✅ Feedback endpoint test PASSED")
    return {"ok": True, "data": data}


if __name__ == "__main__":
    print("="*60)
    print("NOTIFICATION CONTRACT TEST")
    print("="*60)
    
    # Test GET /notifications
    result = test_get_notifications(user_id=1)
    
    # If we have notifications, test feedback
    api_response = result.get("api_response", {})
    if api_response.get("ok") and api_response.get("data") is not None:
        data_obj = api_response["data"]
        if isinstance(data_obj, dict) and "notifications" in data_obj:
            notifications = data_obj.get("notifications", [])
            if notifications:
                first_notif = notifications[0]
                notif_id = first_notif.get("id")
                if notif_id:
                    test_feedback_endpoint(notif_id, reaction="seen")
                    test_feedback_endpoint(notif_id, reaction="like")
            else:
                print("\n⚠️  No notifications found. Creating a test notification...")
                # Try to create a test notification
                create_result = create_test_notification(user_id=1)
                if create_result.get("ok") and "data" in create_result:
                    notif_data = create_result["data"]
                    if isinstance(notif_data, dict):
                        notif_id = notif_data.get("id")
                    else:
                        notif_id = str(notif_data) if notif_data else None
                    if notif_id:
                        test_feedback_endpoint(str(notif_id), reaction="seen")
    else:
        # User not found - create test user
        api_response = result.get("api_response", {})
        error_info = api_response.get("error")
        if isinstance(error_info, dict):
            error_msg = error_info.get("message", "Unknown error")
        else:
            error_msg = str(error_info) if error_info else "Unknown error"
        print(f"\n⚠️  Error: {error_msg}")
        print("   Creating test user...")
        
        # Try to create a test user
        user_result = create_test_user()
        if user_result.get("ok"):
            user_id = user_result.get("user_id")
            print(f"\n✅ Test user created with ID: {user_id}")
            print("   Re-running notification test...")
            
            # Retry with new user
            result = test_get_notifications(user_id=user_id)
            
            api_response = result.get("api_response", {})
            if api_response.get("ok") and api_response.get("data") is not None:
                data_obj = api_response["data"]
                if isinstance(data_obj, dict) and "notifications" in data_obj:
                    notifications = data_obj.get("notifications", [])
                    if notifications:
                        first_notif = notifications[0]
                        notif_id = first_notif.get("id")
                        if notif_id:
                            test_feedback_endpoint(notif_id, reaction="seen")
                    else:
                        print("\n⚠️  No notifications found. Creating a test notification...")
                        create_result = create_test_notification(user_id=user_id)
                        if create_result.get("ok") and "data" in create_result:
                            notif_data = create_result["data"]
                            if isinstance(notif_data, dict):
                                notif_id = notif_data.get("id")
                            else:
                                notif_id = str(notif_data) if notif_data else None
                            if notif_id:
                                test_feedback_endpoint(str(notif_id), reaction="seen")
    
    print("\n" + "="*60)
    print("TEST COMPLETE")
    print("="*60)

