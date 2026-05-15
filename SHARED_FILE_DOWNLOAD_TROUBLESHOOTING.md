# SecureDrop: Shared File Download 404 - Troubleshooting Guide

## 🔴 Issue

```
GET /api/shared-files/{file_id}/download → 404 Not Found
```

Files appear in the shared files list (200 OK) but fail to download (404 error).

---

## 🔍 Debug Steps

### Step 1: Use the New Debug Endpoint

```bash
# Get your access token
ACCESS_TOKEN="your_token_here"
FILE_ID="AT6VhJqRWyCfRVK_CGHO1g"

# Run debug endpoint
curl -X GET "http://localhost:8000/api/debug/shared-files/${FILE_ID}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  -H "Content-Type: application/json" | jq .
```

**Example Output (Working):**

```json
{
  "file_id": "AT6VhJqRWyCfRVK_CGHO1g",
  "current_user_id": "user_123",
  "file_exists": true,
  "file_info": {
    "id": "AT6VhJqRWyCfRVK_CGHO1g",
    "name": "document.pdf",
    "owner_id": "user_456"
  },
  "total_shares": 2,
  "all_shares": [
    {
      "recipient_id": "user_123",
      "owner_id": "user_456",
      "permission": "download"
    },
    {
      "recipient_id": "user_789",
      "owner_id": "user_456",
      "permission": "download"
    }
  ],
  "my_share": {
    "recipient_id": "user_123",
    "permission": "download"
  },
  "can_download": true
}
```

**Example Output (Issue):**

```json
{
  "can_download": false,
  "my_share": null,
  "total_shares": 2,
  "all_shares": [
    {
      "recipient_id": "user_999",
      "owner_id": "user_456",
      "permission": "download"
    }
  ]
}
```

---

## 🐛 Common Issues & Solutions

### Issue 1: `can_download: false` but `total_shares > 0`

**Problem:** The file is shared with OTHER users, not with you.

**Solution:**

```bash
# 1. Have the file owner share it with you
# OR
# 2. Check that you're logged in as the right user
curl -X GET http://localhost:8000/api/users \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" | jq .

# 3. Share the file with the correct recipient username
curl -X POST "http://localhost:8000/api/files/{file_id}/share-user" \
  -H "Authorization: Bearer ${OWNER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "recipient_username": "correct_username",
    "permission": "download"
  }'
```

---

### Issue 2: `file_exists: false`

**Problem:** The file ID is wrong or the file was deleted.

**Solution:**

```bash
# List all your files
curl -X GET http://localhost:8000/api/files \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" | jq '.[] | {id, name}'

# List files shared with you
curl -X GET http://localhost:8000/api/shared-files \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" | jq '.[] | {file_id, file_name}'

# Use the correct file_id from the response
```

---

### Issue 3: `total_shares: 0`

**Problem:** The file exists but has NO share records at all.

**Solution (Database Issue):**

```bash
# Re-share the file
curl -X POST "http://localhost:8000/api/files/{file_id}/share-users" \
  -H "Authorization: Bearer ${OWNER_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "recipient_usernames": ["user1", "user2"],
    "permission": "download"
  }'

# Then verify with debug endpoint
curl -X GET "http://localhost:8000/api/debug/shared-files/${FILE_ID}" \
  -H "Authorization: Bearer ${ACCESS_TOKEN}"
```

---

### Issue 4: Different User ID Expected

**Problem:** You might be logged in as the wrong user.

**Solution:**

```bash
# Decode your JWT token to see who you are
# Use this to extract the 'sub' claim:

import jwt
import json

token = "YOUR_ACCESS_TOKEN"
decoded = jwt.decode(token, options={"verify_signature": False})
print(f"Logged in as user: {decoded['sub']}")
print(f"Username: {decoded['username']}")

# Compare with the share recipient_id from debug endpoint
```

---

## 🧹 Database Cleanup (If Needed)

If you need to reset all shared files and start fresh:

```sql
-- WARNING: This deletes ALL file shares!
DELETE FROM file_shares;
```

Then re-share files using the API.

---

## 📊 Complete Workflow Test

### User A: Upload and Share File

```bash
# Login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"user_a","password":"password"}' > login_a.json

ADMIN_TOKEN=$(jq -r '.access_token' login_a.json)
ADMIN_ID=$(jq -r '.user_id' login_a.json)  # May need to decode JWT

# Request upload
curl -X POST http://localhost:8000/api/upload-request \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"file_name":"test.pdf","file_size":1024}' > upload_req.json

TOKEN=$(jq -r '.token' upload_req.json)

# Upload file (simulated)
echo "test file content" | curl -X POST "http://localhost:8000/api/upload-commit?token=${TOKEN}" \
  -H "Content-Type: application/octet-stream" \
  --data-binary @-

# Get file ID
curl -X GET http://localhost:8000/api/files \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" | jq '.[] | select(.name=="test.pdf") | .id' > file_id.json

FILE_ID=$(jq -r '.' file_id.json)
echo "File ID: $FILE_ID"

# Share with user_b
curl -X POST "http://localhost:8000/api/files/${FILE_ID}/share-user" \
  -H "Authorization: Bearer ${ADMIN_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"recipient_username":"user_b","permission":"download"}'
```

### User B: Receive and Download File

```bash
# Login as user_b
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"user_b","password":"password"}' > login_b.json

USER_B_TOKEN=$(jq -r '.access_token' login_b.json)

# List shared files
curl -X GET http://localhost:8000/api/shared-files \
  -H "Authorization: Bearer ${USER_B_TOKEN}" | jq '.[] | {file_id, file_name}'

# Debug: Check if we can download
curl -X GET "http://localhost:8000/api/debug/shared-files/${FILE_ID}" \
  -H "Authorization: Bearer ${USER_B_TOKEN}" | jq '.can_download'

# Download
curl -X GET "http://localhost:8000/api/shared-files/${FILE_ID}/download" \
  -H "Authorization: Bearer ${USER_B_TOKEN}" \
  -o downloaded_file.pdf
```

---

## 📋 Checklist

- [ ] File exists (can list it in `/api/files`)
- [ ] File was shared with the correct user
- [ ] You're logged in as the recipient user
- [ ] Debug endpoint shows `"can_download": true`
- [ ] File share has `"permission": "download"` (not just "view")
- [ ] Server logs show detailed error messages (new logging added)

---

## 🔧 Server Logs

After this update, server logs will now show:

```
DEBUG: Download failed - You are not the recipient of this shared file (recipient_id: user_999, your id: user_123)
  File exists: True
  Share record: {'id': '...', 'recipient_id': 'user_999', 'owner_id': '...'}
  Current user: user_123
```

**Check the console where FastAPI is running for these debug messages!**

---

## 🚀 Next Steps

1. **Run the debug endpoint** for the failing file ID
2. **Check the output** against the solutions above
3. **Share the debug output** if you need further help
4. **Restart the server** to see new log messages

---
