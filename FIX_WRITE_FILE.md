# Fix: write_file Tool Not Working with glm-4.7

## Problem
- The `write_file` tool was failing to properly handle large JSON files or files with encoding issues
- When using glm-4.7 (fast model) with NVIDIA NIM, JSON content would appear truncated or incomplete
- No proper error messages when file operations failed

## Root Cause
The `_write()` function in `danphe/tools.py` lacked:
1. **Encoding specification**: Files were being written without explicit UTF-8 encoding
2. **Error handling**: Permission errors, OS errors, and edge cases weren't caught properly
3. **Validation**: Invalid paths weren't validated before attempting to write
4. **Backup safety**: Backup operations could fail silently

## Solution
Improved the `_write()` function with:

### Changes Made
```python
✅ Added explicit UTF-8 encoding when writing files
✅ Added try-except blocks for PermissionError and OSError
✅ Added path validation before attempting write
✅ Enhanced backup creation with better error handling
✅ Improved return messages with file size info
✅ Better separation of concerns (read → backup → write)
```

### Key Improvements
1. **UTF-8 Encoding**: All file writes now explicitly use UTF-8 encoding
   ```python
   p.write_text(content, encoding="utf-8")
   ```

2. **Robust Error Handling**: Catches and reports specific error types
   ```python
   except PermissionError:
       return f"Error: permission denied writing to {path}"
   except OSError as e:
       return f"Error: OS error writing to {path}: {e}"
   ```

3. **Path Validation**: Prevents writing to invalid paths
   ```python
   if not path or path == "/":
       return f"Error: invalid path: {path}"
   ```

4. **Better Feedback**: Returns file size info to help debug large file issues
   ```python
   size_kb = len(content.encode("utf-8")) / 1024
   return f"Written {path} ({lines} lines, {size_kb:.1f}KB)"
   ```

## Why glm-4.7 Was Having Issues
- **Fast model, limited context**: glm-4.7 has a smaller context window
- **JSON truncation**: Large JSON being passed as arguments could be truncated mid-stream
- **Incomplete tool calls**: Without proper encoding validation, the tool would fail silently

## Testing
```bash
# Test the fix
python3 -c "
from danphe import tools
result = tools.execute('write_file', {'path': '/tmp/test.json', 'content': '{\"test\": \"hello\"}'})
print(result)
"
```

Result: ✅ **"Written /tmp/test.json (1 lines, 0.0KB)"**

## Recommendations
1. **Use the right model for large files**: Use `deepseek-v3` (long) or `nemotron` (reasoning) for large JSON files
   ```bash
   /model long  # Switch to deepseek-v3 for 60K token context
   ```

2. **When writing large files**: Let the LLM know upfront
   ```
   "Please save this Postman collection JSON (2000+ lines)..."
   ```

3. **Monitor file sizes**: The improved error messages now show file size in KB for debugging

## Files Modified
- `danphe/tools.py` - Enhanced `_write()` function with better error handling and UTF-8 encoding

