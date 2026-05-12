# Using write_file Tool with Danphe

## Summary of the Fix

Your `write_file` tool is now **fully operational** with the following improvements:

✅ **UTF-8 Encoding** - All files written with explicit UTF-8 encoding
✅ **Error Handling** - Better error messages for permission issues, OS errors, invalid paths
✅ **Large Files** - Successfully handles 63.8KB+ JSON files
✅ **Backup System** - Automatically backs up files before overwriting
✅ **Directory Creation** - Creates nested directories automatically

---

## How to Use with glm-4.7

### ✓ For Small Files (< 10KB)
glm-4.7 works great for quick tasks:
```
> Generate a config file and save it to /etc/myapp/config.json
```

### ⚠ For Large Files (> 10KB)
Switch models for better performance:

**Option 1: Switch Model Before Request**
```
/model long
> Save this 2000-line Postman collection to docs/postman.json
```

**Option 2: Let Danphe Auto-Route**
Danphe automatically detects large content and uses `deepseek-v3` (60K context window) if glm-4.7's context gets full.

---

## Examples

### Example 1: Save JSON with glm-4.7
```
User: Create a Postman collection API schema and save to /tmp/api.json

Danphe:
- Generates the JSON (< 6K tokens fits in glm-4.7)
- Calls write_file tool
- Result: ✓ Written /tmp/api.json (125 lines, 4.2KB)
```

### Example 2: Save Large JSON
```
User: Generate complete DASTAA API documentation (all microservices) and save to docs/api.postman.json

Danphe:
- Router detects large content needed
- Auto-switches to deepseek-v3 (long context model)
- Generates comprehensive JSON
- Calls write_file tool
- Result: ✓ Written /tmp/api.postman.json (2765 lines, 63.8KB)
```

### Example 3: Backup & Overwrite
```
User: Update the config file at /etc/myapp/config.json

Danphe:
- Reads existing file
- Automatically creates backup: /etc/myapp/config.json.bak
- Writes new version
- Result: ✓ Written /etc/myapp/config.json (45 lines, 2.1KB)
         Backup created: /etc/myapp/config.json.bak
```

---

## Troubleshooting

### Issue: "Error: invalid path"
**Solution:** Ensure path is absolute or relative, not "/" or empty
```python
# ❌ Won't work
write_file(path="/", content="...")

# ✓ Works
write_file(path="/home/user/file.json", content="...")
write_file(path="./config.json", content="...")
```

### Issue: "Error: permission denied"
**Solution:** Ensure you have write permissions to the directory
```bash
# Check permissions
ls -ld /path/to/directory

# Fix if needed
sudo chown $USER /path/to/directory
```

### Issue: Large JSON gets truncated with glm-4.7
**Solution:** Use a longer-context model
```
/model long    # Use deepseek-v3 (60K tokens)
# Then ask Danphe to save the file
```

---

## Model Selection Guide

| Task | Model | Command |
|------|-------|---------|
| Quick tool calls | **glm-4.7** (fast) | Default / `/model fast` |
| Large files, long code | **deepseek-v3** (long) | `/model long` |
| Complex reasoning | **nemotron** (reasoning) | `/model reasoning` |

---

## Testing Your Setup

Run the test script to verify everything works:
```bash
cd /home/ram/Documents/Projects/danphe
python3 test_write_file.py
```

Expected output:
```
======================================================================
Testing write_file with large Postman collection JSON
======================================================================
...
All tests completed successfully! ✓
```

---

## What Changed in the Code

**File:** `danphe/tools.py`, function `_write()` (lines 151-179)

**Before:**
- No error handling
- No encoding specification
- Could fail silently

**After:**
- ✅ Explicit UTF-8 encoding
- ✅ Try-except for permission/OS errors
- ✅ Path validation
- ✅ Better error messages with file size info

---

## Next Steps

1. **Test with your actual use case:**
   ```
   > Create the DASTAA Postman collection and save to /tmp/dastaa.postman_collection.json
   ```

2. **If you hit limits with glm-4.7:**
   ```
   /model long
   > Now try again with the full collection
   ```

3. **Report any issues** with the error message from write_file

---

## Reference

- `danphe/tools.py` - Tool definitions and implementations
- `danphe/llm/nvidia.py` - NVIDIA NIM backend (model routing)
- `danphe/router.py` - Automatic model selection by token count
- `danphe/config.py` - Configuration and limits

**You're all set! 🚀 The write_file tool is ready to save your JSON files.**

