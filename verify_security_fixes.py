#!/usr/bin/env python
import os
import sys
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ImsV3.settings')
django.setup()

from django.conf import settings

print("\n" + "="*70)
print("SECURITY SETTINGS VERIFICATION - POST-FIX")
print("="*70 + "\n")

checks = {
    "SESSION_COOKIE_HTTPONLY": True,
    "SESSION_COOKIE_SAMESITE": "Strict",
    "CSRF_COOKIE_HTTPONLY": True,
    "CSRF_COOKIE_SAMESITE": "Strict",
    "SECURE_CONTENT_TYPE_NOSNIFF": True,
    "SECURE_BROWSER_XSS_FILTER": True,
    "X_FRAME_OPTIONS": "DENY",
    "REFERRER_POLICY": "strict-origin-when-cross-origin",
}

passed = 0
for setting_name, expected_value in checks.items():
    actual_value = getattr(settings, setting_name, None)
    is_correct = actual_value == expected_value
    status = "OK" if is_correct else "FAIL"
    print(f"[{status}] {setting_name}: {actual_value}")
    if is_correct:
        passed += 1

print("\n" + "-"*70)
print(f"Results: {passed}/{len(checks)} security settings active")
print("-"*70 + "\n")

if passed == len(checks):
    print("SUCCESS: All security fixes have been applied and are active!\n")
    sys.exit(0)
else:
    print(f"WARNING: Only {passed}/{len(checks)} checks passed.\n")
    sys.exit(1)
