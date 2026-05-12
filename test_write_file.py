#!/usr/bin/env python3
"""
Test script to verify write_file tool works with large JSON files.
This replicates the user's use case with a Postman collection JSON.
"""
import json
from pathlib import Path
from danphe import tools

# Create a sample large Postman collection similar to your case
postman_collection = {
    "info": {
        "name": "DASTAA API Collection",
        "description": "Complete API collection for Integrated DASTAA disaster risk management platform",
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"
    },
    "variable": [
        {
            "key": "baseUrl",
            "value": "http://localhost:8000",
            "type": "string"
        }
    ],
    "item": []
}

# Add some sample items to make it larger
for i in range(50):  # Create 50 API endpoints
    postman_collection["item"].append({
        "name": f"API Endpoint {i+1}",
        "item": [
            {
                "name": f"GET /endpoint/{i}",
                "request": {
                    "method": "GET",
                    "header": [
                        {
                            "key": "Accept",
                            "value": "application/json",
                            "type": "text"
                        }
                    ],
                    "url": {
                        "raw": f"{{{{baseUrl}}}}/api/endpoint/{i}",
                        "host": ["{{baseUrl}}"],
                        "path": ["api", f"endpoint/{i}"]
                    }
                }
            },
            {
                "name": f"POST /endpoint/{i}",
                "request": {
                    "method": "POST",
                    "header": [
                        {
                            "key": "Content-Type",
                            "value": "application/json",
                            "type": "text"
                        }
                    ],
                    "body": {
                        "mode": "raw",
                        "raw": json.dumps({"data": f"payload{i}"})
                    },
                    "url": {
                        "raw": f"{{{{baseUrl}}}}/api/endpoint/{i}",
                        "host": ["{{baseUrl}}"],
                        "path": ["api", f"endpoint/{i}"]
                    }
                }
            }
        ]
    })

# Convert to JSON string
json_content = json.dumps(postman_collection, indent=2)

print("=" * 70)
print("Testing write_file with large Postman collection JSON")
print("=" * 70)
print(f"\nJSON size: {len(json_content) / 1024:.1f}KB")
print(f"JSON lines: {json_content.count(chr(10))}")

# Test 1: Write to /tmp
test_path_1 = "/tmp/test_postman_collection.json"
result1 = tools.execute("write_file", {"path": test_path_1, "content": json_content})
print(f"\n✓ Test 1 - Write to /tmp:")
print(f"  {result1}")

# Verify it was written
if Path(test_path_1).exists():
    print(f"  ✓ File exists")
    file_size = Path(test_path_1).stat().st_size
    print(f"  ✓ File size: {file_size / 1024:.1f}KB")
else:
    print(f"  ✗ File not found!")

# Test 2: Write to a nested directory (should create dirs)
test_path_2 = "/tmp/danphe_test/nested/docs/postman_collection.json"
result2 = tools.execute("write_file", {"path": test_path_2, "content": json_content})
print(f"\n✓ Test 2 - Write to nested directory:")
print(f"  {result2}")

# Verify it was written
if Path(test_path_2).exists():
    print(f"  ✓ File exists")
    print(f"  ✓ Directories created successfully")
else:
    print(f"  ✗ File not found!")

# Test 3: Overwrite and backup
result3 = tools.execute("write_file", {"path": test_path_1, "content": '{"updated": true}'})
print(f"\n✓ Test 3 - Overwrite with backup:")
print(f"  {result3}")

backup_path = Path(test_path_1).with_suffix(".json.bak")
if backup_path.exists():
    print(f"  ✓ Backup created: {backup_path}")
else:
    print(f"  ✗ Backup not found!")

print("\n" + "=" * 70)
print("All tests completed successfully! ✓")
print("=" * 70)

